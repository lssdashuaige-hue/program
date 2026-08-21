import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIStatusError, APITimeoutError

import app.ai.gateway as gateway_module
from app.ai.gateway import (
    DeepSeekChatGateway,
    GatewayDiagnostic,
    GatewayExecutionError,
    ModelOutputError,
    OpenAIResponsesGateway,
    diagnostic_from_exception,
)
from app.ai.models import ReviewDecision


class FakeCompletions:
    def __init__(self, steps: list[str | None | Exception]) -> None:
        self._steps = iter(steps)

    async def create(self, **_: Any) -> SimpleNamespace:
        step = next(self._steps)
        if isinstance(step, Exception):
            raise step
        message = SimpleNamespace(content=step)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice])


class FakeClient:
    def __init__(self, steps: list[str | None | Exception]) -> None:
        completions = FakeCompletions(steps)
        self.chat = SimpleNamespace(completions=completions)


class FakeResponses:
    async def create(self, **_: Any) -> SimpleNamespace:
        return SimpleNamespace(output_text="")

    async def parse(self, **_: Any) -> SimpleNamespace:
        return SimpleNamespace(
            output_parsed=None,
            output_text="invalid structured output",
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def sdk_timeout() -> APITimeoutError:
    return APITimeoutError(
        request=httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    )


def http_408_with_sensitive_details() -> APIStatusError:
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/chat/completions",
    )
    response = httpx.Response(
        408,
        request=request,
        headers={"x-request-id": "raw-upstream-request-id"},
    )
    return APIStatusError(
        "sk-sensitive-timeout-message-1234567890",
        response=response,
        body={"error": {"message": "sensitive upstream timeout body"}},
    )


def test_timeout_sources_are_mapped_without_exception_text() -> None:
    sdk = diagnostic_from_exception(
        sdk_timeout(),
        attempt_index=1,
        attempt_limit=1,
    )
    provider = diagnostic_from_exception(
        http_408_with_sensitive_details(),
        attempt_index=1,
        attempt_limit=1,
    )
    local_unknown = diagnostic_from_exception(
        TimeoutError("sensitive local timeout detail"),
        attempt_index=1,
        attempt_limit=1,
    )

    assert sdk == GatewayDiagnostic(
        code="provider_timeout",
        timeout_origin="sdk_timeout",
        attempt_index=1,
        attempt_limit=1,
    )
    assert provider == GatewayDiagnostic(
        code="provider_timeout",
        http_status=408,
        request_id_present=True,
        timeout_origin="provider_http_408",
        attempt_index=1,
        attempt_limit=1,
    )
    assert local_unknown == GatewayDiagnostic(
        code="provider_timeout",
        timeout_origin="unknown",
        attempt_index=1,
        attempt_limit=1,
    )

    serialized = repr((sdk, provider, local_unknown))
    assert "sk-sensitive" not in serialized
    assert "sensitive upstream" not in serialized
    assert "raw-upstream-request-id" not in serialized
    assert "sensitive local" not in serialized
    assert str(GatewayExecutionError(provider)) == "provider_timeout"


def test_deepseek_text_failure_reports_single_safe_attempt() -> None:
    gateway = DeepSeekChatGateway("test-key", client=FakeClient([None]))

    with pytest.raises(ModelOutputError) as caught:
        asyncio.run(
            gateway.generate_text(
                model="test-model",
                instructions="synthetic instructions",
                user_input="synthetic input",
                reasoning_effort="high",
            )
        )

    assert caught.value.diagnostic == GatewayDiagnostic(
        code="empty_content",
        finish_reason="stop",
        attempt_index=1,
        attempt_limit=1,
    )


def test_openai_failures_report_single_safe_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gateway_module,
        "AsyncOpenAI",
        lambda **_: FakeOpenAIClient(),
    )
    gateway = OpenAIResponsesGateway("test-key")

    with pytest.raises(ModelOutputError) as text_error:
        asyncio.run(
            gateway.generate_text(
                model="test-model",
                instructions="synthetic instructions",
                user_input="synthetic input",
                reasoning_effort="medium",
            )
        )
    with pytest.raises(ModelOutputError) as structured_error:
        asyncio.run(
            gateway.generate_structured(
                model="test-model",
                instructions="synthetic instructions",
                user_input="synthetic input",
                reasoning_effort="medium",
                output_type=ReviewDecision,
            )
        )

    assert text_error.value.diagnostic == GatewayDiagnostic(
        code="empty_content",
        attempt_index=1,
        attempt_limit=1,
    )
    assert structured_error.value.diagnostic == GatewayDiagnostic(
        code="invalid_schema",
        content_present=True,
        attempt_index=1,
        attempt_limit=1,
    )


def test_deepseek_second_structured_attempt_is_visible_on_timeout() -> None:
    gateway = DeepSeekChatGateway(
        "test-key",
        client=FakeClient(["not valid json", sdk_timeout()]),
    )

    with pytest.raises(GatewayExecutionError) as caught:
        asyncio.run(
            gateway.generate_structured(
                model="test-model",
                instructions="synthetic review instructions",
                user_input="synthetic review input",
                reasoning_effort="high",
                output_type=ReviewDecision,
            )
        )

    assert caught.value.diagnostic == GatewayDiagnostic(
        code="provider_timeout",
        timeout_origin="sdk_timeout",
        attempt_index=2,
        attempt_limit=2,
    )


def test_deepseek_final_invalid_schema_reports_second_attempt() -> None:
    gateway = DeepSeekChatGateway(
        "test-key",
        client=FakeClient(["not valid json", "{}"]),
    )

    with pytest.raises(ModelOutputError) as caught:
        asyncio.run(
            gateway.generate_structured(
                model="test-model",
                instructions="synthetic review instructions",
                user_input="synthetic review input",
                reasoning_effort="high",
                output_type=ReviewDecision,
            )
        )

    assert caught.value.diagnostic == GatewayDiagnostic(
        code="invalid_schema",
        finish_reason="stop",
        content_present=True,
        attempt_index=2,
        attempt_limit=2,
    )


@pytest.mark.parametrize(
    "values",
    [
        {"http_status": 399},
        {"http_status": 600},
        {"http_status": True},
        {"attempt_index": 1},
        {"attempt_limit": 1},
        {"attempt_index": 0, "attempt_limit": 1},
        {"attempt_index": 2, "attempt_limit": 1},
        {"attempt_index": 1, "attempt_limit": 9},
        {"attempt_index": True, "attempt_limit": 1},
        {"stage_elapsed_ms": -1},
        {"stage_elapsed_ms": 3_600_001},
        {"stage_timeout_ms": 0},
        {"stage_timeout_ms": 3_600_001},
    ],
)
def test_diagnostic_integer_fields_reject_unsafe_bounds(
    values: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        GatewayDiagnostic(code="provider_timeout", **values)


def test_timeout_origin_is_runtime_allowlisted() -> None:
    with pytest.raises(ValueError):
        GatewayDiagnostic(
            code="provider_timeout",
            timeout_origin="raw-timeout-detail",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        GatewayDiagnostic(
            code="provider_connection",
            timeout_origin="sdk_timeout",
        )


def test_diagnostic_accepts_maximum_safe_integer_bounds() -> None:
    diagnostic = GatewayDiagnostic(
        code="provider_timeout",
        http_status=599,
        attempt_index=8,
        attempt_limit=8,
        stage_elapsed_ms=3_600_000,
        stage_timeout_ms=3_600_000,
    )

    assert diagnostic.attempt_index == 8
    assert diagnostic.stage_elapsed_ms == 3_600_000
