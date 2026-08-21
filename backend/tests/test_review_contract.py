import asyncio
import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.ai.context import (
    ConversationContextMessage,
    permitted_review_source_bases,
    review_input,
)
from app.ai.gateway import GatewayDiagnostic
from app.ai.models import (
    AgentResult,
    FinalResponseChecks,
    REVIEW_FINAL_FINDINGS,
    ReviewDecision,
    VERIFIER_REJECTION_FINDINGS,
    primary_review_final_finding,
    review_disposition_matches_draft,
)
from app.ai.orchestrator import AgentPipelineError, MultiAgentOrchestrator
from app.ai.prompts import load_prompt
from app.ai.review_agent import ReviewAgent
from app.ai.safety import deterministic_safety_response
from tests.review_fixtures import review_decision, safe_final_checks


def checks_with(**updates: object) -> FinalResponseChecks:
    payload = safe_final_checks().model_dump()
    payload.update(updates)
    return FinalResponseChecks.model_validate(payload)


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "stage": "review",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "gateway_error",
            "contract_failure_code": "question_limit_exceeded",
        },
        {
            "stage": "review",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
        },
        {
            "stage": "review",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "candidate_text_as_a_code",
        },
        {
            "stage": "review_verifier",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "question_limit_exceeded",
        },
        {
            "stage": "review",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "verifier_rejected",
        },
        {
            "stage": "review",
            "diagnostic": GatewayDiagnostic(code="provider_timeout"),
            "reason": "review_contract_violation",
            "contract_failure_code": "question_limit_exceeded",
        },
        {
            "stage": "review_verifier",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "verifier_rejected",
        },
        {
            "stage": "review_verifier",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "verifier_rejected",
            "verifier_finding": "none",
        },
        {
            "stage": "review_verifier",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "verifier_rejected",
            "verifier_finding": "raw_verifier_rationale",
        },
        {
            "stage": "review_verifier",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "verifier_digest_mismatch",
            "verifier_finding": "pas_principle_violation",
        },
        {
            "stage": "review",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "final_checks_not_release_ready",
        },
        {
            "stage": "review",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "question_limit_exceeded",
            "review_final_finding": "health_boundary",
        },
        {
            "stage": "review",
            "diagnostic": GatewayDiagnostic(code="invalid_schema"),
            "reason": "review_contract_violation",
            "contract_failure_code": "final_checks_not_release_ready",
            "review_final_finding": "raw_review_rationale",
        },
    ],
)
def test_agent_pipeline_error_rejects_unsafe_contract_metadata(
    kwargs: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        AgentPipelineError(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("finding", sorted(VERIFIER_REJECTION_FINDINGS))
def test_agent_pipeline_error_accepts_allowlisted_rejection_findings(
    finding: str,
) -> None:
    error = AgentPipelineError(
        stage="review_verifier",
        diagnostic=GatewayDiagnostic(code="invalid_schema"),
        reason="review_contract_violation",
        contract_failure_code="verifier_rejected",
        verifier_finding=finding,  # type: ignore[arg-type]
    )

    assert error.verifier_finding == finding


@pytest.mark.parametrize("finding", sorted(REVIEW_FINAL_FINDINGS))
def test_agent_pipeline_error_accepts_allowlisted_review_final_findings(
    finding: str,
) -> None:
    error = AgentPipelineError(
        stage="review",
        diagnostic=GatewayDiagnostic(code="invalid_schema"),
        reason="review_contract_violation",
        contract_failure_code="final_checks_not_release_ready",
        review_final_finding=finding,  # type: ignore[arg-type]
    )

    assert error.review_final_finding == finding


def test_review_v2_accepts_safe_accepted_and_rewritten_decisions() -> None:
    accepted = review_decision(final_response="原样安全草稿。")
    rewritten = review_decision(
        draft_disposition="rewritten",
        draft_findings=["unreported_user_fact"],
        final_response="删除补写事实后的回答。",
    )

    assert accepted.contract_version == "2"
    assert accepted.approved is True
    assert accepted.issues == []
    assert accepted.final_checks.release_ready is True
    assert rewritten.approved is False
    assert rewritten.issues == ["unreported_user_fact"]
    assert "approved" not in accepted.model_dump()
    assert "issues" not in accepted.model_dump()


@pytest.mark.parametrize(
    "payload_update",
    [
        {"draft_disposition": "accepted", "draft_findings": ["diagnosis"]},
        {"draft_disposition": "rewritten", "draft_findings": []},
        {"draft_findings": ["diagnosis", "diagnosis"]},
        {"final_response": "   "},
        {"rationale": "\n\t"},
        {"unknown_review_field": "must fail"},
    ],
)
def test_review_v2_rejects_incoherent_or_extra_top_level_fields(
    payload_update: dict[str, object],
) -> None:
    payload = review_decision(final_response="安全回答。").model_dump()
    payload.update(payload_update)

    with pytest.raises(ValidationError):
        ReviewDecision.model_validate(payload)


@pytest.mark.parametrize(
    "checks_update",
    [
        {"source_bases": ["current_user_message", "current_user_message"]},
        {"source_attribution_ok": "true"},
        {"adds_unreported_user_fact": "false"},
        {"named_guess_count": "2"},
        {"extra_check": False},
    ],
)
def test_final_checks_reject_duplicates_coercion_and_extra_fields(
    checks_update: dict[str, object],
) -> None:
    payload = safe_final_checks().model_dump()
    payload.update(checks_update)

    with pytest.raises(ValidationError):
        FinalResponseChecks.model_validate(payload)


def test_legacy_review_shape_is_not_silently_upgraded() -> None:
    with pytest.raises(ValidationError):
        ReviewDecision.model_validate(
            {
                "approved": True,
                "issues": [],
                "final_response": "旧合同回答。",
                "risk_level": "none",
                "rationale": "Legacy payload.",
            }
        )


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("source_attribution_ok", False),
        ("adds_unreported_user_fact", True),
        ("adds_unreported_third_party_fact", True),
        ("promotes_prior_ai_hypothesis", True),
        ("named_guess_count", 3),
        ("diagnostic_self_screening_present", True),
        ("health_boundary", "violated"),
        ("cross_chat_boundary", "violated"),
        ("other_pas_requirements_ok", False),
    ],
)
def test_release_ready_is_server_computed_from_every_final_check(
    field: str,
    unsafe_value: object,
) -> None:
    assert checks_with(**{field: unsafe_value}).release_ready is False


