import asyncio

import pytest

from app.ai.models import FinalVerificationDecision, ReviewDecision, RiskLevel
from app.ai.orchestrator import MultiAgentOrchestrator
from app.ai.safety import (
    classify_preflight_risk,
    deterministic_safety_response,
    safe_fallback_result,
)
from tests.review_fixtures import review_decision, verification_decision


CONCERNING_ZH_SNAPSHOT = (
    "你写下的内容显示，你可能正承受不想继续活着的念头；这需要被认真对待。"
    "即使目前没有计划，也不等于风险可以忽略。"
    "先暂停原因或童年经历的深挖。"
    "请直接确认当前安全：你现在是否有伤害自己的冲动、能否保证此刻安全、"
    "是否独处，以及身边是否有可用于伤害自己的物品或手段？"
    "请现在联系一位现实中可信任的人，把情况告诉对方并请其陪着你；"
    "同时把可能伤害自己的物品移远或交给对方保管。"
    "如果冲动增强、无法保证安全或已经准备行动，请立即结束独处，"
    "前往有人的安全地点或最近的急诊，并联系当地紧急服务或危机支持。"
)
CONCERNING_EN_SNAPSHOT = (
    "What you wrote suggests that you may be carrying thoughts of not wanting "
    "to be alive, and that needs to be taken seriously. Even without a plan "
    "right now, the risk is not safe to ignore. Pause any deeper analysis of "
    "causes or childhood for now. Please answer directly about immediate "
    "safety: do you have an urge to harm yourself right now, can you stay safe "
    "at this moment, are you alone, and do you have access to anything you "
    "could use to hurt yourself? Contact a trusted person in your real life "
    "now, tell them what is happening, and ask them to stay with you; move any "
    "possible means away or hand them to that person. If the urge grows, you "
    "cannot stay safe, or you have begun preparing, leave isolation "
    "immediately, go to a staffed safe place or the nearest emergency "
    "department, and contact local emergency or crisis support."
)
URGENT_ZH_SNAPSHOT = (
    "你写下的内容显示，当前存在需要立即处理的紧急自伤危险；"
    "先暂停童年经历或原因分析。"
    "请只回答当前安全：你是否已经开始行动，伤害自己的手段是否就在身边？"
    "无论答案是什么，现在都请立刻放下并远离任何可能伤害自己的物品或手段，"
    "把它们交给别人，结束独处并去到有人的安全地点。"
    "请马上联系一位现实中可信任的人，请对方来陪你；同时立即联系当地紧急服务，"
    "或直接前往最近的急诊。"
)
URGENT_EN_SNAPSHOT = (
    "What you wrote indicates an immediate self-harm emergency that requires "
    "action now; pause any analysis of childhood or causes. Answer only about "
    "immediate safety: have you started acting, and are any means within reach? "
    "Regardless of the answer, put down and move away from anything you could "
    "use to hurt yourself now, hand it to someone else, leave isolation, and "
    "go where other people are present. Contact a trusted person immediately "
    "and ask them to stay with you; at the same time, contact local emergency "
    "services or go directly to the nearest emergency department."
)


class StubReflectionAgent:
    def __init__(self, draft: str = "未经安全包络的草稿") -> None:
        self.draft = draft
        self.calls = 0

    async def respond(self, user_message: str) -> str:
        self.calls += 1
        return self.draft


class StubReviewAgent:
    def __init__(self, decision: ReviewDecision) -> None:
        self.decision = decision
        self.calls = 0

    async def review(self, user_message: str, reflection_draft: str) -> ReviewDecision:
        self.calls += 1
        return self.decision


class StubFinalVerifier:
    def __init__(self, candidate: str) -> None:
        self.decision = verification_decision(candidate)
        self.calls = 0

    async def verify(
        self,
        _user_message: str,
        _candidate_response: str,
        **_kwargs: object,
    ) -> FinalVerificationDecision:
        self.calls += 1
        return self.decision


class NeverCalledMemoryAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, **kwargs: object) -> None:
        self.calls += 1
        raise AssertionError("Safety responses must not call Memory.")


