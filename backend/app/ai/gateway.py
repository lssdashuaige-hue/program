import json
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol, TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)
PipelineStage = Literal["reflection", "review", "review_verifier"]
TimeoutOrigin = Literal[
    "sdk_timeout",
    "provider_http_408",
    "stage_deadline",
    "case_deadline",
    "unknown",
]
GatewayErrorCode = Literal[
    "provider_authentication",
    "provider_permission",
    "provider_rate_limited",
    "provider_timeout",
    "provider_connection",
    "provider_unavailable",
    "provider_http_error",
    "empty_content",
    "invalid_schema",
    "unexpected_error",
]
SafeFinishReason = Literal[
    "stop",
    "length",
    "content_filter",
    "tool_calls",
    "insufficient_system_resource",
    "other",
]

_SAFE_FINISH_REASONS = {
    "stop",
    "length",
    "content_filter",
    "tool_calls",
    "insufficient_system_resource",
}

_TIMEOUT_ORIGINS = {
    "sdk_timeout",
    "provider_http_408",
    "stage_deadline",
    "case_deadline",
    "unknown",
}
_MAX_DIAGNOSTIC_ATTEMPTS = 8
_MAX_DIAGNOSTIC_DURATION_MS = 3_600_000


@dataclass(frozen=True)
class GatewayDiagnostic:
    code: GatewayErrorCode
    http_status: int | None = None
    finish_reason: SafeFinishReason | None = None
    content_present: bool = False
    request_id_present: bool = False
    timeout_origin: TimeoutOrigin | None = None
    attempt_index: int | None = None
    attempt_limit: int | None = None
    stage_elapsed_ms: int | None = None
    stage_timeout_ms: int | None = None

    def __post_init__(self) -> None:
        if self.http_status is not None and (
            isinstance(self.http_status, bool)
            or not isinstance(self.http_status, int)
            or not 400 <= self.http_status <= 599
        ):
            raise ValueError("Diagnostic HTTP status must be between 400 and 599.")

        if (self.attempt_index is None) != (self.attempt_limit is None):
            raise ValueError(
                "Diagnostic attempt index and limit must be provided together."
            )
        if self.attempt_index is not None and self.attempt_limit is not None:
            if (
                isinstance(self.attempt_index, bool)
                or isinstance(self.attempt_limit, bool)
                or not isinstance(self.attempt_index, int)
                or not isinstance(self.attempt_limit, int)
                or not 1 <= self.attempt_index <= self.attempt_limit
                or self.attempt_limit > _MAX_DIAGNOSTIC_ATTEMPTS
            ):
                raise ValueError("Diagnostic attempt metadata is outside safe bounds.")

        if self.stage_elapsed_ms is not None and (
            isinstance(self.stage_elapsed_ms, bool)
            or not isinstance(self.stage_elapsed_ms, int)
            or not 0 <= self.stage_elapsed_ms <= _MAX_DIAGNOSTIC_DURATION_MS
        ):
            raise ValueError("Diagnostic stage elapsed time is outside safe bounds.")
        if self.stage_timeout_ms is not None and (
            isinstance(self.stage_timeout_ms, bool)
            or not isinstance(self.stage_timeout_ms, int)
            or not 1 <= self.stage_timeout_ms <= _MAX_DIAGNOSTIC_DURATION_MS
        ):
            raise ValueError("Diagnostic stage timeout is outside safe bounds.")

        if self.timeout_origin is not None:
            if self.timeout_origin not in _TIMEOUT_ORIGINS:
                raise ValueError("Diagnostic timeout origin is not allowlisted.")
            if self.code != "provider_timeout":
                raise ValueError(
                    "Diagnostic timeout origin requires a provider timeout code."
                )


class GatewayExecutionError(RuntimeError):
    def __init__(self, diagnostic: GatewayDiagnostic) -> None:
        super().__init__(diagnostic.code)
        self.diagnostic = diagnostic


class ModelOutputError(GatewayExecutionError):
    """Raised when a model call does not produce a usable PAS result."""


def _safe_finish_reason(value: Any) -> SafeFinishReason | None:
    if not isinstance(value, str):
        return None
    return value if value in _SAFE_FINISH_REASONS else "other"


def _strict_json_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Structured model output contains a duplicate key.")
        result[key] = value
    return result


def gateway_error_retryable(code: GatewayErrorCode) -> bool:
    return code in {
        "provider_rate_limited",
        "provider_timeout",
        "provider_connection",
        "provider_unavailable",
        "empty_content",
    }