def test_satisfied_and_not_applicable_boundaries_are_releaseable() -> None:
    assert safe_final_checks().release_ready is True
    assert checks_with(
        health_boundary="satisfied",
        cross_chat_boundary="satisfied",
        named_guess_count=2,
    ).release_ready is True


def test_disposition_comparison_normalizes_only_formatting() -> None:
    accepted = review_decision(final_response="同一段  回答。")
    rewritten = review_decision(
        draft_disposition="rewritten",
        draft_findings=["pas_principle_violation"],
        final_response="已经修正的回答。",
    )

    assert review_disposition_matches_draft(accepted, "  同一段\n回答。 ") is True
    assert review_disposition_matches_draft(rewritten, "原始回答。") is True
    assert review_disposition_matches_draft(accepted, "不同回答。") is False
    assert review_disposition_matches_draft(rewritten, "已经修正的回答。") is False


def test_zero_width_formatting_cannot_fake_a_rewrite() -> None:
    decision = review_decision(
        draft_disposition="rewritten",
        draft_findings=["pas_principle_violation"],
        final_response="原\u200b始回答。",
    )

    assert review_disposition_matches_draft(decision, "原始回答。") is False


def test_review_input_manifest_contains_only_sources_actually_supplied() -> None:
    no_history = json.loads(review_input("当前消息", "草稿", ()))
    mixed_history = json.loads(
        review_input(
            "当前消息",
            "草稿",
            (
                ConversationContextMessage(role="user", content="用户历史"),
                ConversationContextMessage(role="assistant", content="助手历史"),
            ),
        )
    )

    assert no_history["source_manifest"] == ["current_user_message"]
    assert no_history["history_present"] is False
    assert "No conversation history was supplied" in no_history["history_boundary"]
    assert mixed_history["history_present"] is True
    assert "Only the supplied history is available" in mixed_history["history_boundary"]
    assert mixed_history["source_manifest"] == [
        "current_user_message",
        "supplied_user_history",
        "supplied_assistant_history_as_ai_output",
    ]
    assert no_history["permitted_source_bases"] == [
        "current_user_message",
        "tentative_inference",
        "general_knowledge",
    ]
    assert mixed_history["permitted_source_bases"] == list(
        permitted_review_source_bases(
            (
                ConversationContextMessage(role="user", content="用户历史"),
                ConversationContextMessage(role="assistant", content="助手历史"),
            )
        )
    )
    assert "other_chat" not in " ".join(mixed_history["source_manifest"])
    assert "draft is the audit target, not evidence" in no_history[
        "source_manifest_boundary"
    ]
    assert "accepted requires an unchanged final_response" in no_history[
        "review_disposition_boundary"
    ]
    assert "rewritten requires at least one real draft finding" in no_history[
        "review_disposition_boundary"
    ]
    assert "Repeating several user-reported states" in no_history[
        "named_guess_count_boundary"
    ]
    assert "named_guess_count=0" in no_history["named_guess_count_boundary"]


