import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from app.ai.memory_agent import MemoryAgent
from app.ai.models import MemoryDecision, ReviewDecision
from app.ai.orchestrator import MultiAgentOrchestrator
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent


class MemoryPipelineGateway:
    def __init__(
        self,
        *,
        memory_decision: MemoryDecision | None,
        fail_memory: bool = False,
    ) -> None:
        self.memory_decision = memory_decision
        self.fail_memory = fail_memory

    async def generate_text(self, **kwargs: Any) -> str:
        return "我们可以先看看这个模式在什么情境下出现。"

    async def generate_structured(self, **kwargs: Any) -> Any:
        if kwargs["output_type"] is ReviewDecision:
            return ReviewDecision(
                approved=True,
                final_response="我们可以先看看这个模式在什么情境下出现。",
                issues=[],
                risk_level="none",
                rationale="Safe exploratory response.",
            )
        if self.fail_memory:
            raise RuntimeError("memory unavailable")
        assert self.memory_decision is not None
        return self.memory_decision


def build_memory_pipeline(
    gateway: MemoryPipelineGateway,
) -> MultiAgentOrchestrator:
    return MultiAgentOrchestrator(
        reflection_agent=ReflectionAgent(
            gateway=gateway,
            model="reflection-model",
            instructions="reflection",
            reasoning_effort="medium",
        ),
        review_agent=ReviewAgent(
            gateway=gateway,
            model="review-model",
            instructions="review",
            reasoning_effort="medium",
        ),
        memory_agent=MemoryAgent(
            gateway=gateway,
            model="memory-model",
            instructions="memory",
            reasoning_effort="medium",
        ),
    )


def test_memory_agent_returns_candidate_without_persisting() -> None:
    gateway = MemoryPipelineGateway(
        memory_decision=MemoryDecision(
            should_propose=True,
            kind="pattern",
            content="用户注意到自己在害怕失败时容易拖延。",
            confidence="medium",
            confirmation_prompt="这符合你的体验吗？你希望 PAS 记住它吗？",
            rationale="The user explicitly described a recurring pattern.",
        )
    )

    result = asyncio.run(
        build_memory_pipeline(gateway).respond(
            "我发现自己每次害怕失败时都会拖延。"
        )
    )

    assert result.mode == "multi-agent"
    assert result.memory_candidate is not None
    assert result.memory_candidate.kind == "pattern"
    assert result.memory_candidate.confidence == "medium"


def test_memory_failure_does_not_block_reviewed_response() -> None:
    gateway = MemoryPipelineGateway(memory_decision=None, fail_memory=True)

    result = asyncio.run(
        build_memory_pipeline(gateway).respond("我发现自己在压力下会退开。")
    )

    assert result.response == "我们可以先看看这个模式在什么情境下出现。"
    assert result.mode == "multi-agent"
    assert result.memory_candidate is None


def test_declined_memory_cannot_contain_candidate_fields() -> None:
    with pytest.raises(ValidationError):
        MemoryDecision(
            should_propose=False,
            kind="pattern",
            content=None,
            confidence=None,
            confirmation_prompt=None,
            rationale="Invalid mixed decision.",
        )