def _with_attempt(
    diagnostic: GatewayDiagnostic,
    *,
    attempt_index: int | None,
    attempt_limit: int | None,
) -> GatewayDiagnostic:
    if attempt_index is None and attempt_limit is None:
        return diagnostic
    return replace(
        diagnostic,
        attempt_index=attempt_index,
        attempt_limit=attempt_limit,
    )


def diagnostic_from_exception(
    error: Exception,
    *,
    attempt_index: int | None = None,
    attempt_limit: int | None = None,
) -> GatewayDiagnostic:
    if isinstance(error, GatewayExecutionError):
        diagnostic = error.diagnostic
    elif isinstance(error, ValidationError):
        diagnostic = GatewayDiagnostic(
            code="invalid_schema",
            content_present=True,
        )
    elif isinstance(error, APITimeoutError):
        diagnostic = GatewayDiagnostic(
            code="provider_timeout",
            timeout_origin="sdk_timeout",
        )
    elif isinstance(error, TimeoutError):
        diagnostic = GatewayDiagnostic(
            code="provider_timeout",
            timeout_origin="unknown",
        )
    elif isinstance(error, APIConnectionError):
        diagnostic = GatewayDiagnostic(code="provider_connection")
    elif isinstance(error, APIStatusError):
        status = error.status_code if 400 <= error.status_code <= 599 else None
        if status == 401:
            code: GatewayErrorCode = "provider_authentication"
        elif status == 403:
            code = "provider_permission"
        elif status == 408:
            code = "provider_timeout"
        elif status == 429:
            code = "provider_rate_limited"
        elif status is not None and status >= 500:
            code = "provider_unavailable"
        else:
            code = "provider_http_error"
        diagnostic = GatewayDiagnostic(
            code=code,
            http_status=status,
            request_id_present=bool(getattr(error, "request_id", None)),
            timeout_origin=(
                "provider_http_408" if status == 408 else None
            ),
        )
    else:
        diagnostic = GatewayDiagnostic(code="unexpected_error")
    return _with_attempt(
        diagnostic,
        attempt_index=attempt_index,
        attempt_limit=attempt_limit,
    )


def _chat_response_parts(response: Any) -> tuple[str | None, SafeFinishReason | None]:
    choices = getattr(response, "choices", None)
    if not choices:
        return None, None
    choice = choices[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None)
    return (
        content if isinstance(content, str) else None,
        _safe_finish_reason(getattr(choice, "finish_reason", None)),
    )


class LanguageModelGateway(Protocol):
    async def generate_text(
        self,
        *,
        model: str,
        instructions: str,
        user_input: str,
        reasoning_effort: str,
    ) -> str: ...

    async def generate_structured(
        self,
        *,
        model: str,
        instructions: str,
        user_input: str,
        reasoning_effort: str,
        output_type: type[StructuredOutput],
        thinking_enabled: bool = True,
    ) -> StructuredOutput: ...


class OpenAIResponsesGateway:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)

    async def generate_text(
        self,
        *,
        model: str,
        instructions: str,
        user_input: str,
        reasoning_effort: str,
    ) -> str:
        try:
            response = await self._client.responses.create(
                model=model,
                instructions=instructions,
                input=user_input,
                reasoning={"effort": reasoning_effort},
                store=False,
                text={"verbosity": "low"},
            )
        except Exception as error:
            raise GatewayExecutionError(
                diagnostic_from_exception(
                    error,
                    attempt_index=1,
                    attempt_limit=1,
                )
            ) from None

        output_text = getattr(response, "output_text", None)
        result = output_text.strip() if isinstance(output_text, str) else ""
        if not result:
            raise ModelOutputError(
                GatewayDiagnostic(
                    code="empty_content",
                    attempt_index=1,
                    attempt_limit=1,
                )
            )
        return result

    async def generate_structured(
        self,
        *,
        model: str,
        instructions: str,
        user_input: str,
        reasoning_effort: str,
        output_type: type[StructuredOutput],
        thinking_enabled: bool = True,
    ) -> StructuredOutput:
        del thinking_enabled  # DeepSeek-only transport control.
        try:
            response = await self._client.responses.parse(
                model=model,
                instructions=instructions,
                input=user_input,
                reasoning={"effort": reasoning_effort},
                store=False,
                text_format=output_type,
            )
        except Exception as error:
            raise GatewayExecutionError(
                diagnostic_from_exception(
                    error,
                    attempt_index=1,
                    attempt_limit=1,
                )
            ) from None

        result = response.output_parsed
        if result is None:
            output_text = getattr(response, "output_text", None)
            content_present = bool(
                isinstance(output_text, str) and output_text.strip()
            )
            raise ModelOutputError(
                GatewayDiagnostic(
                    code="invalid_schema" if content_present else "empty_content",
                    content_present=content_present,
                    attempt_index=1,
                    attempt_limit=1,
                )
            )
        return result


