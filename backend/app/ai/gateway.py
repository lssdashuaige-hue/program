import json
from typing import Any, Protocol, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class ModelOutputError(RuntimeError):
    """Raised when a model call does not produce a usable PAS result."""


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
        response = await self._client.responses.create(
            model=model,
            instructions=instructions,
            input=user_input,
            reasoning={"effort": reasoning_effort},
            store=False,
            text={"verbosity": "low"},
        )
        result = response.output_text.strip()
        if not result:
            raise ModelOutputError("Reflection Agent returned an empty response.")
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
        response = await self._client.responses.parse(
            model=model,
            instructions=instructions,
            input=user_input,
            reasoning={"effort": reasoning_effort},
            store=False,
            text_format=output_type,
        )
        result = response.output_parsed
        if result is None:
            raise ModelOutputError("Review Agent returned no structured decision.")
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
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=base_url)

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
        response = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_input},
            ],
            reasoning_effort=self._deepseek_effort(reasoning_effort),
            extra_body={"thinking": {"type": "enabled"}},
            max_tokens=1600,
        )
        result = response.choices[0].message.content
        if not result or not result.strip():
            raise ModelOutputError("DeepSeek Reflection Agent returned empty content.")
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
        last_error: Exception | None = None

        for attempt in range(2):
            repair_instruction = (
                ""
                if attempt == 0
                else "\nThe previous output was empty or invalid. Return complete valid JSON."
            )
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
            content = response.choices[0].message.content
            if not content or not content.strip():
                last_error = ModelOutputError(
                    "DeepSeek Review Agent returned empty JSON."
                )
                continue

            try:
                return output_type.model_validate_json(content)
            except ValidationError as exc:
                last_error = exc

        raise ModelOutputError(
            "DeepSeek Review Agent returned invalid structured output."
        ) from last_error