def build_stub_orchestrator(
    *,
    risk_level: RiskLevel = "none",
    reviewed_response: str = "这是正常的已审核回应。",
) -> tuple[
    MultiAgentOrchestrator,
    StubReflectionAgent,
    StubReviewAgent,
    NeverCalledMemoryAgent,
]:
    reflection = StubReflectionAgent()
    review = StubReviewAgent(
        review_decision(
            draft_disposition="rewritten",
            draft_findings=(
                ["pas_principle_violation"]
                if risk_level == "none"
                else ["crisis_mishandling"]
            ),
            final_response=reviewed_response,
            risk_level=risk_level,
            rationale="Synthetic Review fixture.",
        )
    )
    memory = NeverCalledMemoryAgent()
    orchestrator = MultiAgentOrchestrator(
        reflection_agent=reflection,
        review_agent=review,
        final_verifier_agent=StubFinalVerifier(reviewed_response),
        memory_agent=memory,
    )
    return orchestrator, reflection, review, memory


def test_passive_self_harm_short_circuits_provider_and_memory() -> None:
    message = "最近很绝望，有时觉得如果明天醒不过来也好，但我没有计划。"
    assessment = classify_preflight_risk(message)
    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert assessment.signal_codes == ("explicit_self_harm", "plan_denied")

    orchestrator, reflection, review, memory = build_stub_orchestrator()
    result = asyncio.run(orchestrator.respond(message))

    assert result.mode == "safety-guard"
    assert result.response_source == "safety_guard"
    assert result.risk_level == "concerning"
    assert result.support_mode == "support"
    assert result.reflection_draft is None
    assert result.review is None
    assert result.memory_candidate is None
    assert reflection.calls == 0
    assert review.calls == 0
    assert memory.calls == 0
    assert "暂停原因或童年经历的深挖" in result.response
    assert "伤害自己的冲动" in result.response
    assert "是否独处" in result.response
    assert "物品或手段" in result.response
    assert "现实中可信任的人" in result.response
    assert "当地紧急服务" in result.response


def test_urgent_self_harm_short_circuits_with_unconditional_actions() -> None:
    message = "我现在已经想好了今晚结束生命的方法，而且一个人待着。"
    assessment = classify_preflight_risk(message)
    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert assessment.signal_codes == (
        "explicit_self_harm",
        "explicit_urgent",
        "plan",
        "immediate_time",
        "alone",
    )

    orchestrator, reflection, review, memory = build_stub_orchestrator()
    result = asyncio.run(orchestrator.respond(message))

    assert result.response_source == "safety_guard"
    assert result.risk_level == "urgent"
    assert reflection.calls == 0
    assert review.calls == 0
    assert memory.calls == 0
    assert "当前存在需要立即处理的紧急自伤危险" in result.response
    assert "暂停童年经历或原因分析" in result.response
    assert "无论答案是什么，现在都请立刻" in result.response
    assert "结束独处" in result.response
    assert "现实中可信任的人" in result.response
    assert "当地紧急服务" in result.response
    assert "最近的急诊" in result.response
    assert all(number not in result.response for number in ("110", "120", "911"))


@pytest.mark.parametrize(
    "message",
    [
        "我现在想死，刀就在手边。",
        "I want to die right now and have pills within reach.",
    ],
)
def test_explicit_self_harm_plus_immediacy_and_means_is_urgent(
    message: str,
) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "immediate_time" in assessment.signal_codes
    assert "means_access" in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "我没有想死，也没有伤害自己的念头。",
        "I do not want to die, and I have no thoughts of self-harm.",
        "I do not want to die, but I want to live.",
        "I do not want to die. I have made up my mind to live.",
        "I do not want to die; I have a plan to stay safe today.",
        "我不想死，我决定了要好好活着。",
        "我在分析电影台词‘我今晚想死’，这不是我的想法。",
        "我的朋友说‘他今晚想死’，但明确不是我本人。",
        (
            "我的朋友说他想死，说的不是我。"
            "我想知道怎么帮助一个想死的朋友。"
        ),
        (
            "我的朋友说他不想活，说的不是我。"
            "我在问如何帮助他，因为他想死。"
        ),
        (
            "My friend said they want to die; not me. I want to know how to "
            "help them because they want to die."
        ),
        (
            "Movie quote: 'I want to die'; not my thought. I want to analyze "
            "why the character says they want to die."
        ),
        (
            "My friend said they want to die; not me. I am worried because "
            "they still want to die."
        ),
        "我的朋友说他想死，说的不是我。我很担心，因为他还是想死。",
        (
            "Movie quote: I want to die; not my thought. I am curious why the "
            "character wants to die."
        ),
        (
            "Movie quote: I want to die; not my thought. I am curious why "
            "suicide appears in the scene."
        ),
        "I am researching and discussing suicide prevention.",
        "我正在研究和讨论自杀预防。",
    ],
)
def test_explicit_non_self_or_denied_risk_does_not_label_user(
    message: str,
) -> None:
    assert classify_preflight_risk(message) is None


