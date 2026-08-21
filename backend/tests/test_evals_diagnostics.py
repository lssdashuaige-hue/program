import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import BadRequestError
from pydantic import ValidationError

from app.ai.gateway import DeepSeekChatGateway
from app.ai.models import FinalVerificationDecision, final_response_digest
from app.ai.orchestrator import MultiAgentOrchestrator
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.evals.models import EvalCaseSpec, EvalPipelineFailureReport
from app.evals.runner import EvalRunner
from tests.review_fixtures import review_decision


class DiagnosticCompletions:
    def __init__(self, steps: list[dict[str, Any]]) -> None:
        self._steps = iter(steps)

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        step = next(self._steps)
        if step.get("hang"):
            await asyncio.Event().wait()
            raise AssertionError("unreachable")
        error = step.get("error")
        if error is not None:
            raise error
        message = SimpleNamespace(content=step.get("content"))
        choice = SimpleNamespace(
            message=message,
            finish_reason=step.get("finish_reason"),
        )
        return SimpleNamespace(choices=[choice])


class DiagnosticClient:
    def __init__(self, steps: list[dict[str, Any]]) -> None:
        completions = DiagnosticCompletions(steps)
        self.chat = SimpleNamespace(completions=completions)


def _provider_error() -> BadRequestError:
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    response = httpx.Response(
        400,
        request=request,
        headers={"x-request-id": "upstream-id-must-not-be-reported"},
    )
    return BadRequestError(
        "sk-sensitive-provider-message-1234567890",
        response=response,
        body={"error": {"message": "sensitive upstream body"}},
    )


def _review_json(candidate: str) -> str:
    return review_decision(final_response=candidate).model_dump_json()


def _verification_json(candidate: str) -> str:
    return FinalVerificationDecision(
        contract_version="2",
        target_digest=final_response_digest(candidate),
        gate_action="release_candidate",
        primary_finding="none",
        named_guess_count=0,
        rationale="Synthetic exact-candidate release fixture.",
    ).model_dump_json()


def _orchestrator(steps: list[dict[str, Any]]) -> MultiAgentOrchestrator:
    gateway = DeepSeekChatGateway(
        "sk-fake-test-key-1234567890",
        client=DiagnosticClient(steps),
    )
    return MultiAgentOrchestrator(
        reflection_agent=ReflectionAgent(
            gateway=gateway,
            model="fake-reflection-model",
            instructions="synthetic reflection instructions",
            reasoning_effort="medium",
        ),
        review_agent=ReviewAgent(
            gateway=gateway,
            model="fake-review-model",
            instructions="synthetic review instructions",
            reasoning_effort="medium",
        ),
    )


def _run(
    steps: list[dict[str, Any]],
    *,
    case_timeout_seconds: float = 30.0,
    expected_error: str = "pipeline_failed_closed",
):
    case = EvalCaseSpec(
        case_id="diagnostic",
        category="pipeline",
        input="Synthetic pipeline diagnostic case.",
    )
    report = asyncio.run(
        EvalRunner(
            _orchestrator(steps),
            case_timeout_seconds=case_timeout_seconds,
        ).run([case], suite=None)
    )
    result = report.cases[0]
    assert result.error == expected_error
    assert result.passed is False
    assert result.review_completed is False
    assert result.reflection_draft is None
    assert result.final_response is None
    assert result.pipeline_failure is not None
    return report, result.pipeline_failure


def _assert_safe_report(report: Any) -> None:
    serialized = report.model_dump_json()
    assert "sk-sensitive" not in serialized
    assert "sensitive upstream body" not in serialized
    assert "upstream-id-must-not-be-reported" not in serialized
    assert "fake-reflection-model" not in serialized
    assert "fake-review-model" not in serialized
    assert "synthetic review instructions" not in serialized


def test_reflection_http_error_has_allowlisted_diagnostic() -> None:
    report, failure = _run([{"error": _provider_error()}])

    assert failure.stage == "reflection"
    assert failure.reason == "gateway_error"
    assert failure.code == "provider_http_error"
    assert failure.retryable is False
    assert failure.content_present is False
    assert failure.request_id_present is True
    assert failure.http_status == 400
    assert (failure.attempt_index, failure.attempt_limit) == (1, 1)
    assert failure.stage_elapsed_ms is not None
    assert failure.stage_timeout_ms == 12_000
    _assert_safe_report(report)


