import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import app.ai.gateway as gateway_module
from app.ai.gateway import DeepSeekChatGateway, ModelOutputError
from app.ai.models import ReviewDecision


class FakeCompletions:
    def __init__(
        self,
        contents: list[str | None],
        reasoning_contents: list[str | None] | None = None,
    ) -> None:
        self.contents = iter(contents)
        self.reasoning_contents = iter(
            reasoning_contents or [None for _ in contents]
        )
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        content = next(self.contents)
        message = SimpleNamespace(
            content=content,
            reasoning_content=next(self.reasoning_contents),
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeDeepSeekClient:
    def __init__(
        self,
        contents: list[str | None],
        reasoning_contents: list[str | None] | None = None,
    ) -> None:
        self.completions = FakeCompletions(contents, reasoning_contents)
        self.chat = SimpleNamespace(completions=self.completions)


def test_deepseek_text_generation_disables_thinking_for_unreviewed_draft() -> None:
    client = FakeDeepSeekClient(["经过审核前的探索草稿"])
    gateway = DeepSeekChatGateway("test-key", client=client)

    result = asyncio.run(
        gateway.generate_text(
            model="deepseek-v4-pro",
            instructions="PAS reflection",
            user_input="我最近很累",
            reasoning_effort="high",
        )
    )

    assert result == "经过审核前的探索草稿"
    call = client.completions.calls[0]
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in call
    assert call["max_tokens"] == 1600
    assert call["model"] == "deepseek-v4-pro"


def test_deepseek_client_disables_implicit_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_client = object()

    def build_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return fake_client

    monkeypatch.setattr(gateway_module, "AsyncOpenAI", build_client)

    gateway = DeepSeekChatGateway("test-key")

    assert gateway._client is fake_client
    assert captured["max_retries"] == 0


def test_deepseek_structured_review_is_validated() -> None:
    content = ReviewDecision(
        approved=False,
        final_response="这是审核后的回复。",
        issues=["overcertainty"],
        risk_level="none",
        rationale="The draft was too certain.",
    ).model_dump_json()
    client = FakeDeepSeekClient([content])
    gateway = DeepSeekChatGateway("test-key", client=client)

    result = asyncio.run(
        gateway.generate_structured(
            model="deepseek-v4-pro",
            instructions="PAS review",
            user_input='{"user_message":"测试","reflection_draft":"草稿"}',
            reasoning_effort="high",
            output_type=ReviewDecision,
        )
    )

    assert result.final_response == "这是审核后的回复。"
    call = client.completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"] == {"thinking": {"type": "enabled"}}
    assert call["reasoning_effort"] == "high"
    assert call["max_tokens"] == 2400


def test_deepseek_review_never_uses_reasoning_content_as_output() -> None:
    safe_content = ReviewDecision(
        approved=True,
        final_response="只采用 content 中经过验证的回复。",
        issues=[],
        risk_level="none",
        rationale="The content is safe.",
    ).model_dump_json()
    client = FakeDeepSeekClient(
        [safe_content],
        reasoning_contents=[
            '{"approved":true,"final_response":"绝不能采用的思维内容"}'
        ],
    )
    gateway = DeepSeekChatGateway("test-key", client=client)

    result = asyncio.run(
        gateway.generate_structured(
            model="deepseek-v4-pro",
            instructions="PAS review",
            user_input="test",
            reasoning_effort="high",
            output_type=ReviewDecision,
        )
    )

    assert result.final_response == "只采用 content 中经过验证的回复。"
    assert "思维内容" not in result.final_response


def test_deepseek_invalid_review_fails_closed_after_retry() -> None:
    client = FakeDeepSeekClient(["not json", None])
    gateway = DeepSeekChatGateway("test-key", client=client)

    with pytest.raises(ModelOutputError):
        asyncio.run(
            gateway.generate_structured(
                model="deepseek-v4-pro",
                instructions="PAS review",
                user_input="test",
                reasoning_effort="high",
                output_type=ReviewDecision,
            )
        )

    assert len(client.completions.calls) == 2
