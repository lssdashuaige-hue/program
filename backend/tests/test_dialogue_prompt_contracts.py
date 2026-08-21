from app.ai.prompts import load_prompt, reflection_instructions, review_instructions


def normalized(value: str) -> str:
    return " ".join(value.split())


def test_generic_assent_is_not_interpreted_as_resonance_or_endorsement() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    assert (
        "does not authorize any claim that an interpretation fit, resonated, "
        "seemed plausible to the user"
    ) in dialogue
    assert "Do not interpret the assent" in dialogue
    assert "你认可了这个猜测" in dialogue
    assert (
        "Do not say or imply that the assent shows resonance, fit, plausibility"
        in reflection
    )
    assert "Never interpret the assent as evidence about the user" in reflection
    assert "Reject and rewrite any draft that interprets generic assent" in review
    assert 'Do not repair the error by saying that the assent "may have resonated"' in review
    assert "does not support a claim that the hypothesis resonated" in verifier
    assert "reject wording that interprets the assent" in verifier

    for instructions in (reflection_instructions(), review_instructions()):
        loaded = normalized(instructions)
        assert "prior assistant" in loaded
        assert "reson" in loaded
        assert "correct" in loaded


def test_third_party_cause_request_keeps_unseen_psychology_unknown() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))

    assert "does not authorize a story about that person's unseen psychology" in dialogue
    assert "at most two observable interaction patterns" in dialogue
    assert "upbringing, personal history, hidden motive" in dialogue
    assert "good or bad intent" in dialogue
    assert "emotional capacity" in dialogue
    assert "actual reasons" in dialogue and "remain unknown" in dialogue
    assert "even tentatively" in dialogue

    assert (
        "asks you to guess why a parent, family member, or other person"
        in reflection
    )
    assert "do not propose an unseen psychological cause" in reflection
    assert "at most two observable interaction patterns" in reflection
    assert "good or bad intent" in reflection
    assert "actual reasons" in reflection and "remain unknown" in reflection
    assert "even tentatively" in reflection

    assert "does not authorize any hypothesis about that person's unseen psychology" in review
    assert (
        "at most two observable interaction patterns"
        in review
    )
    assert "biography, motive, intent, emotional capacity" in review
    assert "reason and relative causal contributions unknown" in review
    assert "even when introduced as tentative" in review


def test_guess_and_undefined_label_contracts_preserve_evidence_limits() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))

    for loaded in (dialogue, reflection, review):
        assert "inferred or deduced" in loaded
        assert "undefined" in loaded
        assert "supplied history" in loaded
    assert "claim they were previously supplied" in dialogue
    assert "ask exactly one concise question about what they mean" in reflection
    assert "must ask exactly one concise clarification" in review


def test_lifespan_forbids_converting_group_associations_to_individual_years() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    boundary = (
        "Group-level research or statistical associations cannot be converted "
        "into an estimate of an individual's lifespan or years lost"
    )
    assert boundary in dialogue
    assert "no trusted retrieval or source verification" in dialogue
    assert "numeric ranges, disease rankings disguised as estimates" in dialogue

    assert (
        "group-level research or statistical associations cannot be converted "
        "into an individual's lifespan"
    ) in reflection
    assert "give no precise number, range, disease ranking, or citation" in reflection
    assert "variation or modifiable risk pathways" in reflection

    assert (
        "group-level research or statistical associations cannot be converted "
        "into an individual's lifespan"
    ) in review
    assert "reject precise figures, numeric ranges, disease rankings" in review
    assert "without a `bounded_response_kind`" in review
    assert "useful qualitative account of variation or modifiable risk pathways" in review

    assert "deterministic `personal_lifespan_conversion` boundary candidate" in reflection
    assert "names no specific explanation, mechanism, or contributing domain" in reflection
    assert "honest `named_guess_count` is zero" in reflection
    assert 'bounded_response_kind="personal_lifespan_conversion"' in review
    assert "honest `named_guess_count=0`" in review
    assert 'health_boundary="satisfied"' in review
    assert "not a fact about a concrete third person" in review
    assert "generic qualified professional role" in review
    assert "use exactly `current_user_message` and `general_knowledge`" in review
    assert "deterministic `personal_lifespan_conversion` boundary candidate" in verifier
    assert "independently compute `named_guess_count=0`" in verifier
    assert 'health_boundary="satisfied"' in verifier
    assert "not, by themselves, facts about a concrete third person" in verifier
    assert "route tag as release proof" in verifier


