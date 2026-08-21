from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, require_authenticated_user
from app.main import app
from app.persistence import (
    ConversationRecord,
    MemoryRecord,
    MemorySettingsRecord,
    PersistenceNotAllowed,
    ProfileExportRecord,
    ThemeRecord,
    get_persistence,
)


NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)


class InMemoryDataControlPersistence:
    def __init__(self) -> None:
        self.settings: dict[UUID, MemorySettingsRecord] = {}
        self.memories: dict[UUID, list[MemoryRecord]] = {}
        self.sources: dict[tuple[UUID, UUID], str] = {}
        self.conversations: dict[UUID, list[ConversationRecord]] = {}
        self.profiles: dict[UUID, ProfileExportRecord] = {}
        self.themes: dict[UUID, list[ThemeRecord]] = {}
        self.deleted_users: list[UUID] = []

    async def get_memory_settings(self, user: AuthenticatedUser) -> MemorySettingsRecord:
        return self.settings.get(user.id, MemorySettingsRecord())

    async def set_memory_enabled(
        self,
        user: AuthenticatedUser,
        *,
        enabled: bool,
    ) -> MemorySettingsRecord:
        record = MemorySettingsRecord(
            memory_enabled=enabled,
            memory_enabled_at=NOW if enabled else None,
            updated_at=NOW,
        )
        self.settings[user.id] = record
        return record

    async def list_memories(
        self,
        user: AuthenticatedUser,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        return self.memories.get(user.id, [])[offset : offset + limit]

    async def create_confirmed_memory(
        self,
        user: AuthenticatedUser,
        *,
        source_message_id: UUID,
        kind: str,
        content: str,
        confidence: str,
    ) -> MemoryRecord:
        if not (await self.get_memory_settings(user)).memory_enabled:
            raise PersistenceNotAllowed("memory is off")
        if self.sources.get((user.id, source_message_id)) != content:
            raise PersistenceNotAllowed("source mismatch")
        memory_id = uuid4()
        record = MemoryRecord(
            id=memory_id,
            user_id=user.id,
            lineage_id=memory_id,
            source_message_id=source_message_id,
            kind=kind,
            content=content,
            original_content=content,
            confidence=confidence,
            confirmed=True,
            status="active",
            version=1,
            version_origin="source_quote",
            confirmed_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        self.memories.setdefault(user.id, []).insert(0, record)
        return record

    async def revise_memory(
        self,
        user: AuthenticatedUser,
        *,
        memory_id: UUID,
        expected_version: int,
        content: str,
    ) -> MemoryRecord | None:
        items = self.memories.get(user.id, [])
        current = next((item for item in items if item.id == memory_id), None)
        if current is None:
            return None
        revised = current.model_copy(
            update={
                "id": uuid4(),
                "supersedes_id": current.id,
                "content": content,
                "version": expected_version + 1,
                "version_origin": "user_revision",
                "confirmed_at": NOW + timedelta(minutes=1),
                "created_at": NOW + timedelta(minutes=1),
                "updated_at": NOW + timedelta(minutes=1),
            }
        )
        index = items.index(current)
        items[index] = current.model_copy(
            update={
                "status": "superseded",
                "superseded_at": NOW + timedelta(minutes=1),
            }
        )
        items.insert(0, revised)
        return revised

    async def set_memory_status(
        self,
        user: AuthenticatedUser,
        *,
        memory_id: UUID,
        memory_status: str,
    ) -> MemoryRecord | None:
        items = self.memories.get(user.id, [])
        current = next((item for item in items if item.id == memory_id), None)
        if current is None:
            return None
        updated = current.model_copy(
            update={
                "status": memory_status,
                "paused_at": NOW if memory_status == "paused" else None,
            }
        )
        items[items.index(current)] = updated
        return updated

    async def delete_memory_lineage(
        self,
        user: AuthenticatedUser,
        lineage_id: UUID,
    ) -> bool:
        items = self.memories.get(user.id, [])
        kept = [item for item in items if item.lineage_id != lineage_id]
        if len(kept) == len(items):
            return False
        self.memories[user.id] = kept
        return True

    async def list_conversations(
        self,
        user: AuthenticatedUser,
        *,
        limit: int,
        offset: int,
    ) -> list[ConversationRecord]:
        return self.conversations.get(user.id, [])[offset : offset + limit]

    async def list_export_messages(
        self,
        user: AuthenticatedUser,
        conversation_id: UUID,
    ) -> list[Any]:
        assert conversation_id in {
            item.id for item in self.conversations.get(user.id, [])
        }
        return []

    async def get_export_profile(
        self,
        user: AuthenticatedUser,
    ) -> ProfileExportRecord | None:
        return self.profiles.get(user.id)

    async def list_themes(
        self,
        user: AuthenticatedUser,
        *,
        limit: int,
        offset: int,
    ) -> list[ThemeRecord]:
        return self.themes.get(user.id, [])[offset : offset + limit]

    async def delete_account(self, user: AuthenticatedUser) -> None:
        self.deleted_users.append(user.id)
        self.settings.pop(user.id, None)
        self.memories.pop(user.id, None)
        self.conversations.pop(user.id, None)
        self.profiles.pop(user.id, None)
        self.themes.pop(user.id, None)


@pytest.fixture(autouse=True)
def clear_overrides() -> Any:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def authorize(
    fake: InMemoryDataControlPersistence,
    active_user: dict[str, UUID],
) -> None:
    def current_user() -> AuthenticatedUser:
        return AuthenticatedUser(
            id=active_user["id"],
            access_token=f"token-{active_user['id']}",
        )

    app.dependency_overrides[require_authenticated_user] = current_user
    app.dependency_overrides[get_persistence] = lambda: fake


def test_data_control_requires_login_and_rejects_forged_fields() -> None:
    client = TestClient(app)

    logged_out = client.get("/data-control")
    forged = client.patch(
        "/data-control/memory",
        json={"enabled": True, "user_id": str(uuid4())},
    )

    assert logged_out.status_code == 401
    assert forged.status_code == 401


def test_memory_is_default_off_then_exact_source_is_versioned_and_deletable() -> None:
    fake = InMemoryDataControlPersistence()
    user_id = uuid4()
    active_user = {"id": user_id}
    source_id = uuid4()
    fake.sources[(user_id, source_id)] = "这是需要完整保留的原话。"
    authorize(fake, active_user)
    client = TestClient(app)

    initial = client.get("/data-control")
    blocked = client.post(
        "/data-control/memories",
        json={
            "source_message_id": str(source_id),
            "kind": "reflection",
            "content": "这是需要完整保留的原话。",
            "confidence": "low",
        },
    )
    enabled = client.patch("/data-control/memory", json={"enabled": True})
    forged = client.post(
        "/data-control/memories",
        json={
            "source_message_id": str(source_id),
            "kind": "reflection",
            "content": "删掉否定语境的改写",
            "confidence": "low",
        },
    )
    saved = client.post(
        "/data-control/memories",
        json={
            "source_message_id": str(source_id),
            "kind": "reflection",
            "content": "这是需要完整保留的原话。",
            "confidence": "low",
        },
    )

    assert initial.status_code == 200
    assert initial.json()["memory_enabled"] is False
    assert initial.json()["stored_memories_used_as_model_context"] is False
    assert blocked.status_code == 409
    assert enabled.status_code == 200
    assert enabled.json()["memory_enabled"] is True
    assert forged.status_code == 409
    assert saved.status_code == 201
    assert "user_id" not in saved.json()
    assert saved.json()["original_content"] == "这是需要完整保留的原话。"

    memory_id = saved.json()["id"]
    lineage_id = saved.json()["lineage_id"]
    revised = client.post(
        f"/data-control/memories/{memory_id}/revisions",
        json={"expected_version": 1, "content": "这是我主动确认的新版本。"},
    )
    paused = client.patch(
        f"/data-control/memories/{revised.json()['id']}/status",
        json={"status": "paused"},
    )
    deleted = client.delete(f"/data-control/memories/{lineage_id}")

    assert revised.status_code == 200
    assert revised.json()["version"] == 2
    assert revised.json()["version_origin"] == "user_revision"
    assert revised.json()["original_content"] == "这是需要完整保留的原话。"
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert deleted.status_code == 204
    assert fake.memories[user_id] == []


def test_two_users_are_isolated_and_account_deletion_leaves_the_other_user() -> None:
    fake = InMemoryDataControlPersistence()
    user_a = uuid4()
    user_b = uuid4()
    active_user = {"id": user_a}
    source_a = uuid4()
    source_b = uuid4()
    fake.sources[(user_a, source_a)] = "A 的原话"
    fake.sources[(user_b, source_b)] = "B 的原话"
    fake.profiles[user_a] = ProfileExportRecord(
        display_name="用户 A",
        created_at=NOW,
        updated_at=NOW,
    )
    fake.profiles[user_b] = ProfileExportRecord(
        display_name="用户 B",
        created_at=NOW,
        updated_at=NOW,
    )
    fake.themes[user_a] = [
        ThemeRecord(
            id=uuid4(),
            title="A 的主题",
            status="exploring",
            created_at=NOW,
            updated_at=NOW,
        )
    ]
    fake.themes[user_b] = [
        ThemeRecord(
            id=uuid4(),
            title="B 的主题",
            status="paused",
            created_at=NOW,
            updated_at=NOW,
        )
    ]
    authorize(fake, active_user)
    client = TestClient(app)

    for user_id, source_id, content in (
        (user_a, source_a, "A 的原话"),
        (user_b, source_b, "B 的原话"),
    ):
        active_user["id"] = user_id
        assert client.patch("/data-control/memory", json={"enabled": True}).status_code == 200
        assert client.post(
            "/data-control/memories",
            json={
                "source_message_id": str(source_id),
                "kind": "experience",
                "content": content,
                "confidence": "low",
            },
        ).status_code == 201

    memory_b = fake.memories[user_b][0]
    active_user["id"] = user_a
    assert client.post(
        f"/data-control/memories/{memory_b.id}/revisions",
        json={"expected_version": 1, "content": "越权修改"},
    ).status_code == 404
    assert client.patch(
        f"/data-control/memories/{memory_b.id}/status",
        json={"status": "paused"},
    ).status_code == 404
    assert client.delete(
        f"/data-control/memories/{memory_b.lineage_id}"
    ).status_code == 404
    assert [item["content"] for item in client.get("/data-control").json()["memories"]] == ["A 的原话"]

    exported = client.get("/data-control/export")
    deleted = client.request(
        "DELETE",
        "/data-control/account",
        json={"confirmation": "删除我的 PAS 账户"},
    )

    assert exported.status_code == 200
    assert exported.json()["user_id"] == str(user_a)
    assert "account_email" in exported.json()
    assert exported.json()["profile"]["display_name"] == "用户 A"
    assert [item["title"] for item in exported.json()["themes"]] == ["A 的主题"]
    assert [item["content"] for item in exported.json()["memory_versions"]] == ["A 的原话"]
    assert deleted.status_code == 204
    assert fake.deleted_users == [user_a]
    assert user_a not in fake.memories
    assert user_a not in fake.profiles
    assert user_a not in fake.themes
    assert fake.profiles[user_b].display_name == "用户 B"
    assert [item.title for item in fake.themes[user_b]] == ["B 的主题"]
    assert [item.content for item in fake.memories[user_b]] == ["B 的原话"]

    active_user["id"] = user_b
    assert [item["content"] for item in client.get("/data-control").json()["memories"]] == ["B 的原话"]


def test_account_delete_requires_exact_confirmation() -> None:
    fake = InMemoryDataControlPersistence()
    active_user = {"id": uuid4()}
    authorize(fake, active_user)

    response = TestClient(app).request(
        "DELETE",
        "/data-control/account",
        json={"confirmation": "删除账户"},
    )

    assert response.status_code == 422
    assert fake.deleted_users == []
