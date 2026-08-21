import asyncio
import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.ai.context import ConversationContextMessage, verification_input
from app.ai.final_verifier_agent import (
    FinalVerifierAgent,
    default_final_verifier_model,
)
from app.ai.models import (
    AgentResult,
    FinalResponseChecks,
    FinalVerificationDecision,
    explicit_named_guess_lower_bound,
    final_response_digest,
)
from app.ai.orchestrator import AgentPipelineError, MultiAgentOrchestrator
from tests.review_fixtures import review_decision, verification_decision


class StaticReflection:
    def __init__(self, draft: str) -> None:
        self.draft = draft

    async def respond(self, _message: str, **_kwargs: object) -> str:
        return self.draft


class StaticReview:
    def __init__(self, candidate: str, *, risk_level: str = "none") -> None:
        self.calls = 0
        self.decision = review_decision(
            draft_disposition="rewritten",
            draft_findings=[
                "crisis_mishandling"
                if risk_level != "none"
                else "pas_principle_violation"
            ],
            final_response=candidate,
            risk_level=risk_level,  # type: ignore[arg-type]
        )

    async def review(self, _message: str, _draft: str, **_kwargs: object):
        self.calls += 1
        return self.decision


class StaticVerifier:
    def __init__(
        self,
        decision: FinalVerificationDecision,
        *,
        delay: float = 0,
    ) -> None:
        self.decision = decision
        self.delay = delay
        self.calls = 0
        self.kwargs: dict[str, object] = {}

    async def verify(
        self,
        user_message: str,
        candidate_response: str,
        **kwargs: object,
    ) -> FinalVerificationDecision:
        self.calls += 1
        self.kwargs = {
            "user_message": user_message,
            "candidate_response": candidate_response,
            **kwargs,
        }
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.decision


class CountingMemory:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, **_kwargs: object):
        self.calls += 1
        raise RuntimeError("Synthetic optional Memory failure.")


def build_pipeline(
    *,
    draft: str,
    review: StaticReview,
    verifier: StaticVerifier,
    memory: CountingMemory | None = None,
    verifier_timeout_seconds: float = 15,
) -> MultiAgentOrchestrator:
    return MultiAgentOrchestrator(
        reflection_agent=StaticReflection(draft),  # type: ignore[arg-type]
        review_agent=review,  # type: ignore[arg-type]
        final_verifier_agent=verifier,  # type: ignore[arg-type]
        memory_agent=memory,  # type: ignore[arg-type]
        verifier_timeout_seconds=verifier_timeout_seconds,
    )


def test_final_verification_contract_accepts_only_coherent_strict_shape() -> None:
    candidate = "候选内容。"
    release = verification_decision(candidate)
    rejection = verification_decision(
        candidate,
        release=False,
        primary_finding="unreported_third_party_fact",
    )

    assert release.gate_action == "release_candidate"
    assert release.primary_finding == "none"
    assert release.named_guess_count == 0
    assert rejection.gate_action == "reject_candidate"
    assert rejection.primary_finding == "unreported_third_party_fact"

    for update in (
        {"gate_action": "release_candidate", "primary_finding": "health_boundary"},
        {"gate_action": "reject_candidate", "primary_finding": "none"},
        {"contract_version": "1"},
        {"target_digest": "A" * 64},
        {"target_digest": "0" * 63},
        {"target_digest": f" {release.target_digest}"},
        {"rationale": " \n\t "},
        {"named_guess_count": "0"},
        {"named_guess_count": -1},
        {"named_guess_count": 13},
        {"extra": "forbidden"},
    ):
        payload = release.model_dump()
        payload.update(update)
        with pytest.raises(ValidationError):
            FinalVerificationDecision.model_validate(payload)


def test_final_verification_requires_an_independent_named_guess_count() -> None:
    candidate = "候选内容。"
    payload = verification_decision(candidate).model_dump()
    payload.pop("named_guess_count")

    with pytest.raises(ValidationError):
        FinalVerificationDecision.model_validate(payload)