def test_persistent_functional_change_requires_a_concrete_medical_path() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    assert "affirmatively name a concrete real-world evaluation path" in dialogue
    assert 'physical causes "need to be ruled out"' in dialogue
    assert "do not select or name specific laboratory tests, specialties" in dialogue
    assert "clinician should decide what evaluation or tests are appropriate" in dialogue
    assert "需要先排除身体层面的原因" in reflection
    assert "do not substitute for saying what the user can do" in reflection
    assert "Do not choose specific tests, specialties" in reflection
    assert "leave the evaluation and test selection to a clinician" in reflection
    assert "reject a draft that only says physical causes should be ruled out" in review
    assert "Do not claim this requirement is met when no action is actually named" in review
    assert "selects specific laboratory tests or specialties" in review
    assert "clinician should choose any evaluation or tests" in review
    assert "leaves evaluation and test selection to a clinician" in verifier
    assert "selects specific laboratory tests or specialties" in verifier


def test_failed_ordinary_cases_have_compact_safe_and_unsafe_semantic_anchors() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    # Undefined labels: one direct clarification, no invented menu of meanings.
    assert "Ask exactly one concise clarification" in dialogue
    assert "do not offer multiple-choice interpretations" in dialogue
    assert "ask exactly one concise question" in reflection
    assert "do not offer possible definitions" in reflection
    assert "Reject multiple-choice interpretations, multiple questions" in review

    # Imported observer descriptor: preserve the user's report without a stereotype.
    assert "say that the user reported or brought it here" in dialogue
    assert "descriptor cannot predict whether this user likes being observed" in dialogue
    assert "Imported descriptor: safe" in review
    assert "cross_chat_boundary=satisfied" in review
    assert "Do not require an access disclaimer" in verifier

    # Neuro language: reject literal personal mechanism while naming broad alternatives.
    assert "cannot be treated as a confirmed personal mechanism" in dialogue
    assert "Choose no more than two alternative domains in any one answer" in dialogue
    assert "Do not enumerate a larger menu" in dialogue
    assert "Sleep, broad physical state, medication effects, and stress" not in dialogue
    assert "does not establish them as this user's personal mechanism" in reflection
    assert "Neuro metaphor: safe" in review
    assert "does not establish an individualized mechanism" in verifier
    assert "include at least one and at most two alternative domains" in dialogue
    assert "must still name at least one alternative domain" in reflection
    assert "must retain at least one such direction" in review
    assert "must also retain at least one alternative domain" in verifier


def test_obvious_low_risk_typo_contract_forbids_invented_state() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    assert "use the surrounding topic and sentence" in dialogue
    assert "Do not turn that repair into new symptoms" in dialogue
    assert "make the smallest plausible repair" in reflection
    assert "any other fact that the user did not report" in reflection
    assert "A hedge does not cure the source error" in reflection
    assert "an obvious low-risk typo treated as a new symptom or material ambiguity" in review
    assert "used to add unreported bodily difficulty, exhaustion, duration" in review
    assert "mark `adds_unreported_user_fact=true`" in review
    assert "An uncertainty marker does not repair an attribution error" in verifier
    assert "named-guess count is zero" in dialogue
    assert "`named_guess_count` is zero" in reflection
    assert "has count zero" in review
    assert "count zero" in verifier
    assert "safe final shape adds no explanation" in review
    assert "safe shape adds no explanation" in verifier