def test_review_schema_exposes_disposition_and_guess_count_boundaries() -> None:
    decision_schema = ReviewDecision.model_json_schema()["properties"]
    checks_schema = FinalResponseChecks.model_json_schema()["properties"]

    assert "accepted only when final_response" in decision_schema[
        "draft_disposition"
    ]["description"]
    assert "auditing a safe draft is not itself a finding" in decision_schema[
        "draft_findings"
    ]["description"]
    assert "Copy the Reflection draft unchanged" in decision_schema[
        "final_response"
    ]["description"]
    assert "Do not count states faithfully repeated" in checks_schema[
        "named_guess_count"
    ]["description"]
    assert "adds no explanation has count zero" in checks_schema[
        "named_guess_count"
    ]["description"]


def test_review_prompt_separates_draft_findings_from_final_checks() -> None:
    prompt = load_prompt("review.md")

    assert "draft_findings` describe only the Reflection draft" in prompt
    assert "`final_checks` describe only `final_response`" in prompt
    assert "draft is the audit target, not evidence" in prompt
    for field in FinalResponseChecks.model_fields:
        assert f"`{field}`" in prompt


class StaticReflection:
    def __init__(self, draft: str) -> None:
        self.draft = draft

    async def respond(self, _message: str, **_kwargs: object) -> str:
        return self.draft


class StaticReview:
    def __init__(self, decision: ReviewDecision) -> None:
        self.decision = decision

    async def review(
        self,
        _message: str,
        _draft: str,
        **_kwargs: object,
    ) -> ReviewDecision:
        return self.decision


class CountingMemory:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, **_kwargs: object) -> None:
        self.calls += 1
        raise AssertionError("A contract failure must not reach Memory.")


def orchestrator_for(
    draft: str,
    decision: ReviewDecision,
) -> tuple[MultiAgentOrchestrator, CountingMemory]:
    memory = CountingMemory()
    return (
        MultiAgentOrchestrator(
            reflection_agent=StaticReflection(draft),  # type: ignore[arg-type]
            review_agent=StaticReview(decision),  # type: ignore[arg-type]
            memory_agent=memory,  # type: ignore[arg-type]
        ),
        memory,
    )


@pytest.mark.parametrize(
    ("draft", "decision"),
    [
        (
            "原草稿。",
            review_decision(final_response="被改动却声称接受。"),
        ),
        (
            "没有变化。",
            review_decision(
                draft_disposition="rewritten",
                draft_findings=["pas_principle_violation"],
                final_response="没有变化。",
            ),
        ),
    ],
)
def test_orchestrator_fails_closed_on_disposition_mismatch(
    draft: str,
    decision: ReviewDecision,
) -> None:
    orchestrator, memory = orchestrator_for(draft, decision)

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(orchestrator.respond("普通合成消息"))

    assert caught.value.stage == "review"
    assert caught.value.reason == "review_contract_violation"
    assert caught.value.contract_failure_code == "draft_disposition_mismatch"
    assert caught.value.diagnostic.code == "invalid_schema"
    assert memory.calls == 0


@pytest.mark.parametrize(
    ("field", "unsafe_value", "expected_finding"),
    [
        ("source_attribution_ok", False, "source_attribution"),
        ("adds_unreported_user_fact", True, "unreported_user_fact"),
        ("adds_unreported_third_party_fact", True, "unreported_third_party_fact"),
        (
            "promotes_prior_ai_hypothesis",
            True,
            "prior_ai_hypothesis_promotion",
        ),
        ("named_guess_count", 3, "guess_limit"),
        (
            "diagnostic_self_screening_present",
            True,
            "diagnostic_self_screening",
        ),
        ("health_boundary", "violated", "health_boundary"),
        ("cross_chat_boundary", "violated", "cross_chat_boundary"),
        ("other_pas_requirements_ok", False, "pas_principle_violation"),
    ],
)
def test_normal_review_requires_every_final_check_before_memory(
    field: str,
    unsafe_value: object,
    expected_finding: str,
) -> None:
    decision = review_decision(
        draft_disposition="rewritten",
        draft_findings=["pas_principle_violation"],
        final_response="候选最终回答。",
        final_checks=checks_with(**{field: unsafe_value}),
    )
    orchestrator, memory = orchestrator_for("原始草稿。", decision)

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(orchestrator.respond("普通合成消息"))

    assert caught.value.reason == "review_contract_violation"
    assert caught.value.contract_failure_code == "final_checks_not_release_ready"
    assert caught.value.review_final_finding == expected_finding
    assert primary_review_final_finding(decision.final_checks) == expected_finding
    assert memory.calls == 0


