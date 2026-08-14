import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import BadRequestError
from pydantic import ValidationError

from app.ai.gateway import DeepSeekChatGateway
from app.ai.orchestrator import MultiAgentOrchestrator
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.evals.models import EvalCaseSpec, EvalPipelineFailureReport
from app.evals.runner import EvalRunner


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

    assert failure.model_dump(exclude_none=True) == {
        "stage": "reflection",
        "code": "provider_http_error",
        "retryable": False,
        "content_present": False,
        "request_id_present": True,
        "http_status": 400,
    }
    _assert_safe_report(report)


def test_reflection_empty_content_reports_safe_finish_reason() -> None:
    report, failure = _run(
        [{"content": None, "finish_reason": "length"}]
    )

    assert failure.model_dump(exclude_none=True) == {
        "stage": "reflection",
        "code": "empty_content",
        "retryable": True,
        "content_present": False,
        "request_id_present": False,
        "finish_reason": "length",
    }
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

    assert failure.model_dump(exclude_none=True) == {
        "stage": "review",
        "code": "invalid_schema",
        "retryable": False,
        "content_present": True,
        "request_id_present": False,
        "finish_reason": "stop",
    }
    serialized = report.model_dump_json()
    assert "not-a-boolean" not in serialized
    assert "validation" not in failure.model_dump_json()
    _assert_safe_report(report)


def test_pipeline_diagnostic_rejects_non_allowlisted_fields() -> None:
    with pytest.raises(ValidationError):
        EvalPipelineFailureReport.model_validate(
            {
                "stage": "review",
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

    assert failure.model_dump(exclude_none=True) == {
        "stage": "reflection",
        "code": "provider_timeout",
        "retryable": True,
        "content_present": False,
        "request_id_present": False,
    }
    _assert_safe_report(report)


def test_hanging_review_reports_stage_aware_timeout() -> None:
    report, failure = _run(
        [
            {"content": "Draft that must never be returned."},
            {"hang": True},
        ],
        case_timeout_seconds=0.01,
        expected_error="timeout",
    )

    assert failure.model_dump(exclude_none=True) == {
        "stage": "review",
        "code": "provider_timeout",
        "retryable": True,
        "content_present": False,
        "request_id_present": False,
    }
    review_gate = next(
        assertion
        for assertion in report.cases[0].hard_assertions
        if assertion.rule == "review_unavailable_fails_closed"
    )
    assert review_gate.applicable is True
    assert review_gate.passed is True
    _assert_safe_report(report)
