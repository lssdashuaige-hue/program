import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)
PipelineStage = Literal["reflection", "review"]
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


@dataclass(frozen=True)
class GatewayDiagnostic:
    code: GatewayErrorCode
    http_status: int | None = None
    finish_reason: SafeFinishReason | None = None
    content_present: bool = False
    request_id_present: bool = False


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


def gateway_error_retryable(code: GatewayErrorCode) -> bool:
    return code in {
        "provider_rate_limited",
        "provider_timeout",
        "provider_connection",
        "provider_unavailable",
        "empty_content",
    }


def diagnostic_from_exception(error: Exception) -> GatewayDiagnostic:
    if isinstance(error, GatewayExecutionError):
        return error.diagnostic
    if isinstance(error, ValidationError):
        return GatewayDiagnostic(
            code="invalid_schema",
            content_present=True,
        )
    if isinstance(error, (APITimeoutError, TimeoutError)):
        return GatewayDiagnostic(code="provider_timeout")
    if isinstance(error, APIConnectionError):
        return GatewayDiagnostic(code="provider_connection")
    if isinstance(error, APIStatusError):
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
        return GatewayDiagnostic(
            code=code,
            http_status=status,
            request_id_present=bool(getattr(error, "request_id", None)),
        )
    return GatewayDiagnostic(code="unexpected_error")


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
            raise GatewayExecutionError(diagnostic_from_exception(error)) from None

        output_text = getattr(response, "output_text", None)
        result = output_text.strip() if isinstance(output_text, str) else ""
        if not result:
            raise ModelOutputError(GatewayDiagnostic(code="empty_content"))
        return result

    async def generate_structured(
        self,
        *,
        model: str,
        instructions: str,
        user_input: str,
        reasoning_effort: str,
        output_type: type[StructuredOutput],
    ) -> StructuredOutput:
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
            raise GatewayExecutionError(diagnostic_from_exception(error)) from None

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
            raise GatewayExecutionError(diagnostic_from_exception(error)) from None

        result, finish_reason = _chat_response_parts(response)
        if not result or not result.strip():
            raise ModelOutputError(
                GatewayDiagnostic(
                    code="empty_content",
                    finish_reason=finish_reason,
                    content_present=False,
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
    ) -> StructuredOutput:
        schema = json.dumps(output_type.model_json_schema(), ensure_ascii=False)
        structured_instructions = (
            f"{instructions}\n\n"
            "Return one valid JSON object only. It must follow this JSON schema:\n"
            f"{schema}\n"
            "Do not wrap the JSON in Markdown or add text outside it."
        )
        last_error: ModelOutputError | None = None

        for attempt in range(2):
            repair_instruction = (
                ""
                if attempt == 0
                else "\nThe previous output was empty or invalid. Return complete valid JSON."
            )
            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": structured_instructions + repair_instruction,
                        },
                        {"role": "user", "content": user_input},
                    ],
                    reasoning_effort=self._deepseek_effort(reasoning_effort),
                    extra_body={"thinking": {"type": "enabled"}},
                    response_format={"type": "json_object"},
                    max_tokens=2400,
                )
            except Exception as error:
                raise GatewayExecutionError(
                    diagnostic_from_exception(error)
                ) from None

            content, finish_reason = _chat_response_parts(response)
            if not content or not content.strip():
                last_error = ModelOutputError(
                    GatewayDiagnostic(
                        code="empty_content",
                        finish_reason=finish_reason,
                        content_present=False,
                    )
                )
                continue

            try:
                return output_type.model_validate_json(content)
            except ValidationError:
                last_error = ModelOutputError(
                    GatewayDiagnostic(
                        code="invalid_schema",
                        finish_reason=finish_reason,
                        content_present=True,
                    )
                )

        if last_error is None:
            last_error = ModelOutputError(
                GatewayDiagnostic(code="unexpected_error")
            )
        raise last_error from None
