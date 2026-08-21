from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api
from app.ai.bounded_responses import bounded_response_candidate
from app.ai.gateway import GatewayDiagnostic
from app.ai.models import AgentResult, MemoryCandidate
from app.ai.orchestrator import AgentPipelineError
from app.ai.safety import review_safety_envelope_result
from app.api.chat import get_orchestrator
from app.auth import AuthenticatedUser
from app.main import app
from app.persistence import (
    PersistenceConflict,
    PersistenceUnavailable,
    SavedReviewedTurn,
    get_optional_persistence,
)
from tests.review_fixtures import (
    review_decision,
    safe_final_checks,
    verification_decision,
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
            mode="multi-agent",
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
            review=review_decision(
                draft_disposition="rewritten",
                draft_findings=["pas_principle_violation"],
                final_response="这是 Review 后最终回复。",
                rationale="SENTINEL_RATIONALE",
            ),
            verification=verification_decision("这是 Review 后最终回复。"),
        )


class ExplodingOrchestrator:
    async def respond(self, _message: str, **_kwargs) -> AgentResult:
        raise AssertionError("The model pipeline must not be called.")


class BoundedSuccessOrchestrator:
    async def respond(self, message: str, **_kwargs) -> AgentResult:
        candidate = bounded_response_candidate(message)
        assert candidate is not None
        decision = review_decision(
            final_response=candidate.response,
            final_checks=safe_final_checks(
                source_bases=("current_user_message", "general_knowledge"),
                cross_chat_boundary=(
                    "satisfied"
                    if candidate.kind == "unavailable_cross_chat_context"
                    else "not_applicable"
                ),
            ),
            rationale="SENTINEL_BOUNDED_RATIONALE",
        )
        return AgentResult(
            response=candidate.response,
            mode="multi-agent",
            support_mode="reflection",
            response_source="review",
            risk_level="none",
            reflection_draft=candidate.response,
            review=decision,
            verification=verification_decision(candidate.response),
            bounded_response_kind=candidate.kind,
        )


class BoundedFailureOrchestrator:
    async def respond(self, _message: str, **_kwargs) -> AgentResult:
        raise AgentPipelineError(
            stage="review",
            diagnostic=GatewayDiagnostic(
                code="invalid_schema",
                content_present=True,
            ),
            reason="review_contract_violation",
            contract_failure_code="bounded_candidate_not_accepted",
        )


class BoundedSafetyEnvelopeOrchestrator:
    async def respond(self, message: str, **_kwargs) -> AgentResult:
        candidate = bounded_response_candidate(message)
        assert candidate is not None
        decision = review_decision(
            draft_disposition="rewritten",
            draft_findings=["crisis_mishandling"],
            final_response="SENTINEL_UNRELEASED_CANDIDATE",
            risk_level="concerning",
        )
        return review_safety_envelope_result(
            user_message=message,
            reflection_draft=candidate.response,
            review=decision,
        )


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


class LegacyConflictPersistence(FakePersistence):
    async def get_saved_turn(self, _user, **_kwargs):
        self.read_calls += 1
        raise PersistenceConflict(
            "The existing turn did not pass the current release contracts."
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
        "review_contract_version": "2",
        "verification_contract_version": "2",
        "bounded_response_kind": None,
        "conversation_id": None,
        "conversation_title": "用户实际原文",
    }
    assert "SENTINEL_DRAFT" not in str(persistence.saved_kwargs)
    assert "SENTINEL_RATIONALE" not in str(persistence.saved_kwargs)


@pytest.mark.parametrize(
    "user_message",
    [
        "你觉得她疏远我的动机是什么？",
        "我在另一个聊天讲过，请读取后告诉我结论。",
    ],
)
def test_authenticated_bounded_turn_persists_only_original_and_exact_final(
    monkeypatch: pytest.MonkeyPatch,
    user_message: str,
) -> None:
    candidate = bounded_response_candidate(user_message)
    assert candidate is not None
    persistence = FakePersistence()
    turn_id = uuid4()
    _override_authenticated(
        monkeypatch,
        BoundedSuccessOrchestrator(),
        persistence,
        uuid4(),
    )

    try:
        response = TestClient(app).post(
            "/chat",
            json={"message": user_message, "client_turn_id": str(turn_id)},
            headers={"Authorization": "Bearer user-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"] == candidate.response
    assert payload["mode"] == "multi-agent"
    assert payload["response_source"] == "review"
    assert payload["persistence"]["status"] == "saved"
    assert "memory_candidate" not in payload
    for internal_field in (
        "bounded_response_kind",
        "review_contract_version",
        "verification_contract_version",
        "reflection_draft",
        "review",
        "verification",
    ):
        assert internal_field not in payload
    assert persistence.saved_kwargs == {
        "client_turn_id": turn_id,
        "user_message": user_message,
        "final_response": candidate.response,
        "response_source": "review",
        "support_mode": "reflection",
        "risk_level": "none",
        "review_contract_version": "2",
        "verification_contract_version": "2",
        "bounded_response_kind": candidate.kind,
        "conversation_id": None,
        "conversation_title": user_message,
    }
    assert "SENTINEL_BOUNDED_RATIONALE" not in str(persistence.saved_kwargs)


@pytest.mark.parametrize(
    ("orchestrator", "expected_source", "expected_status"),
    [
        (BoundedFailureOrchestrator(), "safe_fallback", "not_saved_fallback"),
        (
            BoundedSafetyEnvelopeOrchestrator(),
            "review_safety_envelope",
            "not_saved_support",
        ),
    ],
)
def test_nonreleased_bounded_paths_are_never_persisted_as_normal_turns(
    monkeypatch: pytest.MonkeyPatch,
    orchestrator,
    expected_source: str,
    expected_status: str,
) -> None:
    persistence = FakePersistence()
    _override_authenticated(monkeypatch, orchestrator, persistence, uuid4())

    try:
        response = TestClient(app).post(
            "/chat",
            json={
                "message": "你觉得她疏远我的动机是什么？",
                "client_turn_id": str(uuid4()),
            },
            headers={"Authorization": "Bearer user-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["response_source"] == expected_source
    assert response.json()["persistence"]["status"] == expected_status
    assert persistence.saved_kwargs is None


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
    assert response.json()["mode"] == "multi-agent"
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


def test_legacy_turn_id_is_not_replayed_or_sent_back_through_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistence = LegacyConflictPersistence()
    _override_authenticated(
        monkeypatch,
        ExplodingOrchestrator(),
        persistence,
        uuid4(),
    )

    try:
        response = TestClient(app).post(
            "/chat",
            json={"message": "旧版原文", "client_turn_id": str(uuid4())},
            headers={"Authorization": "Bearer user-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert persistence.read_calls == 1
    assert persistence.saved_kwargs is None


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
