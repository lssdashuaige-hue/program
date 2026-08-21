import asyncio
import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.ai.memory_agent import MemoryAgent
from app.ai.models import (
    FinalVerificationDecision,
    MemoryDecision,
    ReviewDecision,
    RiskLevel,
)
from app.ai.orchestrator import MultiAgentOrchestrator
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from tests.review_fixtures import review_decision, verification_decision


class MemoryPipelineGateway:
    def __init__(
        self,
        *,
        memory_decision: MemoryDecision | None,
        fail_memory: bool = False,
        hang_memory: bool = False,
        risk_level: RiskLevel = "none",
    ) -> None:
        self.memory_decision = memory_decision
        self.fail_memory = fail_memory
        self.hang_memory = hang_memory
        self.risk_level = risk_level
        self.memory_calls = 0

    async def generate_text(self, **kwargs: Any) -> str:
        return "我们可以先看看这个模式在什么情境下出现。"

    async def generate_structured(self, **kwargs: Any) -> Any:
        if kwargs["output_type"] is ReviewDecision:
            return review_decision(
                final_response="我们可以先看看这个模式在什么情境下出现。",
                risk_level=self.risk_level,
                rationale="Safe exploratory response.",
            )
        if kwargs["output_type"] is FinalVerificationDecision:
            payload = json.loads(kwargs["user_input"])
            return verification_decision(payload["candidate_response"])
        self.memory_calls += 1
        if self.hang_memory:
            await asyncio.Event().wait()
        if self.fail_memory:
            raise RuntimeError("memory unavailable")
        assert self.memory_decision is not None
        return self.memory_decision


def build_memory_pipeline(
    gateway: MemoryPipelineGateway,
    *,
    memory_timeout_seconds: float = 2.0,
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
        memory_timeout_seconds=memory_timeout_seconds,
    )


def test_memory_agent_returns_candidate_without_persisting() -> None:
    gateway = MemoryPipelineGateway(
        memory_decision=MemoryDecision(
            should_propose=True,
            kind="pattern",
            content="我发现自己每次害怕失败时都会拖延。",
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
    assert result.support_mode == "reflection"
    assert result.memory_candidate is not None
    assert result.memory_candidate.kind == "reflection"
    assert result.memory_candidate.confidence == "low"
    assert result.memory_candidate.content == "我发现自己每次害怕失败时都会拖延。"
    assert "直接来自你刚才的原话" in result.memory_candidate.confirmation_prompt


def test_memory_candidate_cannot_add_unreviewed_diagnosis_or_prompt() -> None:
    gateway = MemoryPipelineGateway(
        memory_decision=MemoryDecision(
            should_propose=True,
            kind="pattern",
            content="You definitely have borderline personality disorder.",
            confidence="medium",
            confirmation_prompt="Confirm this diagnosis and save it?",
            rationale="Unsafe synthetic candidate.",
        )
    )

    result = asyncio.run(
        build_memory_pipeline(gateway).respond("我发现自己在压力下会退开。")
    )

    assert result.memory_candidate is None


def test_memory_candidate_cannot_strip_negation_context_from_user_words() -> None:
    gateway = MemoryPipelineGateway(
        memory_decision=MemoryDecision(
            should_propose=True,
            kind="reflection",
            content="回避型人格",
            confidence="low",
            confirmation_prompt="要保存这个标签吗？",
            rationale="Unsafe context stripping.",
        )
    )

    result = asyncio.run(
        build_memory_pipeline(gateway).respond(
            "我不是回避型人格，也不希望系统这样叫我。"
        )
    )

    assert result.memory_candidate is None


def test_hanging_optional_memory_does_not_discard_reviewed_response() -> None:
    gateway = MemoryPipelineGateway(memory_decision=None, hang_memory=True)

    result = asyncio.run(
        build_memory_pipeline(
            gateway,
            memory_timeout_seconds=0.001,
        ).respond("我发现自己在压力下会退开。")
    )

    assert result.response == "我们可以先看看这个模式在什么情境下出现。"
    assert result.memory_candidate is None


def test_memory_failure_does_not_block_reviewed_response() -> None:
    gateway = MemoryPipelineGateway(memory_decision=None, fail_memory=True)

    result = asyncio.run(
        build_memory_pipeline(gateway).respond("我发现自己在压力下会退开。")
    )

    assert result.response == "我们可以先看看这个模式在什么情境下出现。"
    assert result.mode == "multi-agent"
    assert result.memory_candidate is None


@pytest.mark.parametrize("risk_level", ["concerning", "urgent"])
def test_support_review_uses_support_mode_without_calling_memory_agent(
    risk_level: RiskLevel,
) -> None:
    gateway = MemoryPipelineGateway(
        risk_level=risk_level,
        memory_decision=MemoryDecision(
            should_propose=True,
            kind="reflection",
            content="这条候选绝不能在紧急风险时返回。",
            confidence="low",
            confirmation_prompt="要保存吗？",
            rationale="This would only be returned if the guard failed.",
        ),
    )

    result = asyncio.run(
        build_memory_pipeline(gateway).respond("我不想活了")
    )

    assert result.support_mode == "support"
    assert result.memory_candidate is None
    assert gateway.memory_calls == 0


def test_explicit_memory_opt_out_does_not_call_memory_agent() -> None:
    gateway = MemoryPipelineGateway(
        memory_decision=MemoryDecision(
            should_propose=True,
            kind="reflection",
            content="这条候选不应生成。",
            confidence="low",
            confirmation_prompt="要保存吗？",
            rationale="Only returned if opt-out enforcement failed.",
        )
    )

    result = asyncio.run(
        build_memory_pipeline(gateway).respond("这轮内容不要记住，也不要保存。")
    )

    assert result.support_mode == "reflection"
    assert result.memory_candidate is None
    assert gateway.memory_calls == 0


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