def test_grounded_short_followup_and_minimal_typo_repairs_have_release_anchors() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    for loaded in (dialogue, reflection, review, verifier):
        assert "Chinese/pinyin" in loaded
        assert "states" in loaded
        assert "reason" in loaded

    assert "not a new user fact" in dialogue
    assert "leave the relationship and reason among those states unknown" in dialogue
    assert "A supplied user entry is a legitimate source" in dialogue
    assert "may be compressed as difficulty starting that same action" in reflection
    assert "Do not source it from a similar assistant paraphrase" in reflection
    assert "Do not stop at a bare compression" in reflection
    assert "one focused question tied to the known action" in reflection
    assert "one low-burden concrete next step" in reflection
    assert "never add filler merely to make it longer" in reflection
    assert "Treat supplied user history as a legitimate user-report source" in review
    assert "do not call it promotion" in review
    assert "still needs one useful continuation" in review
    assert "Reject or rewrite empty padding" in review
    assert "Do not reject it merely for making those repairs" in review
    assert "Those lexical repairs are not new user facts" in verifier
    assert "not a catch-all uncertainty flag" in review
    assert "mixed_cjk_latin_token" in review
    assert "non-authoritative `mixed_cjk_latin_token`" in verifier
    assert "Do not reject that grounded compression merely because" in verifier
    assert "A bare compression with no useful continuation is incomplete" in verifier
    assert "Do not accept filler" in verifier
    assert "do not require a choice among unreported stages" in verifier


def test_undefined_labels_keep_current_message_source_separate_from_meaning() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    assert "sourced from the current user message" in dialogue
    assert "That permission covers only the labels" in dialogue
    assert "using `current_user_message` as the source" in reflection
    assert "This is not evidence for any definition" in reflection
    assert "is correctly sourced from `current_user_message`" in review
    assert "does not define the labels" in review
    assert "A source-explicit safe form is" in review
    assert "valid `current_user_message` sourcing" in verifier
    assert "It supplies no definition" in verifier
    assert "Release this source-explicit shape" in verifier


def test_short_followup_and_typo_anchors_keep_unsupported_states_rejected() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    assert "do not add a bodily or attentional state" in dialogue
    assert "fatigue, resistance, or mechanism" in dialogue
    assert "Do not add fatigue, bodily or attentional difficulty" in reflection
    assert "add no body, attention, fatigue, resistance, or mechanism claim" in reflection
    assert "Reject or rewrite additions about the user's body, attention" in review
    assert "Reject or rewrite any added exhaustion, bodily or attentional state" in review
    assert "Still reject added exhaustion, bodily or attentional state" in verifier
    assert "Reject an answer that instead relies on assistant history as evidence" in verifier

    short_variants = (
        ("你已经列好提纲", "这是身体能量不足"),
        ("你清楚怎么做", "你的身体进入冻结状态"),
        ("你知道邮件要写什么", "前面已经确认是害怕被评价"),
    )
    typo_variants = (
        ("我先把‘jin张’", "这说明你的身体能量"),
        ("我先把‘jiao虑’", "这是神经系统过载"),
    )
    for loaded in (reflection, review):
        for safe_variant, unsafe_variant in short_variants + typo_variants:
            assert f'safe — "{safe_variant}' in loaded
            assert f'Unsafe — "{unsafe_variant}' in loaded
        assert "not mandatory scripts" in loaded or "not scripts" in loaded
    for safe_variant, unsafe_variant in short_variants + typo_variants:
        assert f'release — "{safe_variant}' in verifier
        assert f'reject — "{unsafe_variant}' in verifier
    assert "not mandatory scripts" in verifier
    assert "set `promotes_prior_ai_hypothesis=true`" in review
    assert "This rejection is `prior_ai_hypothesis_promotion`" in verifier

    original_case_surfaces = (
        "每次要开始复习就卡住",
        "就是做不动",
        "考前只有压里没动力，脑子也转bu动",
    )
    for loaded in (dialogue, reflection, review, verifier):
        for original_surface in original_case_surfaces:
            assert original_surface not in loaded


def test_explicit_guess_contract_counts_every_named_or_exemplified_cause() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    assert "at most two grounded possibilities in total" in dialogue
    assert "leave the remaining unknown unenumerated" in dialogue
    assert "name at most two possibilities in total" in reflection
    assert "not two main possibilities plus an extra list" in reflection
    assert "without appending further named or exemplified causes" in reflection
    assert "Count every named or exemplified cause" in review
    assert "exceeds the limit and must be rewritten" in review
    assert "must explicitly return control to the user" in dialogue
    assert "must explicitly tell the user they may correct the guess" in reflection
    assert "must visibly invite the user to correct it" in review
    assert "explicitly lets the user correct it or judge whether it fits" in verifier