def test_digest_and_payload_identify_the_exact_candidate_only() -> None:
    candidate = "同一候选。\n"
    history = (
        ConversationContextMessage(role="user", content="用户历史"),
        ConversationContextMessage(role="assistant", content="AI 历史"),
    )
    payload = json.loads(verification_input("当前原话", candidate, history))
    no_history_payload = json.loads(
        verification_input("当前原话", candidate, ())
    )

    assert set(payload) == {
        "current_user_message",
        "candidate_response",
        "history_present",
        "history_boundary",
        "source_manifest",
        "permitted_source_bases",
        "named_guess_count_boundary",
        "target_digest",
        "conversation_history",
    }
    assert payload["candidate_response"] == candidate
    assert payload["history_present"] is True
    assert "Only the supplied conversation history" in payload["history_boundary"]
    assert no_history_payload["history_present"] is False
    assert "No conversation history was supplied" in no_history_payload["history_boundary"]
    assert payload["target_digest"] == final_response_digest(candidate)
    assert payload["target_digest"] != final_response_digest(candidate.strip())
    assert "Repeating several user-reported states" in payload[
        "named_guess_count_boundary"
    ]
    assert "named_guess_count=0" in payload["named_guess_count_boundary"]
    assert payload["source_manifest"] == [
        "current_user_message",
        "supplied_user_history",
        "supplied_assistant_history_as_ai_output",
    ]
    assert payload["permitted_source_bases"] == [
        "current_user_message",
        "supplied_user_history",
        "supplied_assistant_history_as_ai_output",
        "tentative_inference",
        "general_knowledge",
    ]
    assert "candidate is evidence" not in json.dumps(payload)


def test_verifier_guess_count_schema_excludes_faithful_user_state_repetition() -> None:
    description = FinalVerificationDecision.model_json_schema()["properties"][
        "named_guess_count"
    ]["description"]

    assert "Do not count states faithfully repeated from the user" in description
    assert "Several reported states with no proposed explanation count as zero" in (
        description
    )


def test_lifespan_bounded_route_is_server_context_not_release_proof() -> None:
    candidate = "群体统计不能换算成你的个人寿命。"
    payload = json.loads(
        verification_input(
            "这会让我少活几年？",
            candidate,
            (),
            bounded_response_kind="personal_lifespan_conversion",
        )
    )

    assert payload["bounded_response_kind"] == "personal_lifespan_conversion"
    assert "not model evidence or a release instruction" in payload[
        "bounded_candidate_boundary"
    ]
    assert "group-level methodological statement" in payload[
        "bounded_route_semantics"
    ]
    assert "generic qualified professional role" in payload[
        "bounded_route_semantics"
    ]
    assert "current_user_message and general_knowledge" in payload[
        "bounded_route_semantics"
    ]
    assert payload["target_digest"] == final_response_digest(candidate)


def test_third_party_fact_schema_distinguishes_generic_roles_from_people() -> None:
    schema = FinalResponseChecks.model_json_schema()
    description = schema["properties"]["adds_unreported_third_party_fact"][
        "description"
    ]

    assert "concrete, user-related, or identifiable third person" in description
    assert "group-level methodological limitation" in description
    assert "generic professional role" in description
    assert "all other PAS checks" in description


def test_cross_chat_schema_treats_explicit_access_denial_as_satisfied() -> None:
    schema = FinalResponseChecks.model_json_schema()
    description = schema["properties"]["cross_chat_boundary"]["description"]

    assert "An access denial" in description
    assert "accurate user attribution" in description
    assert "satisfy the boundary" in description
    assert "not violations" in description
    assert "claims unavailable cross-chat material" in description


def test_review_schema_marks_minimal_lexical_repair_as_compliant() -> None:
    schema = FinalResponseChecks.model_json_schema()
    user_fact_description = schema["properties"]["adds_unreported_user_fact"][
        "description"
    ]
    other_pas_description = schema["properties"]["other_pas_requirements_ok"][
        "description"
    ]

    assert "Chinese/pinyin lexical repair is not a new user fact" in user_fact_description
    assert "preserves only the reported states" in user_fact_description
    assert "Do not set this false merely" in other_pas_description
    assert "keeping their relationship and cause unknown" in other_pas_description