class DeepSeekChatGateway:
    """DeepSeek Chat Completions adapter for the shared PAS agent contract."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.deepseek.com",
        client: Any | None = None,
    ) -> None:
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=0,
        )

    @staticmethod
    def _deepseek_effort(reasoning_effort: str) -> str:
        return "max" if reasoning_effort in {"max", "xhigh"} else "high"

    async def generate_text(
        self,
        *,
        model: str,
        instructions: str,
        user_input: str,
        reasoning_effort: str,
    ) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_input},
                ],
                # Reflection is an untrusted draft and is never returned before
                # Review. Non-thinking mode keeps that first stage bounded while
                # preserving high-effort thinking for the safety-critical Review.
                extra_body={"thinking": {"type": "disabled"}},
                max_tokens=1600,
            )
        except Exception as error:
            raise GatewayExecutionError(
                diagnostic_from_exception(
                    error,
                    attempt_index=1,
                    attempt_limit=1,
                )
            ) from None

        result, finish_reason = _chat_response_parts(response)
        if not result or not result.strip():
            raise ModelOutputError(
                GatewayDiagnostic(
                    code="empty_content",
                    finish_reason=finish_reason,
                    content_present=False,
                    attempt_index=1,
                    attempt_limit=1,
                )
            )
        return result.strip()

    async def generate_structured(
        self,
        *,
        model: str,
        instructions: str,
        user_input: str,
        reasoning_effort: str,
        output_type: type[StructuredOutput],
        thinking_enabled: bool = True,
    ) -> StructuredOutput:
        schema = json.dumps(output_type.model_json_schema(), ensure_ascii=False)
        structured_instructions = (
            f"{instructions}\n\n"
            "Return one valid JSON object only. It must follow this JSON schema:\n"
            f"{schema}\n"
            "Do not wrap the JSON in Markdown or add text outside it."
        )
        last_error: ModelOutputError | None = None

        attempt_limit = 2
        for attempt in range(attempt_limit):
            attempt_index = attempt + 1
            repair_instruction = (
                ""
                if attempt == 0
                else "\nThe previous output was empty or invalid. Return complete valid JSON."
            )
            try:
                request: dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": structured_instructions + repair_instruction,
                        },
                        {"role": "user", "content": user_input},
                    ],
                    "extra_body": {
                        "thinking": {
                            "type": "enabled" if thinking_enabled else "disabled"
                        }
                    },
                    "response_format": {"type": "json_object"},
                    "max_tokens": 2400,
                }
                if thinking_enabled:
                    request["reasoning_effort"] = self._deepseek_effort(
                        reasoning_effort
                    )
                response = await self._client.chat.completions.create(**request)
            except Exception as error:
                raise GatewayExecutionError(
                    diagnostic_from_exception(
                        error,
                        attempt_index=attempt_index,
                        attempt_limit=attempt_limit,
                    )
                ) from None

            content, finish_reason = _chat_response_parts(response)
            if not content or not content.strip():
                last_error = ModelOutputError(
                    GatewayDiagnostic(
                        code="empty_content",
                        finish_reason=finish_reason,
                        content_present=False,
                        attempt_index=attempt_index,
                        attempt_limit=attempt_limit,
                    )
                )
                continue

            try:
                parsed = json.loads(
                    content,
                    object_pairs_hook=_strict_json_object_pairs,
                )
                return output_type.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError, ValueError):
                last_error = ModelOutputError(
                    GatewayDiagnostic(
                        code="invalid_schema",
                        finish_reason=finish_reason,
                        content_present=True,
                        attempt_index=attempt_index,
                        attempt_limit=attempt_limit,
                    )
                )

        if last_error is None:
            last_error = ModelOutputError(
                GatewayDiagnostic(
                    code="unexpected_error",
                    attempt_index=attempt_limit,
                    attempt_limit=attempt_limit,
                )
            )
        raise last_error from None
