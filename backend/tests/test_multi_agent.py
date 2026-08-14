import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.models import ReviewDecision
from app.ai.orchestrator import AgentPipelineError, MultiAgentOrchestrator
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.api.chat import get_orchestrator
from app.main import app


class FakeGateway:
    def __init__(
        self,
        *,
        draft: str = "draft",
        decision: ReviewDecision | None = None,
        fail_review: bool = False,
    ) -> None:
        self.draft = draft
        self.decision = decision
        self.fail_review = fail_review
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def generate_text(self, **kwargs: Any) -> str:
        self.calls.append(("reflection", kwargs))
        return self.draft

    async def generate_structured(self, **kwargs: Any) -> ReviewDecision:
        self.calls.append(("review", kwargs))
        if self.fail_review:
            raise RuntimeError("review unavailable")
        assert self.decision is not None
        return self.decision


def build_orchestrator(gateway: FakeGateway) -> MultiAgentOrchestrator:
    return MultiAgentOrchestrator(
        reflection_agent=ReflectionAgent(
            gateway=gateway,
            model="reflection-model",
            instructions="reflection instructions",
            reasoning_effort="medium",
        ),
        review_agent=ReviewAgent(
            gateway=gateway,
            model="review-model",
            instructions="review instructions",
            reasoning_effort="medium",
        ),
    )


def test_review_agent_can_approve_draft() -> None:
    gateway = FakeGateway(
        draft="你似乎很累。哪一种疲惫最接近你的体验？",
        decision=ReviewDecision(
            approved=True,
            final_response="你似乎很累。哪一种疲惫最接近你的体验？",
            issues=[],
            risk_level="none",
            rationale="The draft is tentative and exploratory.",
        ),
    )

    result = asyncio.run(build_orchestrator(gateway).respond("我最近很累"))

    assert result.response == "你似乎很累。哪一种疲惫最接近你的体验？"
    assert result.mode == "dual-agent"
    assert result.support_mode == "reflection"
    assert [call[0] for call in gateway.calls] == ["reflection", "review"]


def test_review_agent_can_rewrite_unsafe_draft() -> None:
    gateway = FakeGateway(
        draft="你就是回避型人格。",
        decision=ReviewDecision(
            approved=False,
            final_response="在一些情境里，你似乎会选择退开。你觉得这种描述贴近你的体验吗？",
            issues=["diagnosis", "labeling", "overcertainty"],
            risk_level="none",
            rationale="The draft fixed a tentative behavior into an identity label.",
        ),
    )

    result = asyncio.run(build_orchestrator(gateway).respond("我总想躲开别人"))

    assert "回避型人格" not in result.response
    assert "你觉得" in result.response


def test_unreviewed_draft_is_never_returned() -> None:
    gateway = FakeGateway(draft="unsafe draft", fail_review=True)

    with pytest.raises(AgentPipelineError):
        asyncio.run(build_orchestrator(gateway).respond("test"))


def test_chat_endpoint_returns_only_reviewed_response() -> None:
    gateway = FakeGateway(
        draft="未经审核的草稿",
        decision=ReviewDecision(
            approved=False,
            final_response="这是经过审核和改写的探索回应。",
            issues=["pas_principle_violation"],
            risk_level="none",
            rationale="The original draft did not follow PAS principles.",
        ),
    )
    app.dependency_overrides[get_orchestrator] = lambda: build_orchestrator(gateway)

    try:
        response = TestClient(app).post("/chat", json={"message": "测试消息"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "response": "这是经过审核和改写的探索回应。",
        "mode": "dual-agent",
        "support_mode": "reflection",
    }
    assert "未经审核" not in response.text


def test_chat_endpoint_fails_closed_when_review_is_unavailable() -> None:
    gateway = FakeGateway(draft="绝不能返回的草稿", fail_review=True)
    app.dependency_overrides[get_orchestrator] = lambda: build_orchestrator(gateway)

    try:
        response = TestClient(app).post("/chat", json={"message": "测试消息"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "PAS 暂时无法完成安全审核，请稍后再试。"
    assert "绝不能返回的草稿" not in response.text


def test_chat_endpoint_is_unavailable_without_review_pipeline() -> None:
    app.dependency_overrides[get_orchestrator] = lambda: None

    try:
        response = TestClient(app).post("/chat", json={"message": "我想整理一下今天"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "PAS 的 AI 与安全审核尚未配置，当前无法开始探索。"
    )
    assert "response" not in response.json()