def test_mixed_script_surface_hint_is_non_authoritative_and_shared_by_both_gates() -> None:
    from app.ai.context import review_input

    message = "上台前jin张，话也说bu顺"
    candidate = "我先按紧张和说不顺理解，原因还不知道。"
    review_payload = json.loads(review_input(message, candidate, ()))
    verifier_payload = json.loads(verification_input(message, candidate, ()))

    for payload in (review_payload, verifier_payload):
        assert payload["input_surface_hints"] == ["mixed_cjk_latin_token"]
        assert "not proof" in payload["input_surface_hint_boundary"]
        assert "preserves the user's reported states" in payload[
            "input_surface_hint_boundary"
        ]


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("还看不出是因为睡眠、身体状态、压力，还是别的什么。", 3),
        ("It could be sleep, physical state, or stress.", 3),
        ("Causes include sleep, physical state, stress.", 3),
        ("Sleep, physical state, stress, and fatigue could contribute.", 4),
        ("Sleep, physical state, stress, and fatigue may all play a role.", 4),
        ("Sleep, physical state, stress, and fatigue are possible contributors.", 4),
        ("Possible factors are sleep, physical state, stress, and fatigue.", 4),
        ("睡眠、身体状态、压力和疲劳都可能有影响。", 4),
        ("睡眠、身体状态、压力和疲劳都可能是因素。", 4),
        ("可能因素包括睡眠、身体状态、压力和疲劳。", 4),
        ("可能与睡眠或身体状态有关。", 0),
        ("这不是因为睡眠、身体状态、压力。", 0),
        ("Causes include neither sleep, physical state, nor stress.", 0),
        ("Sleep, physical state, stress, and fatigue might not contribute.", 0),
        ("睡眠、身体状态、压力和疲劳都不一定有影响。", 0),
        ("The response mentions sleep, physical state, stress.", 0),
        (
            "The user asked whether sleep, physical state, stress, and fatigue "
            "could contribute; that remains unknown.",
            0,
        ),
        (
            "你问睡眠、身体状态、压力和疲劳是否都可能有影响；目前还不知道。",
            0,
        ),
        (
            "I cannot determine whether you have a psychological or personality "
            "diagnosis, and I will not give you a self-diagnosis checklist.",
            0,
        ),
    ],
)
def test_server_guess_lower_bound_only_covers_unmistakable_three_item_lists(
    candidate: str,
    expected: int,
) -> None:
    assert explicit_named_guess_lower_bound(candidate) == expected


def test_exact_primary_candidate_requires_exact_verifier_release_before_memory() -> None:
    candidate = "经过第一遍 Review 的候选。"
    review = StaticReview(candidate)
    verifier = StaticVerifier(verification_decision(candidate))
    memory = CountingMemory()
    pipeline = build_pipeline(
        draft="原草稿。",
        review=review,
        verifier=verifier,
        memory=memory,
    )

    result = asyncio.run(pipeline.respond("当前用户原话"))

    assert result.response == candidate
    assert result.verification is verifier.decision
    assert verifier.kwargs["candidate_response"] == candidate
    assert memory.calls == 1


@pytest.mark.parametrize(
    ("failure", "expected_contract_failure"),
    [
        ("reject", "verifier_rejected"),
        ("wrong_digest", "verifier_digest_mismatch"),
    ],
)
def test_verifier_rejection_or_digest_mismatch_fails_closed_before_memory(
    failure: str,
    expected_contract_failure: str,
) -> None:
    candidate = "不能绕过第二道门。"
    verification = (
        verification_decision(candidate, release=False)
        if failure == "reject"
        else verification_decision(candidate, target_digest="0" * 64)
    )
    verifier = StaticVerifier(verification)
    memory = CountingMemory()
    pipeline = build_pipeline(
        draft="原草稿。",
        review=StaticReview(candidate),
        verifier=verifier,
        memory=memory,
    )

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(pipeline.respond("当前用户原话"))

    assert caught.value.stage == "review_verifier"
    assert caught.value.reason == "review_contract_violation"
    assert caught.value.contract_failure_code == expected_contract_failure
    assert memory.calls == 0


def test_verifier_digest_mismatch_takes_precedence_over_rejection() -> None:
    candidate = "摘要不匹配时，候选不得被发布。"
    verifier = StaticVerifier(
        verification_decision(candidate, release=False, target_digest="0" * 64)
    )
    memory = CountingMemory()
    pipeline = build_pipeline(
        draft="原草稿。",
        review=StaticReview(candidate),
        verifier=verifier,
        memory=memory,
    )

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(pipeline.respond("当前用户原话"))

    assert caught.value.contract_failure_code == "verifier_digest_mismatch"
    assert memory.calls == 0