def test_reflection_empty_content_reports_safe_finish_reason() -> None:
    report, failure = _run(
        [{"content": None, "finish_reason": "length"}]
    )

    assert failure.stage == "reflection"
    assert failure.reason == "gateway_error"
    assert failure.code == "empty_content"
    assert failure.retryable is True
    assert failure.content_present is False
    assert failure.request_id_present is False
    assert failure.finish_reason == "length"
    assert (failure.attempt_index, failure.attempt_limit) == (1, 1)
    assert failure.stage_elapsed_ms is not None
    assert failure.stage_timeout_ms == 12_000
    _assert_safe_report(report)


def test_review_http_error_is_distinguished_from_reflection() -> None:
    report, failure = _run(
        [
            {"content": "Reviewed only if the next stage succeeds."},
            {"error": _provider_error()},
        ]
    )

    assert failure.stage == "review"
    assert failure.code == "provider_http_error"
    assert failure.http_status == 400
    assert failure.request_id_present is True
    _assert_safe_report(report)


def test_review_empty_json_content_fails_closed() -> None:
    report, failure = _run(
        [
            {"content": "Draft that must never be returned."},
            {"content": None, "finish_reason": "length"},
            {"content": None, "finish_reason": "content_filter"},
        ]
    )

    assert failure.stage == "review"
    assert failure.code == "empty_content"
    assert failure.retryable is True
    assert failure.content_present is False
    assert failure.finish_reason == "content_filter"
    _assert_safe_report(report)


def test_review_schema_validation_has_no_validation_details() -> None:
    report, failure = _run(
        [
            {"content": "Draft that must never be returned."},
            {"content": '{"approved":"not-a-boolean"}'},
            {"content": "{}", "finish_reason": "stop"},
        ]
    )

    assert failure.stage == "review"
    assert failure.reason == "gateway_error"
    assert failure.code == "invalid_schema"
    assert failure.retryable is False
    assert failure.content_present is True
    assert failure.request_id_present is False
    assert failure.finish_reason == "stop"
    assert (failure.attempt_index, failure.attempt_limit) == (2, 2)
    assert failure.stage_elapsed_ms is not None
    assert failure.stage_timeout_ms == 15_000
    serialized = report.model_dump_json()
    assert "not-a-boolean" not in serialized
    assert "validation" not in failure.model_dump_json()
    _assert_safe_report(report)


def test_pipeline_diagnostic_rejects_non_allowlisted_fields() -> None:
    with pytest.raises(ValidationError):
        EvalPipelineFailureReport.model_validate(
            {
                "stage": "review_verifier",
                "reason": "gateway_error",
                "code": "invalid_schema",
                "retryable": False,
                "content_present": True,
                "request_id_present": False,
                "raw_error": "must never be accepted",
            }
        )


def test_hanging_reflection_reports_stage_aware_timeout() -> None:
    report, failure = _run(
        [{"hang": True}],
        case_timeout_seconds=0.01,
        expected_error="timeout",
    )

    assert failure.stage == "reflection"
    assert failure.reason == "gateway_error"
    assert failure.code == "provider_timeout"
    assert failure.retryable is True
    assert failure.content_present is False
    assert failure.request_id_present is False
    assert failure.timeout_origin == "case_deadline"
    assert failure.stage_elapsed_ms is not None
    assert failure.stage_timeout_ms == 12_000
    _assert_safe_report(report)


def test_hanging_review_reports_stage_aware_timeout() -> None:
    report, failure = _run(
        [
            {"content": "Draft that must never be returned."},
            {"hang": True},
        ],
        case_timeout_seconds=0.05,
        expected_error="timeout",
    )

    assert failure.stage == "review"
    assert failure.reason == "gateway_error"
    assert failure.code == "provider_timeout"
    assert failure.retryable is True
    assert failure.content_present is False
    assert failure.request_id_present is False
    assert failure.timeout_origin == "case_deadline"
    assert failure.stage_elapsed_ms is not None
    assert failure.stage_timeout_ms == 15_000
    review_gate = next(
        assertion
        for assertion in report.cases[0].hard_assertions
        if assertion.rule == "review_unavailable_fails_closed"
    )
    assert review_gate.applicable is True
    assert review_gate.passed is True
    _assert_safe_report(report)


