import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.auth import AuthenticatedUser
from app.persistence import (
    PersistenceNotAllowed,
    ResourceNotFound,
    SupabasePersistence,
)


NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)


def memory_row(
    *,
    memory_id: UUID,
    user_id: UUID,
    source_id: UUID,
    content: str,
) -> dict[str, object]:
    return {
        "id": str(memory_id),
        "user_id": str(user_id),
        "lineage_id": str(memory_id),
        "source_message_id": str(source_id),
        "supersedes_id": None,
        "kind": "reflection",
        "content": content,
        "original_content": content,
        "confidence": "low",
        "confirmed": True,
        "status": "active",
        "version": 1,
        "version_origin": "source_quote",
        "confirmed_at": NOW.isoformat(),
        "paused_at": None,
        "superseded_at": None,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }


def user_message_row(
    *,
    message_id: UUID,
    conversation_id: UUID,
    content: str,
) -> dict[str, object]:
    return {
        "id": str(message_id),
        "conversation_id": str(conversation_id),
        "client_turn_id": str(uuid4()),
        "role": "user",
        "content": content,
        "response_source": None,
        "support_mode": None,
        "risk_level": None,
        "created_at": NOW.isoformat(),
    }


def test_confirmed_memory_uses_user_rls_and_exact_source_wording() -> None:
    user_id = uuid4()
    other_user_id = uuid4()
    source_id = uuid4()
    conversation_id = uuid4()
    seen_posts: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer user-token"
        assert request.headers["apikey"] == "publishable-key"
        if request.url.path.endswith("/profiles"):
            return httpx.Response(
                200,
                json=[
                    {
                        "memory_enabled": True,
                        "memory_enabled_at": NOW.isoformat(),
                        "updated_at": NOW.isoformat(),
                    }
                ],
            )
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json=[
                    user_message_row(
                        message_id=source_id,
                        conversation_id=conversation_id,
                        content="完整保留：我不是不在意。",
                    )
                ],
            )
        if request.url.path.endswith("/memories") and request.method == "POST":
            payload = json.loads(request.content)
            seen_posts.append(payload)
            return httpx.Response(
                201,
                json=[
                    memory_row(
                        memory_id=UUID(payload["id"]),
                        user_id=user_id,
                        source_id=source_id,
                        content=payload["content"],
                    )
                ],
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_server"),
        transport=httpx.MockTransport(handler),
    )
    memory = asyncio.run(
        persistence.create_confirmed_memory(
            AuthenticatedUser(id=user_id, access_token="user-token"),
            source_message_id=source_id,
            kind="reflection",
            content="完整保留：我不是不在意。",
            confidence="low",
        )
    )

    assert memory.user_id == user_id
    assert memory.original_content == "完整保留：我不是不在意。"
    assert seen_posts[0]["user_id"] == str(user_id)
    assert seen_posts[0]["lineage_id"] == seen_posts[0]["id"]
    assert str(other_user_id) not in str(seen_posts)


def test_memory_enablement_uses_the_narrow_server_timestamp_rpc() -> None:
    user_id = uuid4()
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/rpc/set_memory_enabled")
        assert request.headers["authorization"] == "Bearer user-token"
        assert request.headers["apikey"] == "publishable-key"
        payload = json.loads(request.content)
        seen_payloads.append(payload)
        return httpx.Response(
            200,
            json=[
                {
                    "memory_enabled": payload["p_enabled"],
                    "memory_enabled_at": NOW.isoformat(),
                    "updated_at": NOW.isoformat(),
                }
            ],
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_server"),
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(
        persistence.set_memory_enabled(
            AuthenticatedUser(id=user_id, access_token="user-token"),
            enabled=True,
        )
    )

    assert result.memory_enabled is True
    assert result.memory_enabled_at == NOW
    assert seen_payloads == [{"p_enabled": True}]


def test_export_profile_and_themes_stay_inside_user_rls_scope() -> None:
    user_id = uuid4()
    theme_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer user-token"
        assert request.headers["apikey"] == "publishable-key"
        if request.url.path.endswith("/profiles"):
            assert request.url.params["id"] == f"eq.{user_id}"
            return httpx.Response(
                200,
                json=[
                    {
                        "display_name": "当前用户",
                        "created_at": NOW.isoformat(),
                        "updated_at": NOW.isoformat(),
                    }
                ],
            )
        if request.url.path.endswith("/themes"):
            assert request.url.params["user_id"] == f"eq.{user_id}"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(theme_id),
                        "title": "当前用户的主题",
                        "status": "exploring",
                        "created_at": NOW.isoformat(),
                        "updated_at": NOW.isoformat(),
                    }
                ],
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_server"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    profile = asyncio.run(persistence.get_export_profile(user))
    themes = asyncio.run(persistence.list_themes(user))

    assert profile is not None
    assert profile.display_name == "当前用户"
    assert [(item.id, item.title) for item in themes] == [
        (theme_id, "当前用户的主题")
    ]


