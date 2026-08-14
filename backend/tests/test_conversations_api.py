from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, require_authenticated_user
from app.main import app
from app.persistence import (
    ConversationRecord,
    MessageRecord,
    get_persistence,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


class FakePersistence:
    def __init__(self) -> None:
        self.conversation = ConversationRecord(
            id=uuid4(),
            title="今天的探索",
            status="active",
            created_at=NOW,
            updated_at=NOW,
        )
        self.deleted = False
        self.last_changes: dict[str, Any] | None = None
        self.last_list_kwargs: dict[str, Any] | None = None

    async def create_conversation(
        self,
        _user: AuthenticatedUser,
        *,
        title: str | None,
    ) -> ConversationRecord:
        return self.conversation.model_copy(update={"title": title})

    async def list_conversations(self, *_args: Any, **kwargs: Any) -> list[ConversationRecord]:
        self.last_list_kwargs = kwargs
        return [self.conversation]

    async def get_conversation(
        self,
        _user: AuthenticatedUser,
        conversation_id: UUID,
    ) -> ConversationRecord | None:
        return self.conversation if conversation_id == self.conversation.id else None

    async def list_messages(
        self,
        _user: AuthenticatedUser,
        conversation_id: UUID,
    ) -> list[MessageRecord]:
        return [
            MessageRecord(
                id=uuid4(),
                conversation_id=conversation_id,
                client_turn_id=uuid4(),
                role="user",
                content="我想整理今天。",
                created_at=NOW,
            )
        ]

    async def update_conversation(
        self,
        _user: AuthenticatedUser,
        conversation_id: UUID,
        changes: dict[str, Any],
    ) -> ConversationRecord | None:
        self.last_changes = changes
        if conversation_id != self.conversation.id:
            return None
        return self.conversation.model_copy(update=changes)

    async def delete_conversation(
        self,
        _user: AuthenticatedUser,
        conversation_id: UUID,
    ) -> bool:
        self.deleted = conversation_id == self.conversation.id
        return self.deleted


@pytest.fixture(autouse=True)
def clear_overrides() -> Any:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def authorize(fake: FakePersistence) -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUser(
        id=uuid4(),
        access_token="user-token",
    )
    app.dependency_overrides[get_persistence] = lambda: fake


def test_conversation_routes_require_login() -> None:
    response = TestClient(app).get("/conversations")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_list_and_message_history_use_stable_envelopes() -> None:
    fake = FakePersistence()
    authorize(fake)
    client = TestClient(app)

    conversations = client.get("/conversations?limit=31&offset=30")
    messages = client.get(f"/conversations/{fake.conversation.id}/messages")

    assert conversations.status_code == 200
    assert conversations.json()["items"][0]["id"] == str(fake.conversation.id)
    assert fake.last_list_kwargs == {
        "conversation_status": None,
        "limit": 31,
        "offset": 30,
    }
    assert messages.status_code == 200
    assert messages.json()["conversation_id"] == str(fake.conversation.id)
    assert messages.json()["items"][0]["role"] == "user"


def test_create_rename_archive_and_delete_conversation() -> None:
    fake = FakePersistence()
    authorize(fake)
    client = TestClient(app)

    created = client.post("/conversations", json={"title": "  新主题  "})
    renamed = client.patch(
        f"/conversations/{fake.conversation.id}",
        json={"title": "整理后的主题", "status": "archived"},
    )
    deleted = client.delete(f"/conversations/{fake.conversation.id}")

    assert created.status_code == 201
    assert created.json()["title"] == "新主题"
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "整理后的主题"
    assert renamed.json()["status"] == "archived"
    assert fake.last_changes == {
        "title": "整理后的主题",
        "status": "archived",
    }
    assert deleted.status_code == 204
    assert deleted.content == b""


def test_unknown_or_other_users_conversation_is_always_404() -> None:
    fake = FakePersistence()
    authorize(fake)
    other_id = uuid4()
    client = TestClient(app)

    detail = client.get(f"/conversations/{other_id}")
    messages = client.get(f"/conversations/{other_id}/messages")
    renamed = client.patch(
        f"/conversations/{other_id}",
        json={"title": "不可见"},
    )
    deleted = client.delete(f"/conversations/{other_id}")

    assert {detail.status_code, messages.status_code, renamed.status_code, deleted.status_code} == {404}


def test_client_cannot_supply_user_id_or_empty_patch() -> None:
    fake = FakePersistence()
    authorize(fake)
    client = TestClient(app)

    forged = client.post(
        "/conversations",
        json={"title": "主题", "user_id": str(uuid4())},
    )
    empty = client.patch(f"/conversations/{fake.conversation.id}", json={})
    null_status = client.patch(
        f"/conversations/{fake.conversation.id}",
        json={"status": None},
    )

    assert forged.status_code == 422
    assert empty.status_code == 422
    assert null_status.status_code == 422