@pytest.mark.parametrize(
    "message",
    [
        "I do not want to die, but sometimes I wish I would not wake up.",
        "I do not want to die, but I keep thinking about suicide.",
        "我不想死，但最近一直有自杀的念头。",
    ],
)
def test_denial_does_not_hide_later_self_harm_disclosure(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"


@pytest.mark.parametrize(
    "message",
    [
        "I want to die. I have made up my mind.",
        "I want to die and cannot stay safe.",
        "我想死，已经决定了。",
        "我想死，不能保证安全。",
    ],
)
def test_explicit_self_harm_plus_intent_is_urgent_without_other_signals(
    message: str,
) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "intent" in assessment.signal_codes


@pytest.mark.parametrize(
    "context",
    [
        "电影角色说‘我今晚想死’，这不是我的想法；",
        "我的朋友说‘他今晚想死’，但明确不是我本人；",
    ],
)
def test_personal_urgent_disclosure_overrides_prior_non_self_context(
    context: str,
) -> None:
    assessment = classify_preflight_risk(
        context + "但我自己今晚已经想好结束生命的方法。"
    )

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "plan" in assessment.signal_codes
    assert "immediate_time" in assessment.signal_codes


def test_explicit_english_personal_risk_overrides_movie_negative_context() -> None:
    assessment = classify_preflight_risk(
        "Movie quote: 'I want to die tonight'; not me, but I myself plan to "
        "end my life tonight."
    )

    assert assessment is not None
    assert assessment.risk_level == "urgent"


@pytest.mark.parametrize(
    "message",
    [
        "电影角色说想死，这不是我的想法，但我最近也不想活了。",
        (
            "Movie quote: I want to die; not my thought, but lately I also do "
            "not want to live."
        ),
        "我的朋友说今晚想死，说的不是我，但我现在也想死。",
        "电影角色说想死，这不是我的想法。其实我最近也不想活了。",
        (
            "My friend said I want to die; not me. Actually, I do not want to "
            "live anymore."
        ),
    ],
)
def test_non_self_context_does_not_hide_later_first_person_disclosure(
    message: str,
) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"


def test_third_party_context_then_current_personal_means_is_urgent() -> None:
    assessment = classify_preflight_risk(
        "我的朋友说今晚想死，说的不是我，但我现在也想死，刀就在手边。"
    )

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "immediate_time" in assessment.signal_codes
    assert "means_access" in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "电影角色说想死，这不是我的想法。其实我现在想死，刀就在手边。",
        (
            "My friend said I want to die; not me. Actually, I want to die and "
            "cannot stay safe."
        ),
    ],
)
def test_non_self_suffix_with_personal_intent_or_means_is_urgent(
    message: str,
) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"


@pytest.mark.parametrize(
    ("message", "expected_risk"),
    [
        (
            "My friend said they want to die; not me. I want to know how to "
            "help them because I also want to die.",
            "concerning",
        ),
        (
            "My friend said they want to die; not me. I want to know how to "
            "help them because I also want to die and cannot stay safe.",
            "urgent",
        ),
    ],
)
def test_direct_personal_disclosure_inside_help_context_is_not_hidden(
    message: str,
    expected_risk: RiskLevel,
) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == expected_risk


