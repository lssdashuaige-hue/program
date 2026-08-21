import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api
from app.ai.context import ConversationContextMessage
from app.ai.models import FinalVerificationDecision, ReviewDecision
from app.ai.orchestrator import AgentPipelineError, MultiAgentOrchestrator
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.api.chat import get_orchestrator
from app.main import app
from tests.review_fixtures import review_decision, verification_decision


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
        if kwargs["output_type"] is FinalVerificationDecision:
            self.calls.append(("review_verifier", kwargs))
            candidate = json.loads(kwargs["user_input"])["candidate_response"]
            return verification_decision(candidate)  # type: ignore[return-value]
        self.calls.append(("review", kwargs))
        if self.fail_review:
            raise RuntimeError("review unavailable")
        assert self.decision is not None
        return self.decision


class HangingOrchestrator:
    async def respond(self, user_message: str) -> Any:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class DelayedGateway(FakeGateway):
    def __init__(
        self,
        *,
        reflection_delay: float,
        review_delay: float,
        decision: ReviewDecision,
    ) -> None:
        super().__init__(decision=decision)
        self.reflection_delay = reflection_delay
        self.review_delay = review_delay

    async def generate_text(self, **kwargs: Any) -> str:
        self.calls.append(("reflection", kwargs))
        await asyncio.sleep(self.reflection_delay)
        return self.draft

    async def generate_structured(self, **kwargs: Any) -> ReviewDecision:
        if kwargs["output_type"] is FinalVerificationDecision:
            self.calls.append(("review_verifier", kwargs))
            candidate = json.loads(kwargs["user_input"])["candidate_response"]
            return verification_decision(candidate)  # type: ignore[return-value]
        self.calls.append(("review", kwargs))
        await asyncio.sleep(self.review_delay)
        assert self.decision is not None
        return self.decision


def build_orchestrator(
    gateway: FakeGateway,
    **timeout_overrides: float,
) -> MultiAgentOrchestrator:
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
        **timeout_overrides,
    )


def test_review_agent_can_approve_draft() -> None:
    gateway = FakeGateway(
        draft="你似乎很累。哪一种疲惫最接近你的体验？",
        decision=review_decision(
            final_response="你似乎很累。哪一种疲惫最接近你的体验？",
            rationale="The draft is tentative and exploratory.",
        ),
    )

    result = asyncio.run(build_orchestrator(gateway).respond("我最近很累"))

    assert result.response == "你似乎很累。哪一种疲惫最接近你的体验？"
    assert result.mode == "multi-agent"
    assert result.support_mode == "reflection"
    assert [call[0] for call in gateway.calls] == [
        "reflection",
        "review",
        "review_verifier",
    ]


def test_reviewed_history_is_passed_to_both_agents_as_bounded_context() -> None:
    gateway = FakeGateway(
        draft="我们可以从这次的新变化开始看。",
        decision=review_decision(
            draft_disposition="rewritten",
            draft_findings=["pas_principle_violation"],
            final_response="这次似乎和上次有一点不同。你最先注意到的变化是什么？",
            rationale="The response remains tentative and uses the prior turn as context.",
        ),
    )
    history = (
        ConversationContextMessage(role="user", content="上次我说工作让我很累。"),
        ConversationContextMessage(
            role="assistant",
            content="当时你更想先分辨身体疲惫还是关系压力。",
        ),
    )

    result = asyncio.run(
        build_orchestrator(gateway).respond(
            "今天情况有一点变化。",
            conversation_history=history,
        )
    )

    reflection_payload = json.loads(gateway.calls[0][1]["user_input"])
    review_payload = json.loads(gateway.calls[1][1]["user_input"])
    verifier_payload = json.loads(gateway.calls[2][1]["user_input"])
    assert reflection_payload["current_user_message"] == "今天情况有一点变化。"
    assert reflection_payload["conversation_history"] == [
        {"role": "user", "content": "上次我说工作让我很累。"},
        {
            "role": "assistant",
            "content": "当时你更想先分辨身体疲惫还是关系压力。",
        },
    ]
    assert review_payload["current_user_message"] == "今天情况有一点变化。"
    assert review_payload["conversation_history"] == reflection_payload[
        "conversation_history"
    ]
    assert verifier_payload["conversation_history"] == reflection_payload[
        "conversation_history"
    ]
    assert verifier_payload["candidate_response"] == (
        "这次似乎和上次有一点不同。你最先注意到的变化是什么？"
    )
    assert result.response == "这次似乎和上次有一点不同。你最先注意到的变化是什么？"