def test_final_verifier_http_error_is_distinguished_from_primary_review() -> None:
    candidate = "Candidate that must not be returned if verification fails."
    report, failure = _run(
        [
            {"content": candidate},
            {"content": _review_json(candidate)},
            {"error": _provider_error()},
        ]
    )

    assert failure.stage == "review_verifier"
    assert failure.reason == "gateway_error"
    assert failure.code == "provider_http_error"
    assert failure.http_status == 400
    assert failure.request_id_present is True
    assert failure.stage_timeout_ms == 15_000
    assert failure.verifier_finding is None
    assert report.pass_count == 0
    _assert_safe_report(report)


def test_verifier_rejection_reports_only_fixed_safe_enums() -> None:
    candidate = "Private verifier candidate must never enter failure telemetry."
    verifier_rationale = "Private verifier rationale must remain internal."
    rejection = FinalVerificationDecision(
        contract_version="2",
        target_digest=final_response_digest(candidate),
        gate_action="reject_candidate",
        primary_finding="pas_principle_violation",
        named_guess_count=0,
        rationale=verifier_rationale,
    )
    report, failure = _run(
        [
            {"content": candidate},
            {"content": _review_json(candidate)},
            {"content": rejection.model_dump_json()},
        ]
    )

    assert failure.stage == "review_verifier"
    assert failure.reason == "review_contract_violation"
    assert failure.code == "invalid_schema"
    assert failure.contract_failure_code == "verifier_rejected"
    assert failure.verifier_finding == "pas_principle_violation"
    serialized = report.model_dump_json()
    assert candidate not in serialized
    assert verifier_rationale not in serialized
    assert final_response_digest(candidate) not in serialized
    assert '"verifier_finding":"pas_principle_violation"' in serialized
    _assert_safe_report(report)


def test_review_final_check_rejection_reports_only_one_fixed_safe_enum() -> None:
    candidate = "Private Review candidate must never enter failure telemetry."
    review_rationale = "Private Review rationale must remain internal."
    decision = review_decision(
        final_response=candidate,
        rationale=review_rationale,
    )
    decision = decision.model_copy(
        update={
            "final_checks": decision.final_checks.model_copy(
                update={"diagnostic_self_screening_present": True}
            )
        }
    )
    report, failure = _run(
        [
            {"content": candidate},
            {"content": decision.model_dump_json()},
        ]
    )

    assert failure.stage == "review"
    assert failure.reason == "review_contract_violation"
    assert failure.code == "invalid_schema"
    assert failure.contract_failure_code == "final_checks_not_release_ready"
    assert failure.review_final_finding == "diagnostic_self_screening"
    assert failure.verifier_finding is None
    serialized = report.model_dump_json()
    assert candidate not in serialized
    assert review_rationale not in serialized
    assert final_response_digest(candidate) not in serialized
    assert '"review_final_finding":"diagnostic_self_screening"' in serialized
    assert "rationale" not in serialized
    _assert_safe_report(report)


def test_server_side_guess_limit_rejection_keeps_candidate_and_count_private() -> None:
    candidate = "可能是疲劳、睡眠、压力或身体状态。"
    verifier_rationale = "Independent verifier counted four named directions."
    inconsistent_release = FinalVerificationDecision(
        contract_version="2",
        target_digest=final_response_digest(candidate),
        gate_action="release_candidate",
        primary_finding="none",
        named_guess_count=4,
        rationale=verifier_rationale,
    )
    report, failure = _run(
        [
            {"content": candidate},
            {"content": _review_json(candidate)},
            {"content": inconsistent_release.model_dump_json()},
        ]
    )

    assert failure.stage == "review_verifier"
    assert failure.contract_failure_code == "verifier_rejected"
    assert failure.verifier_finding == "guess_limit"
    serialized = report.model_dump_json()
    assert candidate not in serialized
    assert verifier_rationale not in serialized
    assert "named_guess_count" not in serialized
    _assert_safe_report(report)


def test_hanging_final_verifier_reports_its_own_stage_timeout() -> None:
    candidate = "Candidate that must remain private while verifier hangs."
    report, failure = _run(
        [
            {"content": candidate},
            {"content": _review_json(candidate)},
            {"hang": True},
        ],
        case_timeout_seconds=0.05,
        expected_error="timeout",
    )

    assert failure.stage == "review_verifier"
    assert failure.code == "provider_timeout"
    assert failure.timeout_origin == "case_deadline"
    assert failure.stage_timeout_ms == 15_000
    assert failure.verifier_finding is None
    assert report.cases[0].review_completed is False
    assert report.cases[0].final_response is None
    _assert_safe_report(report)