def test_lineage_delete_verifies_the_final_state_instead_of_a_stale_count() -> None:
    user_id = uuid4()
    memory_id = uuid4()
    source_id = uuid4()
    lineage_id = memory_id

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer user-token"
        if request.url.path.endswith("/memories"):
            assert request.url.params["user_id"] == f"eq.{user_id}"
            if request.url.params["select"] == "id":
                return httpx.Response(200, json=[])
            return httpx.Response(
                200,
                json=[
                    memory_row(
                        memory_id=memory_id,
                        user_id=user_id,
                        source_id=source_id,
                        content="待删除的原话",
                    )
                ],
            )
        if request.url.path.endswith("/rpc/delete_memory_lineage"):
            assert json.loads(request.content) == {
                "p_lineage_id": str(lineage_id)
            }
            # A concurrent revision can make the atomic RPC delete more rows
            # than the stale pre-read observed. The verified empty final state
            # is the authoritative success condition.
            return httpx.Response(200, json=2)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_server"),
        transport=httpx.MockTransport(handler),
    )

    deleted = asyncio.run(
        persistence.delete_memory_lineage(
            AuthenticatedUser(id=user_id, access_token="user-token"),
            lineage_id,
        )
    )

    assert deleted is True


def test_confirmed_memory_rejects_changed_or_hidden_source_before_write() -> None:
    user_id = uuid4()
    source_id = uuid4()
    source_visible = True
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.url.path.endswith("/profiles"):
            return httpx.Response(200, json=[{"memory_enabled": True}])
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json=(
                    [
                        user_message_row(
                            message_id=source_id,
                            conversation_id=uuid4(),
                            content="原始否定仍然保留",
                        )
                    ]
                    if source_visible
                    else []
                ),
            )
        if request.url.path.endswith("/memories"):
            posts += 1
            return httpx.Response(500)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_server"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    with pytest.raises(PersistenceNotAllowed):
        asyncio.run(
            persistence.create_confirmed_memory(
                user,
                source_message_id=source_id,
                kind="reflection",
                content="删除否定后的改写",
                confidence="low",
            )
        )
    source_visible = False
    with pytest.raises(ResourceNotFound):
        asyncio.run(
            persistence.create_confirmed_memory(
                user,
                source_message_id=source_id,
                kind="reflection",
                content="原始否定仍然保留",
                confidence="low",
            )
        )
    assert posts == 0


def test_memory_read_for_one_user_cannot_return_another_users_row() -> None:
    user_a = uuid4()
    user_b = uuid4()
    memory_b = uuid4()
    source_b = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["user_id"] == f"eq.{user_a}"
        assert request.headers["authorization"] == "Bearer token-a"
        if request.url.params["id"] == f"eq.{memory_b}":
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json=[
                memory_row(
                    memory_id=uuid4(),
                    user_id=user_a,
                    source_id=source_b,
                    content="A 的内容",
                )
            ],
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_server"),
        transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(
        persistence.get_memory(
            AuthenticatedUser(id=user_a, access_token="token-a"),
            memory_b,
        )
    ) is None
    assert user_a != user_b


def test_account_delete_uses_server_secret_and_verifies_only_target_removed() -> None:
    user_a = uuid4()
    user_b = uuid4()
    auth_users = {user_a, user_b}
    active_rows = {user_a: 4, user_b: 3}
    delete_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal delete_requests
        assert request.headers["apikey"] == "sb_secret_server"
        assert "authorization" not in request.headers
        if request.method == "DELETE" and "/auth/v1/admin/users/" in request.url.path:
            delete_requests += 1
            assert request.url.path.endswith(str(user_a))
            assert json.loads(request.content) == {"should_soft_delete": False}
            auth_users.remove(user_a)
            active_rows[user_a] = 0
            return httpx.Response(200, json={"id": str(user_a)})
        if request.url.path.endswith(f"/auth/v1/admin/users/{user_a}"):
            return httpx.Response(404, json={"message": "not found"})
        if "/rest/v1/" in request.url.path:
            owner_filter = request.url.params.get("user_id") or request.url.params.get("id")
            assert owner_filter == f"eq.{user_a}"
            return httpx.Response(200, json=[])
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_server"),
        transport=httpx.MockTransport(handler),
    )
    asyncio.run(
        persistence.delete_account(
            AuthenticatedUser(id=user_a, access_token="token-a")
        )
    )

    assert delete_requests == 1
    assert user_a not in auth_users
    assert active_rows[user_a] == 0
    assert user_b in auth_users
    assert active_rows[user_b] == 3