def test_neuro_mechanism_contract_prefers_direct_answer_without_relaxing_limit() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    assert "normally needs no follow-up" in reflection
    assert "global maximum of one" in reflection
    assert "one safe question would materially help, it remains legal" in review
    assert "must never be relaxed" in review
    assert "A single safe follow-up question does not itself violate" in verifier
    assert "Name no more than two alternative domains in total" in reflection
    assert "Choose the two domains you will actually name before drafting" in reflection
    assert "The two-direction limit is not conditional" in review
    assert "rewrite it down to no more than two" in review
    assert "Independently count every explanation, mechanism" in verifier
    assert "never copy or infer a count from primary Review" in verifier
    assert 'contract_version="2"' in verifier
    assert "keep its source explicit" in dialogue
    assert "make the attribution explicit" in reflection
    assert "explicitly attributed to the current user" in review
    assert "explicitly sourced to the current user" in verifier
    assert "unattributed echo" in dialogue
    assert "unmarked echo" in verifier
    for loaded in (reflection, review, verifier):
        assert "fatigue, sleep, stress, and broad physical state" in loaded or (
            "medication, stress, fatigue" in loaded
        )


def test_review_disposition_contract_cannot_relabel_an_unchanged_safe_draft() -> None:
    review = normalized(load_prompt("review.md"))

    assert "perform a literal disposition consistency check" in review
    assert "do not label it `rewritten` merely because you considered or audited it" in (
        review
    )
    assert "never return the unchanged draft under `rewritten`" in review
    assert "never edit the draft while returning `accepted`" in review
    assert "accept and copy it unless another independent issue" in review


def test_local_discourse_repairs_are_present_in_both_generation_gates() -> None:
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    for loaded in (reflection, review, verifier):
        assert "若不贴近请告诉我" in loaded
        assert "你觉得这个猜测很贴近" in loaded
        assert "不要拖延就医" in loaded
        assert "先去门诊" in loaded
    assert "waiting or observation is enough" in review
    assert "waste of time" in verifier
    assert "前额叶可能只是暂时没电" in reflection
    assert "temporarily out of power" in verifier


def test_named_diagnosis_contract_rejects_traits_packaged_as_possibilities() -> None:
    dialogue = normalized(load_prompt("dialogue-style.md"))
    reflection = normalized(load_prompt("reflection.md"))
    review = normalized(load_prompt("review.md"))

    assert "Do not introduce unreported diagnostic-style traits" in dialogue
    assert "ask only about distress, persistence, and functional impact" in dialogue
    assert "Do not invent an unreported diagnostic trait" in reflection
    assert 'package it as "another possibility"' in reflection
    assert "invents an unreported diagnostic-style trait" in review


def test_single_chat_diagnostic_route_has_positive_and_negative_audit_boundaries() -> None:
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    assert 'bounded_response_kind="single_chat_diagnostic_request"' in review
    assert "does not assert that distress or impairment is already present" in review
    assert "does not claim that distress or impairment is already present" in verifier
    for loaded in (review, verifier):
        assert "is not diagnostic self-screening" in loaded
        assert "qualified mental-health professional" in loaded
        assert "test" in loaded
        assert "medicine" in loaded
        assert "specialist" in loaded
    assert "`general_knowledge`" in review
    assert "general knowledge" in verifier
    assert "not an instruction to rubber-stamp the route" in review
    assert "diagnosis or probability" in review
    assert "does not make that miniature self-screening prompt acceptable" in review
    assert "functional impact without supplying diagnostic traits" in review


def test_unavailable_cross_chat_route_has_exact_positive_audit_boundaries() -> None:
    review = normalized(load_prompt("review.md"))
    verifier = normalized(load_prompt("review-verifier.md"))

    assert 'bounded_response_kind="unavailable_cross_chat_context"' in review
    for loaded in (review, verifier):
        assert "cannot view or read other chats" in loaded
        assert "paste or summarize" in loaded
        assert "explicit denial satisfies the cross-chat boundary" in loaded
        assert "mentioning the other chat only to deny access is not a violation" in loaded
        assert "zero named guesses" in loaded
        assert "zero questions" in loaded
        assert "already" in loaded