def test_review_final_finding_uses_fixed_precedence_without_content() -> None:
    checks = checks_with(
        source_attribution_ok=False,
        adds_unreported_user_fact=True,
        health_boundary="violated",
    )

    assert primary_review_final_finding(checks) == "source_attribution"
    assert primary_review_final_finding(safe_final_checks()) is None


def test_orchestrator_rejects_a_source_basis_absent_from_the_manifest() -> None:
    decision = review_decision(
        final_response="原始草稿。",
        final_checks=checks_with(source_bases=["supplied_user_history"]),
    )
    orchestrator, memory = orchestrator_for("原始草稿。", decision)

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(orchestrator.respond("普通合成消息"))

    assert caught.value.reason == "review_contract_violation"
    assert caught.value.contract_failure_code == "source_basis_unavailable"
    assert memory.calls == 0


def test_orchestrator_rejects_multiple_user_facing_questions() -> None:
    decision = review_decision(
        draft_disposition="rewritten",
        draft_findings=["pas_principle_violation"],
        final_response="这是第一个问题？这是第二个问题?",
    )
    orchestrator, memory = orchestrator_for("原始草稿。", decision)

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(orchestrator.respond("普通合成消息"))

    assert caught.value.stage == "review"
    assert caught.value.reason == "review_contract_violation"
    assert caught.value.contract_failure_code == "question_limit_exceeded"
    assert memory.calls == 0


def test_elevated_review_still_uses_deterministic_envelope() -> None:
    message = "普通合成消息"
    decision = review_decision(
        draft_disposition="rewritten",
        draft_findings=["crisis_mishandling"],
        final_response="绝不能公开的 Review final。",
        final_checks=checks_with(other_pas_requirements_ok=False),
        risk_level="urgent",
    )
    orchestrator, memory = orchestrator_for("原始草稿。", decision)

    result = asyncio.run(orchestrator.respond(message))

    assert result.response == deterministic_safety_response(message, "urgent")
    assert "绝不能公开" not in result.response
    assert result.response_source == "review_safety_envelope"
    assert memory.calls == 0


def test_elevated_review_contract_mismatch_cannot_block_the_safety_envelope() -> None:
    message = "普通合成消息"
    decision = review_decision(
        draft_disposition="accepted",
        final_response="与草稿不同且绝不能公开。",
        final_checks=checks_with(
            source_bases=["supplied_user_history"],
            source_attribution_ok=False,
            other_pas_requirements_ok=False,
        ),
        risk_level="urgent",
    )
    orchestrator, memory = orchestrator_for("原始草稿。", decision)

    result = asyncio.run(orchestrator.respond(message))

    assert result.response == deterministic_safety_response(message, "urgent")
    assert "绝不能公开" not in result.response
    assert result.response_source == "review_safety_envelope"
    assert memory.calls == 0


def test_agent_result_defensively_rejects_an_unreleasable_normal_review() -> None:
    decision = review_decision(
        final_response="最终回答。",
        final_checks=checks_with(named_guess_count=3),
    )

    with pytest.raises(ValidationError):
        AgentResult(
            response="最终回答。",
            mode="dual-agent",
            support_mode="reflection",
            response_source="review",
            risk_level="none",
            reflection_draft="最终回答。",
            review=decision,
        )


class WrongTypeGateway:
    async def generate_structured(self, **_kwargs: Any) -> Any:
        return {"contract_version": "2"}


class CapturingReviewGateway:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    async def generate_structured(self, **kwargs: Any) -> ReviewDecision:
        self.kwargs = kwargs
        return review_decision(final_response="草稿")


def test_review_agent_rejects_an_unexpected_gateway_output_type() -> None:
    agent = ReviewAgent(
        gateway=WrongTypeGateway(),  # type: ignore[arg-type]
        model="synthetic-model",
        instructions="synthetic instructions",
        reasoning_effort="medium",
    )

    with pytest.raises(TypeError):
        asyncio.run(agent.review("用户消息", "草稿"))


def test_review_agent_defaults_to_bounded_non_thinking_transport() -> None:
    gateway = CapturingReviewGateway()
    agent = ReviewAgent(
        gateway=gateway,  # type: ignore[arg-type]
        model="synthetic-model",
        instructions="synthetic instructions",
        reasoning_effort="high",
    )

    asyncio.run(agent.review("用户消息", "草稿"))

    assert gateway.kwargs["thinking_enabled"] is False
