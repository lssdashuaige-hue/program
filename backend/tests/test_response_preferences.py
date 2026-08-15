import asyncio
import json
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api
from app.ai.context import (
    RESPONSE_PREFERENCE_GUIDANCE,
    ResponsePreference,
)
from app.ai.models import AgentResult, MemoryDecision, ReviewDecision
from app.ai.orchestrator import MultiAgentOrchestrator
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.api.chat import get_orchestrator
from app.auth import AuthenticatedUser
from app.main import app
from app.persistence import SavedReviewedTurn, get_optional_persistence


PREFERENCES = tuple(RESPONSE_PREFERENCE_GUIDANCE)


def reviewed_result() -> AgentResult:
    final_response = "这是 Review 后的最终回应。"
    review = ReviewDecision(
        approved=True,
        final_response=final_response,
        issues=[],
        risk_level="none",
        rationale="The result is safe and preserves the user's wording.",
    )
    return AgentResult(
        response=final_response,
        mode="dual-agent",
        support_mode="reflection",
        response_source="review",
        risk_level="none",
        reflection_draft="仅供 Review 的草稿。",
        review=review,
    )


class CapturingGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def generate_text(self, **kwargs: Any) -> str:
        self.calls.append(("reflection", kwargs))
        return "一种暂定的 Reflection 草稿。"

    async def generate_structured(self, **kwargs: Any) -> ReviewDecision:
        self.calls.append(("review", kwargs))
        return ReviewDecision(
            approved=True,
            final_response="这是 Review 后的最终回应。",
            issues=[],
            risk_level="none",
            rationale="The preference remains a soft style target.",
        )


class CapturingMemoryAgent:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    async def evaluate(self, **kwargs: object) -> MemoryDecision:
        self.kwargs = kwargs
        return MemoryDecision(
            should_propose=False,
            rationale="A response preference is not memory.",
        )


def build_orchestrator(
    gateway: CapturingGateway,
    *,
    memory_agent: CapturingMemoryAgent | None = None,
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
        memory_agent=memory_agent,
    )


@pytest.mark.parametrize("preference", PREFERENCES)
def test_fixed_response_preference_reaches_reflection_and_review(
    preference: str,
) -> None:
    gateway = CapturingGateway()
    user_message = "  这是用户原话。\n请保留空白。  "

    asyncio.run(
        build_orchestrator(gateway).respond(
            user_message,
            response_preference=cast(ResponsePreference, preference),
        )
    )

    reflection_payload = json.loads(gateway.calls[0][1]["user_input"])
    review_payload = json.loads(gateway.calls[1][1]["user_input"])
    for payload in (reflection_payload, review_payload):
        assert payload["current_user_message"] == user_message
        assert payload["response_preference"] == preference
        assert payload["response_preference_guidance"] == (
            RESPONSE_PREFERENCE_GUIDANCE[cast(ResponsePreference, preference)]
        )
        assert "soft, single-turn" in payload["response_preference_boundary"]
        assert "not user-authored content" in payload[
            "response_preference_boundary"
        ]
        assert "must not weaken safety" in payload[
            "response_preference_boundary"
        ]
    assert "soft style target" in review_payload["review_instruction"]


def test_no_preference_preserves_the_existing_raw_reflection_input() -> None:
    gateway = CapturingGateway()
    user_message = "  用户原文不会被修剪。\n"

    asyncio.run(build_orchestrator(gateway).respond(user_message))

    assert gateway.calls[0][1]["user_input"] == user_message
    review_payload = json.loads(gateway.calls[1][1]["user_input"])
    assert review_payload["current_user_message"] == user_message
    assert "response_preference" not in review_payload


def test_response_preference_never_enters_memory_input() -> None:
    gateway = CapturingGateway()
    memory = CapturingMemoryAgent()
    user_message = "  只把这一段原话交给 Memory。  "

    asyncio.run(
        build_orchestrator(gateway, memory_agent=memory).respond(
            user_message,
            response_preference="organize",
        )
    )

    assert memory.kwargs == {
        "user_message": user_message,
        "risk_level": "none",
    }