@pytest.mark.parametrize(
    ("message", "expected_risk"),
    [
        (
            "我的朋友说他想死，说的不是我。我想知道怎么帮他，因为我也想死。",
            "concerning",
        ),
        (
            "我的朋友说他想死，说的不是我。我想知道怎么帮他，因为我也想死，"
            "而且我不能保证安全。",
            "urgent",
        ),
    ],
)
def test_chinese_direct_disclosure_inside_help_context_is_not_hidden(
    message: str,
    expected_risk: RiskLevel,
) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == expected_risk


@pytest.mark.parametrize(
    "message",
    [
        "My friend has a plan and a knife tonight. I also want to die.",
        "朋友今晚有计划，刀在手边。其实我最近也不想活了。",
    ],
)
def test_third_party_urgent_signals_do_not_escalate_user_disclosure(
    message: str,
) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert "plan" not in assessment.signal_codes
    assert "means_access" not in assessment.signal_codes
    assert "immediate_time" not in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "I also want to die. The knife is within my reach.",
        "我也想死。刀就在我手边。",
    ],
)
def test_user_accessible_means_escalates_direct_disclosure(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "means_access" in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "I want to die and the knife is within my reach, but my friend is here.",
        "我想死，刀就在我手边，但我的朋友在这里。",
    ],
)
def test_later_friend_reference_does_not_hide_user_means(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "means_access" in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        (
            "I also want to die, while my friend has a plan and a knife "
            "tonight, and I am worried."
        ),
        "我也想死，而我的朋友今晚有计划，刀在手边，最后我很担心。",
    ],
)
def test_later_user_reference_does_not_claim_friend_signals(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert "plan" not in assessment.signal_codes
    assert "means_access" not in assessment.signal_codes
    assert "immediate_time" not in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "I kinda want to die.",
        "I kind of want to die.",
        "I sort of do not want to live.",
        "I maybe want to die.",
        "我有点想死。",
        "我好像不想活了。",
        "我感觉自己想死。",
        "我似乎有自杀的念头。",
    ],
)
def test_common_hedges_still_count_as_direct_disclosure(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"


def test_each_signal_keeps_its_owner_after_later_subject_changes() -> None:
    assessment = classify_preflight_risk(
        "I want to die. My friend has pills in her hand tonight. I am worried."
    )

    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert "means_access" not in assessment.signal_codes
    assert "immediate_time" not in assessment.signal_codes


def test_later_friend_does_not_remove_already_user_owned_means() -> None:
    assessment = classify_preflight_risk(
        "I want to die. The knife is within my reach. My friend just arrived."
    )

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "means_access" in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "I am perhaps a little suicidal.",
        "I'm somewhat suicidal lately.",
        "I have lately been thinking about suicide.",
        "I sometimes feel kind of suicidal.",
        "I feel a little suicidal.",
        "我其实最近偶尔会有点不想活了。",
        "我有时候甚至会觉得死了也好。",
        "我其实有点好像不想活了。",
    ],
)
def test_extended_direct_disclosure_hedges_are_concerning(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"


@pytest.mark.parametrize(
    "message",
    [
        (
            "My friend said they are suicidal; not me. I am perhaps a little "
            "worried about their suicide risk."
        ),
        "我的朋友说他有自杀想法，说的不是我。我其实最近偶尔有点担心他的自杀风险。",
    ],
)
def test_hedged_friend_worry_is_not_a_personal_disclosure(message: str) -> None:
    assert classify_preflight_risk(message) is None


@pytest.mark.parametrize(
    "message",
    [
        (
            "I want to die, but my friend has a plan and a knife that I find "
            "worrying."
        ),
        (
            "I want to die, but my friend has a plan and a knife I am worried "
            "about tonight."
        ),
        "我也不想活了，但朋友今晚有计划、刀在手边让我很担心。",
    ],
)
def test_later_user_worry_does_not_reassign_friend_signals(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert assessment.signal_codes == ("explicit_self_harm",)


@pytest.mark.parametrize(
    "message",
    [
        "我想死。朋友有刀让我担心，今晚还有计划。",
        "我想死。朋友有刀让我担心而且今晚有计划。",
    ],
)
def test_chinese_object_pronoun_does_not_switch_signal_owner(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert assessment.signal_codes == ("explicit_self_harm",)


@pytest.mark.parametrize(
    "message",
    [
        "我想死。朋友有刀，这使得我担心，今晚还有计划。",
        "我想死。朋友有刀，这害得我担心，今晚还有计划。",
    ],
)
def test_mid_segment_chinese_object_does_not_switch_owner(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert assessment.signal_codes == ("explicit_self_harm",)


@pytest.mark.parametrize(
    "message",
    [
        "I want to die. I had no plan earlier, but now I have a plan tonight.",
        "我想死，之前没有计划，但现在已经想好了方法。",
    ],
)
def test_later_positive_plan_is_not_erased_by_earlier_denial(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "plan_denied" in assessment.signal_codes
    assert "plan" in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "I want to die tonight, but I do not have a plan.",
        "我今天想死，但没有计划。",
    ],
)
def test_plan_marker_inside_denial_span_is_not_positive(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert "plan_denied" in assessment.signal_codes
    assert "plan" not in assessment.signal_codes


@pytest.mark.parametrize(
    ("message", "expected_signal"),
    [
        ("朋友的情况让我很担心我也不想活了现在不能保证安全。", "intent"),
        ("朋友的情况让我很担心我也不想活了刀就在手边。", "means_access"),
        ("朋友的情况让我很担心我也不想活了现在已经想好了方法。", "plan"),
        ("朋友的情况让我很担心我也不想活了现在一个人。", "alone"),
    ],
)
def test_direct_disclosure_synthetically_switches_chinese_owner(
    message: str,
    expected_signal: str,
) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert expected_signal in assessment.signal_codes


def test_chinese_object_worry_without_disclosure_does_not_switch_owner() -> None:
    assert (
        classify_preflight_risk("朋友有刀让我很担心现在不能保证安全。")
        is None
    )


def test_each_direct_disclosure_creates_a_new_user_subject_event() -> None:
    assessment = classify_preflight_risk("我想死朋友有刀我不能保证安全。")

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "intent" in assessment.signal_codes
    assert "means_access" not in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "I do not really want to live anymore.",
        "I probably want to die.",
        "I am kind of feeling suicidal.",
        "我不太想活了。",
        "我不是很想活了。",
        "我大概有点想死。",
        "我也许有点不想活了。",
    ],
)
def test_inserted_hedges_still_form_direct_disclosure(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"


@pytest.mark.parametrize(
    "message",
    [
        "I do not really want my friend to die.",
        "I probably worry that my friend wants to die.",
        "我不太想让朋友死。",
        "我大概有点担心朋友想死。",
        "朋友告诉我想死。",
    ],
)
def test_inserted_hedges_do_not_turn_third_party_risk_into_user_risk(
    message: str,
) -> None:
    assert classify_preflight_risk(message) is None


@pytest.mark.parametrize(
    "message",
    [
        "我想死。其他计划也想好了，今晚就要去做。",
        "我想死。其他方法已经想好了，今晚就要去做。",
        "我想死。吉他旁边的方法已经想好了，今晚就要去做。",
    ],
)
def test_pronoun_characters_inside_words_do_not_change_owner(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "plan" in assessment.signal_codes
    assert "intent" in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "我想死。他的方法已经想好了，他今晚就要去做。",
        "我想死。我担心他有计划，他今晚就要去做。",
    ],
)
def test_real_chinese_third_person_pronoun_keeps_other_owner(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert "plan" not in assessment.signal_codes
    assert "intent" not in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        "I want to die tonight, but I have not made a plan.",
        "我今天想死，但没有明确计划。",
        "我今天想死，但还没想好方法。",
    ],
)
def test_generalized_plan_denial_spans_are_not_positive(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "concerning"
    assert "plan_denied" in assessment.signal_codes
    assert "plan" not in assessment.signal_codes


@pytest.mark.parametrize(
    "message",
    [
        (
            "I want to die. The knife is within reach as my friend holds "
            "pills in her hand."
        ),
        (
            "I want to die. The knife is within reach alongside my friend "
            "holding pills in her hand."
        ),
        "我想死。刀在手边以及朋友有药在她手里。",
        "我想死。刀在手边还有朋友拿着药在她手里。",
        (
            "My friend holds pills in her hand as I want to die with a knife."
        ),
    ],
)
def test_ownership_does_not_cross_intervening_subjects(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "means_access" in assessment.signal_codes


@pytest.mark.parametrize(
    ("message", "expected_risk"),
    [
        ("I want to die. My friend has a knife in her hand.", "concerning"),
        ("I want to die. My friend has a knife within my reach.", "urgent"),
    ],
)
def test_local_explicit_means_ownership_still_overrides_subject(
    message: str,
    expected_risk: RiskLevel,
) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == expected_risk


@pytest.mark.parametrize(
    "message",
    [
        (
            "I want to die tonight with a plan as my friend discusses her "
            "plan."
        ),
        "我今晚想死并有计划以及朋友在谈她的计划。",
    ],
)
def test_plan_ownership_does_not_cross_intervening_subjects(message: str) -> None:
    assessment = classify_preflight_risk(message)

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "plan" in assessment.signal_codes
    assert "immediate_time" in assessment.signal_codes


@pytest.mark.parametrize(
    ("message", "risk_level", "expected"),
    [
        ("我不想活了。", "concerning", CONCERNING_ZH_SNAPSHOT),
        ("I do not want to live.", "concerning", CONCERNING_EN_SNAPSHOT),
        ("我今晚想死，刀就在手边。", "urgent", URGENT_ZH_SNAPSHOT),
        ("I want to die tonight with means in reach.", "urgent", URGENT_EN_SNAPSHOT),
    ],
)
def test_deterministic_safety_copy_literal_snapshot(
    message: str,
    risk_level: RiskLevel,
    expected: str,
) -> None:
    assert deterministic_safety_response(message, risk_level) == expected


def test_explicit_fiction_quote_negative_control_uses_normal_pipeline() -> None:
    message = (
        "我在分析电影台词‘我不想活了’的叙事作用，这不是我的想法，"
        "也不涉及任何现实中的危险。"
    )
    assert classify_preflight_risk(message) is None

    orchestrator, reflection, review, _memory = build_stub_orchestrator()
    result = asyncio.run(orchestrator.respond(message))

    assert result.response_source == "review"
    assert result.mode == "multi-agent"
    assert result.risk_level == "none"
    assert reflection.calls == 1
    assert review.calls == 1


def test_explicit_friend_quote_is_not_misclassified_as_self_reference() -> None:
    message = "我的朋友说‘我不想活了’，但说的不是我。"

    assert classify_preflight_risk(message) is None


def test_nfkc_normalization_preserves_high_confidence_detection() -> None:
    assessment = classify_preflight_risk(
        "I am thinking about ｓｕｉｃｉｄｅ and have a plan tonight."
    )

    assert assessment is not None
    assert assessment.risk_level == "urgent"
    assert "plan" in assessment.signal_codes
    assert "immediate_time" in assessment.signal_codes


@pytest.mark.parametrize("risk_level", ["concerning", "urgent"])
def test_review_elevated_risk_is_replaced_by_deterministic_envelope(
    risk_level: RiskLevel,
) -> None:
    unsafe_review_response = "让我们继续分析童年，不必联系现实中的人。"
    orchestrator, reflection, review, memory = build_stub_orchestrator(
        risk_level=risk_level,
        reviewed_response=unsafe_review_response,
    )

    result = asyncio.run(orchestrator.respond("最近我觉得自己好像撑不住了。"))

    assert result.mode == "safety-guard"
    assert result.response_source == "review_safety_envelope"
    assert result.risk_level == risk_level
    assert result.support_mode == "support"
    assert result.reflection_draft == reflection.draft
    assert result.review is review.decision
    assert result.memory_candidate is None
    assert unsafe_review_response not in result.response
    assert reflection.calls == 1
    assert review.calls == 1
    assert memory.calls == 0
    assert "现实中可信任的人" in result.response


def test_safe_fallback_does_not_infer_user_risk_or_claim_review() -> None:
    result = safe_fallback_result("我只是想整理一下今天。")

    assert result.mode == "safety-guard"
    assert result.response_source == "safe_fallback"
    assert result.risk_level is None
    assert result.support_mode == "support"
    assert result.reflection_draft is None
    assert result.review is None
    assert result.memory_candidate is None
    assert "不会返回未经审核的内容" in result.response
