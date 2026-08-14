from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api
from app.ai.models import AgentResult, MemoryCandidate, ReviewDecision
from app.api.chat import get_orchestrator
from app.auth import AuthenticatedUser
from app.main import app
from app.persistence import (
    PersistenceUnavailable,
    SavedReviewedTurn,
    get_optional_persistence,
)


class NormalOrchestrator:
    def __init__(self, *, with_memory: bool = False) -> None:
        self.calls = 0
        self.history = ()
        self.with_memory = with_memory

    async def respond(self, message: str, *, conversation_history=()) -> AgentResult:
        self.calls += 1
        self.history = conversation_history
        return AgentResult(
            response="这是 Review 后最终回复。",
            mode="multi-agent" if self.with_memory else "dual-agent",
            support_mode="reflection",
            memory_candidate=(
                MemoryCandidate(
                    kind="reflection",
                    content="候选理解",
                    confidence="low",
                    confirmation_prompt="要保存这条候选理解吗？",
                )
                if self.with_memory
                else None
            ),
            response_source="review",
            risk_level="none",
            reflection_draft="SENTINEL_DRAFT",
            review=ReviewDecision(
                approved=True,
                final_response="这是 Review 后最终回复。",
                risk_level="none",
                rationale="SENTINEL_RATIONALE",
            ),
        )


class ExplodingOrchestrator:
    async def respond(self, _message: str, **_kwargs) -> AgentResult:
        raise AssertionError("The model pipeline must not be called.")


class FakePersistence:
    def __init__(
        self,
        *,
        existing: SavedReviewedTurn | None = None,
        fail_save: bool = False,
    ) -> None:
        self.existing = existing
        self.fail_save = fail_save
        self.saved_kwargs = None
        self.context_messages = []
        self.read_calls = 0

    async def get_saved_turn(self, _user, **_kwargs):
        self.read_calls += 1
        return self.existing

    async def list_context_messages(self, _user, _conversation_id):
        return self.context_messages

    async def save_reviewed_turn(self, _user, **kwargs):
        self.saved_kwargs = kwargs
        if self.fail_save:
            raise PersistenceUnavailable("simulated failure")
        return SavedReviewedTurn(
            conversation_id=kwargs.get("conversation_id") or uuid4(),
            client_turn_id=kwargs["client_turn_id"],
            user_message_id=uuid4(),
            assistant_message_id=uuid4(),
            response=kwargs["final_response"],
            already_saved=False,
        )


def _override_authenticated(
    monkeypatch: pytest.MonkeyPatch,
    orchestrator,
    persistence: FakePersistence,
    user_id: UUID,
) -> None:
    async def authenticate(_credentials, _settings):
        return AuthenticatedUser(id=user_id, access_token="user-token")

    monkeypatch.setattr(chat_api, "optional_authenticated_user", authenticate)
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_optional_persistence] = lambda: persistence