@pytest.mark.parametrize(
    ("review_count", "verifier_count"),
    [(3, 0), (0, 3), (2, 3), (3, 2)],
)
def test_either_gate_counting_more_than_two_guesses_fails_closed(
    review_count: int,
    verifier_count: int,
) -> None:
    candidate = "可能是疲劳、睡眠、压力或身体状态。"
    review = StaticReview(candidate)
    review.decision = review_decision(
        draft_disposition="rewritten",
        draft_findings=["pas_principle_violation"],
        final_response=candidate,
        final_checks=review.decision.final_checks.model_copy(
            update={"named_guess_count": review_count}
        ),
    )
    # The ordinary orchestrator blocks an unsafe primary Review before calling
    # the verifier. Exercise the second-door merge only with a release-ready
    # Review, while retaining the >2 primary count cases for the defensive
    # AgentResult test below.
    if review_count > 2:
        with pytest.raises(AgentPipelineError) as caught:
            asyncio.run(
                build_pipeline(
                    draft="原草稿。",
                    review=review,
                    verifier=StaticVerifier(
                        verification_decision(
                            candidate,
                            named_guess_count=verifier_count,
                        )
                    ),
                ).respond("当前用户原话")
            )
        assert caught.value.stage == "review"
        assert caught.value.contract_failure_code == "final_checks_not_release_ready"
        return

    pipeline = build_pipeline(
        draft="原草稿。",
        review=review,
        verifier=StaticVerifier(
            verification_decision(
                candidate,
                named_guess_count=verifier_count,
            )
        ),
    )

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(pipeline.respond("当前用户原话"))

    assert caught.value.stage == "review_verifier"
    assert caught.value.contract_failure_code == "verifier_rejected"
    assert caught.value.verifier_finding == "guess_limit"


def test_two_or_fewer_guesses_from_both_gates_remain_releaseable() -> None:
    candidate = "可能与睡眠或压力有关，具体原因还不知道。"
    review = StaticReview(candidate)
    review.decision = review_decision(
        draft_disposition="rewritten",
        draft_findings=["pas_principle_violation"],
        final_response=candidate,
        final_checks=review.decision.final_checks.model_copy(
            update={"named_guess_count": 2}
        ),
    )
    pipeline = build_pipeline(
        draft="原草稿。",
        review=review,
        verifier=StaticVerifier(
            verification_decision(candidate, named_guess_count=1)
        ),
    )

    result = asyncio.run(pipeline.respond("当前用户原话"))

    assert result.response == candidate


@pytest.mark.parametrize(
    "candidate",
    [
        (
            "只凭这一条，还看不出是因为睡眠、身体状态、压力，"
            "还是别的什么，原因仍未知。"
        ),
        "Causes include sleep, physical state, stress.",
        "Sleep, physical state, stress, and fatigue could contribute.",
        "睡眠、身体状态、压力和疲劳都可能有影响。",
    ],
)
def test_server_explicit_list_lower_bound_blocks_two_model_undercount(
    candidate: str,
) -> None:
    review = StaticReview(candidate)
    verifier = StaticVerifier(
        verification_decision(candidate, named_guess_count=0)
    )
    memory = CountingMemory()
    pipeline = build_pipeline(
        draft="原草稿。",
        review=review,
        verifier=verifier,
        memory=memory,
    )

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(pipeline.respond("脑子转不动。"))

    assert caught.value.stage == "review_verifier"
    assert caught.value.contract_failure_code == "verifier_rejected"
    assert caught.value.verifier_finding == "guess_limit"
    assert memory.calls == 0


def test_agent_result_defensively_rejects_two_model_explicit_list_undercount() -> None:
    candidate = "It could be sleep, physical state, or stress."
    review = review_decision(
        draft_disposition="rewritten",
        draft_findings=["pas_principle_violation"],
        final_response=candidate,
    )

    with pytest.raises(ValidationError):
        AgentResult(
            response=candidate,
            mode="multi-agent",
            support_mode="reflection",
            response_source="review",
            risk_level="none",
            reflection_draft="Original draft.",
            review=review,
            verification=verification_decision(
                candidate,
                named_guess_count=0,
            ),
        )