def test_review_agent_can_rewrite_unsafe_draft() -> None:
    gateway = FakeGateway(
        draft="你就是回避型人格。",
        decision=review_decision(
            draft_disposition="rewritten",
            draft_findings=["diagnosis", "labeling", "overcertainty"],
            final_response="在一些情境里，你似乎会选择退开。你觉得这种描述贴近你的体验吗？",
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


def test_reflection_and_review_receive_independent_time_budgets() -> None:
    final = "这是经过独立时间预算审核的回复。"
    gateway = DelayedGateway(
        reflection_delay=0.06,
        review_delay=0.06,
        decision=review_decision(
            draft_disposition="rewritten",
            draft_findings=["pas_principle_violation"],
            final_response=final,
            rationale="Safe.",
        ),
    )

    result = asyncio.run(
        build_orchestrator(
            gateway,
            reflection_timeout_seconds=0.1,
            review_timeout_seconds=0.1,
        ).respond("测试独立阶段预算")
    )

    assert result.response == final
    assert [call[0] for call in gateway.calls] == [
        "reflection",
        "review",
        "review_verifier",
    ]


def test_reflection_stage_timeout_is_reported_and_review_is_not_called() -> None:
    gateway = DelayedGateway(
        reflection_delay=0.02,
        review_delay=0,
        decision=review_decision(
            final_response="绝不能到达的回复。",
            rationale="Unreachable.",
        ),
    )

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(
            build_orchestrator(
                gateway,
                reflection_timeout_seconds=0.001,
                review_timeout_seconds=0.03,
            ).respond("测试 Reflection 超时")
        )

    assert caught.value.stage == "reflection"
    assert caught.value.diagnostic.code == "provider_timeout"
    assert caught.value.diagnostic.timeout_origin == "stage_deadline"
    assert caught.value.diagnostic.stage_elapsed_ms is not None
    assert caught.value.diagnostic.stage_elapsed_ms >= 1
    assert caught.value.diagnostic.stage_timeout_ms == 1
    assert [call[0] for call in gateway.calls] == ["reflection"]


def test_review_stage_timeout_fails_closed_without_returning_draft() -> None:
    gateway = DelayedGateway(
        reflection_delay=0,
        review_delay=0.02,
        decision=review_decision(
            final_response="绝不能到达的回复。",
            rationale="Unreachable.",
        ),
    )

    with pytest.raises(AgentPipelineError) as caught:
        asyncio.run(
            build_orchestrator(
                gateway,
                reflection_timeout_seconds=0.03,
                review_timeout_seconds=0.001,
            ).respond("测试 Review 超时")
        )

    assert caught.value.stage == "review"
    assert caught.value.diagnostic.code == "provider_timeout"
    assert caught.value.diagnostic.timeout_origin == "stage_deadline"
    assert caught.value.diagnostic.stage_elapsed_ms is not None
    assert caught.value.diagnostic.stage_elapsed_ms >= 1
    assert caught.value.diagnostic.stage_timeout_ms == 1
    assert [call[0] for call in gateway.calls] == ["reflection", "review"]
    assert "draft" not in str(caught.value)


def test_chat_endpoint_returns_only_reviewed_response() -> None:
    gateway = FakeGateway(
        draft="未经审核的草稿",
        decision=review_decision(
            draft_disposition="rewritten",
            draft_findings=["pas_principle_violation"],
            final_response="这是经过审核和改写的探索回应。",
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
        "mode": "multi-agent",
        "support_mode": "reflection",
        "response_source": "review",
        "persistence": {"status": "not_requested"},
    }
    assert "未经审核" not in response.text


def test_chat_endpoint_returns_fixed_fallback_when_review_is_unavailable() -> None:
    gateway = FakeGateway(draft="绝不能返回的草稿", fail_review=True)
    app.dependency_overrides[get_orchestrator] = lambda: build_orchestrator(gateway)

    try:
        response = TestClient(app).post("/chat", json={"message": "测试消息"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["mode"] == "safety-guard"
    assert response.json()["support_mode"] == "support"
    assert "不会返回未经审核的内容" in response.json()["response"]
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


def test_chat_endpoint_allows_preflight_safety_without_provider() -> None:
    app.dependency_overrides[get_orchestrator] = lambda: None

    try:
        response = TestClient(app).post(
            "/chat",
            json={
                "message": "我现在已经想好了今晚结束生命的方法，而且一个人待着。"
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["mode"] == "safety-guard"
    assert response.json()["support_mode"] == "support"
    assert "立即处理的紧急自伤危险" in response.json()["response"]
    assert "memory_candidate" not in response.json()


def test_chat_timeout_returns_fixed_fallback_without_unreviewed_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.dependency_overrides[get_orchestrator] = lambda: HangingOrchestrator()
    monkeypatch.setattr(chat_api, "CHAT_TIMEOUT_SECONDS", 0.001)

    try:
        response = TestClient(app).post(
            "/chat",
            json={"message": "我只是想整理一下今天发生的事情。"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["mode"] == "safety-guard"
    assert response.json()["support_mode"] == "support"
    assert "不会返回未经审核的内容" in response.json()["response"]