def test_authenticated_normal_turn_saves_only_public_reviewed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = NormalOrchestrator()
    persistence = FakePersistence()
    turn_id = uuid4()
    _override_authenticated(monkeypatch, orchestrator, persistence, uuid4())

    try:
        response = TestClient(app).post(
            "/chat",
            json={"message": "用户实际原文", "client_turn_id": str(turn_id)},
            headers={"Authorization": "Bearer user-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == "这是 Review 后最终回复。"
    assert payload["response_source"] == "review"
    assert payload["persistence"]["status"] == "saved"
    assert persistence.saved_kwargs == {
        "client_turn_id": turn_id,
        "user_message": "用户实际原文",
        "final_response": "这是 Review 后最终回复。",
        "response_source": "review",
        "support_mode": "reflection",
        "risk_level": "none",
        "conversation_id": None,
        "conversation_title": "用户实际原文",
    }
    assert "SENTINEL_DRAFT" not in str(persistence.saved_kwargs)
    assert "SENTINEL_RATIONALE" not in str(persistence.saved_kwargs)


def test_saved_retry_returns_without_calling_the_model_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turn_id = uuid4()
    existing = SavedReviewedTurn(
        conversation_id=uuid4(),
        client_turn_id=turn_id,
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        response="已经保存的 Review 最终回复。",
    )
    persistence = FakePersistence(existing=existing)
    _override_authenticated(
        monkeypatch,
        ExplodingOrchestrator(),
        persistence,
        uuid4(),
    )

    try:
        response = TestClient(app).post(
            "/chat",
            json={"message": "同一条原文", "client_turn_id": str(turn_id)},
            headers={"Authorization": "Bearer user-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["response"] == "已经保存的 Review 最终回复。"
    assert response.json()["persistence"]["status"] == "already_saved"


def test_saved_retry_still_recovers_when_model_pipeline_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turn_id = uuid4()
    existing = SavedReviewedTurn(
        conversation_id=uuid4(),
        client_turn_id=turn_id,
        user_message_id=uuid4(),
        assistant_message_id=uuid4(),
        response="断网前已经保存的最终回复。",
    )
    persistence = FakePersistence(existing=existing)

    async def authenticate(_credentials, _settings):
        return AuthenticatedUser(id=uuid4(), access_token="user-token")

    monkeypatch.setattr(chat_api, "optional_authenticated_user", authenticate)
    app.dependency_overrides[get_orchestrator] = lambda: None
    app.dependency_overrides[get_optional_persistence] = lambda: persistence

    try:
        response = TestClient(app).post(
            "/chat",
            json={"message": "同一条原文", "client_turn_id": str(turn_id)},
            headers={"Authorization": "Bearer user-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["response"] == "断网前已经保存的最终回复。"
    assert response.json()["persistence"]["status"] == "already_saved"


def test_resumed_turn_uses_only_filtered_reviewed_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = NormalOrchestrator()
    persistence = FakePersistence()
    persistence.context_messages = [
        SimpleNamespace(role="user", content="上一轮原文"),
        SimpleNamespace(role="assistant", content="上一轮审核后回复"),
    ]
    conversation_id = uuid4()
    _override_authenticated(monkeypatch, orchestrator, persistence, uuid4())

    try:
        response = TestClient(app).post(
            "/chat",
            json={
                "message": "继续这一段",
                "conversation_id": str(conversation_id),
                "client_turn_id": str(uuid4()),
            },
            headers={"Authorization": "Bearer user-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [(item.role, item.content) for item in orchestrator.history] == [
        ("user", "上一轮原文"),
        ("assistant", "上一轮审核后回复"),
    ]


def test_preflight_support_is_never_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistence = FakePersistence()
    auth_called = False

    async def reject_stale_token(_credentials, _settings):
        nonlocal auth_called
        auth_called = True
        raise AssertionError("Safety preflight must precede remote authentication.")

    monkeypatch.setattr(chat_api, "optional_authenticated_user", reject_stale_token)
    app.dependency_overrides[get_orchestrator] = lambda: ExplodingOrchestrator()
    app.dependency_overrides[get_optional_persistence] = lambda: persistence

    try:
        response = TestClient(app).post(
            "/chat",
            json={
                "message": "我今晚已经想好了结束生命的方法，而且一个人待着。",
                "client_turn_id": str(uuid4()),
            },
            headers={"Authorization": "Bearer stale-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["response_source"] == "safety_guard"
    assert response.json()["persistence"]["status"] == "not_saved_support"
    assert persistence.read_calls == 0
    assert persistence.saved_kwargs is None
    assert auth_called is False


def test_failed_storage_returns_reviewed_answer_but_suppresses_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = NormalOrchestrator(with_memory=True)
    persistence = FakePersistence(fail_save=True)
    _override_authenticated(monkeypatch, orchestrator, persistence, uuid4())

    try:
        response = TestClient(app).post(
            "/chat",
            json={"message": "普通表达", "client_turn_id": str(uuid4())},
            headers={"Authorization": "Bearer user-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["persistence"]["status"] == "failed"
    assert "memory_candidate" not in response.json()


def test_anonymous_client_cannot_resume_a_saved_conversation() -> None:
    app.dependency_overrides[get_orchestrator] = lambda: ExplodingOrchestrator()

    try:
        response = TestClient(app).post(
            "/chat",
            json={
                "message": "继续",
                "conversation_id": str(uuid4()),
                "client_turn_id": str(uuid4()),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