def test_agent_result_defensively_rejects_a_high_verifier_guess_count() -> None:
    candidate = "可能是疲劳、睡眠、压力或身体状态。"
    review = review_decision(
        draft_disposition="rewritten",
        draft_findings=["pas_principle_violation"],
        final_response=candidate,
    )

    with pytest.raises(ValidationError):
        AgentResult(
            response=candidate,
            mode="multi-agent",
            support_mode="reflection",
            response_source="review",
            risk_level="none",
            reflection_draft="草稿。",
            review=review,
            verification=verification_decision(
                candidate,
                named_guess_count=4,
            ),
        )


def test_missing_verifier_has_a_fixed_safe_contract_failure_code() -> None:
    candidate = "没有第二道门时不得发布。"
    pipeline = MultiAgentOrchestrator(
        reflection_agent=StaticReflection("原草稿。"),  # type: ignore[arg-type]
        review_agent=StaticReview(candidate),  # type: ignore[arg-type]
        final_verifier_agent=None,
    )

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(pipeline.respond("当前用户原话"))

    assert caught.value.stage == "review_verifier"
    assert caught.value.reason == "review_contract_violation"
    assert caught.value.contract_failure_code == "verifier_unavailable"


def test_verifier_timeout_has_own_stage_and_fails_closed() -> None:
    candidate = "超时不能发布。"
    verifier = StaticVerifier(verification_decision(candidate), delay=0.02)
    pipeline = build_pipeline(
        draft="原草稿。",
        review=StaticReview(candidate),
        verifier=verifier,
        verifier_timeout_seconds=0.001,
    )

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(pipeline.respond("当前用户原话"))

    assert caught.value.stage == "review_verifier"
    assert caught.value.diagnostic.timeout_origin == "stage_deadline"
    assert caught.value.diagnostic.stage_timeout_ms == 1


def test_elevated_primary_risk_skips_verifier_and_uses_safety_envelope() -> None:
    candidate = "不得发布的风险候选。"
    review = StaticReview(candidate, risk_level="urgent")
    verifier = StaticVerifier(verification_decision(candidate))
    pipeline = build_pipeline(
        draft="原草稿。",
        review=review,
        verifier=verifier,
    )

    result = asyncio.run(pipeline.respond("普通合成消息"))

    assert result.response_source == "review_safety_envelope"
    assert result.verification is None
    assert verifier.calls == 0


def test_agent_result_defensively_requires_exact_release_provenance() -> None:
    candidate = "最终内容。"
    review = review_decision(
        draft_disposition="rewritten",
        draft_findings=["pas_principle_violation"],
        final_response=candidate,
    )

    for verification in (
        None,
        verification_decision(candidate, release=False),
        verification_decision(candidate, target_digest="0" * 64),
    ):
        with pytest.raises(ValidationError):
            AgentResult(
                response=candidate,
                mode="dual-agent",
                support_mode="reflection",
                response_source="review",
                risk_level="none",
                reflection_draft="草稿。",
                review=review,
                verification=verification,
            )


class CapturingGateway:
    def __init__(self, candidate: str) -> None:
        self.candidate = candidate
        self.kwargs: dict[str, Any] = {}

    async def generate_structured(self, **kwargs: Any) -> FinalVerificationDecision:
        self.kwargs = kwargs
        return verification_decision(self.candidate)


def test_final_verifier_uses_bounded_non_thinking_transport_and_expected_model() -> None:
    candidate = "候选。"
    gateway = CapturingGateway(candidate)
    agent = FinalVerifierAgent(
        gateway=gateway,  # type: ignore[arg-type]
        model="deepseek-v4-flash",
        instructions="Verifier instructions",
        reasoning_effort="high",
    )

    asyncio.run(agent.verify("用户原话", candidate))

    assert gateway.kwargs["thinking_enabled"] is False
    assert gateway.kwargs["model"] == "deepseek-v4-flash"
    assert gateway.kwargs["output_type"] is FinalVerificationDecision
    assert default_final_verifier_model("deepseek-v4-pro") == "deepseek-v4-flash"
    assert default_final_verifier_model("gpt-5.6-terra") == "gpt-5.6-terra"