class CapturingOrchestrator:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def respond(
        self,
        message: str,
        *,
        conversation_history=(),
        response_preference: ResponsePreference | None = None,
    ) -> AgentResult:
        self.calls.append(
            {
                "message": message,
                "conversation_history": conversation_history,
                "response_preference": response_preference,
            }
        )
        return reviewed_result()


@pytest.mark.parametrize("preference", PREFERENCES)
def test_chat_accepts_each_preference_without_rewriting_the_message(
    preference: str,
) -> None:
    orchestrator = CapturingOrchestrator()
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    user_message = "  原样发送\n第二行  "

    try:
        response = TestClient(app).post(
            "/chat",
            json={
                "message": user_message,
                "response_preference": preference,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert orchestrator.calls == [
        {
            "message": user_message,
            "conversation_history": (),
            "response_preference": preference,
        }
    ]


def test_chat_rejects_unknown_preference_before_the_pipeline() -> None:
    orchestrator = CapturingOrchestrator()
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    try:
        response = TestClient(app).post(
            "/chat",
            json={
                "message": "普通消息",
                "response_preference": "diagnose_me",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert orchestrator.calls == []


def test_preflight_safety_ignores_preference_and_needs_no_provider() -> None:
    app.dependency_overrides[get_orchestrator] = lambda: None

    try:
        response = TestClient(app).post(
            "/chat",
            json={
                "message": "我今晚想死，刀就在手边。",
                "response_preference": "explore_causes",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["response_source"] == "safety_guard"
    assert "立即处理的紧急自伤危险" in response.json()["response"]


class FakePersistence:
    def __init__(self) -> None:
        self.saved_kwargs: dict[str, object] | None = None

    async def get_saved_turn(self, _user, **_kwargs):
        return None

    async def list_context_messages(self, _user, _conversation_id):
        return []

    async def save_reviewed_turn(self, _user, **kwargs):
        self.saved_kwargs = kwargs
        return SavedReviewedTurn(
            conversation_id=kwargs.get("conversation_id") or uuid4(),
            client_turn_id=kwargs["client_turn_id"],
            user_message_id=uuid4(),
            assistant_message_id=uuid4(),
            response=kwargs["final_response"],
            already_saved=False,
        )


def override_authenticated(
    monkeypatch: pytest.MonkeyPatch,
    orchestrator: CapturingOrchestrator,
    persistence: FakePersistence,
    user_id: UUID,
) -> None:
    async def authenticate(_credentials, _settings):
        return AuthenticatedUser(id=user_id, access_token="user-token")

    monkeypatch.setattr(chat_api, "optional_authenticated_user", authenticate)
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_optional_persistence] = lambda: persistence


def test_persistence_saves_only_the_raw_message_not_the_preference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = CapturingOrchestrator()
    persistence = FakePersistence()
    turn_id = uuid4()
    user_message = "  用户实际原文\n不要改写  "
    override_authenticated(
        monkeypatch,
        orchestrator,
        persistence,
        uuid4(),
    )

    try:
        response = TestClient(app).post(
            "/chat",
            json={
                "message": user_message,
                "response_preference": "next_step",
                "client_turn_id": str(turn_id),
            },
            headers={"Authorization": "Bearer user-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert orchestrator.calls[0]["message"] == user_message
    assert orchestrator.calls[0]["response_preference"] == "next_step"
    assert persistence.saved_kwargs == {
        "client_turn_id": turn_id,
        "user_message": user_message,
        "final_response": "这是 Review 后的最终回应。",
        "response_source": "review",
        "support_mode": "reflection",
        "risk_level": "none",
        "conversation_id": None,
        "conversation_title": "用户实际原文 不要改写",
    }
    assert "response_preference" not in persistence.saved_kwargs
