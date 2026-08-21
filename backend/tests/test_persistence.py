import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.auth import AuthenticatedUser
from app.persistence import (
    CURRENT_REVIEW_CONTRACT_VERSION,
    CURRENT_VERIFICATION_CONTRACT_VERSION,
    OWNED_TURN_LOCATOR_SELECT,
    PRIVATE_MESSAGE_SELECT,
    PUBLIC_MESSAGE_SELECT,
    MessageRecord,
    PersistenceConflict,
    PersistenceNotAllowed,
    PersistenceUnavailable,
    ResourceNotFound,
    SupabasePersistence,
    should_persist_response,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc).isoformat()


def message_provenance(
    role: str,
    *,
    legacy: bool = False,
    bounded_response_kind: str | None = None,
) -> dict[str, str | None]:
    if role != "assistant":
        return {
            "review_contract_version": None,
            "verification_contract_version": None,
            "bounded_response_kind": None,
        }
    if legacy:
        return {
            "review_contract_version": "legacy",
            "verification_contract_version": "legacy",
            "bounded_response_kind": None,
        }
    return {
        "review_contract_version": CURRENT_REVIEW_CONTRACT_VERSION,
        "verification_contract_version": CURRENT_VERIFICATION_CONTRACT_VERSION,
        "bounded_response_kind": bounded_response_kind,
    }


def conversation_row(conversation_id: UUID) -> dict[str, str | None]:
    return {
        "id": str(conversation_id),
        "title": "今天的探索",
        "status": "active",
        "created_at": NOW,
        "updated_at": NOW,
    }


def turn_locator_rows(
    conversation_id: UUID,
    turn_id: UUID,
) -> list[dict[str, str]]:
    return [
        {
            "conversation_id": str(conversation_id),
            "client_turn_id": str(turn_id),
            "role": role,
        }
        for role in ("user", "assistant")
    ]


def private_rows(
    user_id: UUID,
    rows: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    return [{**row, "user_id": str(user_id)} for row in rows]


def test_conversation_reads_are_user_scoped_and_rls_authenticated() -> None:
    user_id = uuid4()
    conversation_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/v1/conversations"
        assert request.headers["apikey"] == "publishable-key"
        assert request.headers["authorization"] == "Bearer user-token"
        assert request.url.params["user_id"] == f"eq.{user_id}"
        return httpx.Response(200, json=[conversation_row(conversation_id)])

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    rows = asyncio.run(persistence.list_conversations(user))

    assert [row.id for row in rows] == [conversation_id]


def test_current_provenance_is_excluded_from_public_message_serialization() -> None:
    message = MessageRecord(
        id=uuid4(),
        conversation_id=uuid4(),
        client_turn_id=uuid4(),
        role="assistant",
        content="公开回应",
        response_source="review",
        support_mode="reflection",
        risk_level="none",
        review_contract_version="2",
        verification_contract_version="2",
        bounded_response_kind="unavailable_cross_chat_context",
        created_at=NOW,
    )

    payload = message.model_dump(mode="json")

    assert payload["content"] == "公开回应"
    assert "review_contract_version" not in payload
    assert "verification_contract_version" not in payload
    assert "bounded_response_kind" not in payload


def test_verifier_v1_turn_is_history_only_and_cannot_enter_current_context() -> None:
    conversation_id = uuid4()
    turn_id = uuid4()
    rows = [
        MessageRecord(
            id=uuid4(),
            conversation_id=conversation_id,
            client_turn_id=turn_id,
            role="user",
            content="旧版用户表达",
            created_at=NOW,
        ),
        MessageRecord(
            id=uuid4(),
            conversation_id=conversation_id,
            client_turn_id=turn_id,
            role="assistant",
            content="旧版 v1 回应",
            response_source="review",
            support_mode="reflection",
            risk_level="none",
            review_contract_version="2",
            verification_contract_version="1",
            created_at=NOW,
        ),
    ]

    assert SupabasePersistence._complete_reviewed_turn_messages(
        rows,
        current_contracts_only=True,
    ) == []
    assert SupabasePersistence._complete_reviewed_turn_messages(rows) == rows


def test_existing_reviewed_turn_is_returned_without_any_write() -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    turn_id = uuid4()
    user_message_id = uuid4()
    assistant_message_id = uuid4()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        assert request.method == "GET"
        if request.url.path.endswith("/conversations"):
            assert request.headers["authorization"] == "Bearer user-token"
            return httpx.Response(200, json=[conversation_row(conversation_id)])
        if request.url.params["select"] == OWNED_TURN_LOCATOR_SELECT:
            assert request.headers["authorization"] == "Bearer user-token"
            assert "user_id" not in request.url.params
            return httpx.Response(
                200,
                json=turn_locator_rows(conversation_id, turn_id),
            )
        assert request.url.params["select"] == PRIVATE_MESSAGE_SELECT
        assert request.headers["apikey"] == "sb_secret_test"
        assert "authorization" not in request.headers
        assert request.url.params["user_id"] == f"eq.{user_id}"
        assert request.url.params["conversation_id"] == f"eq.{conversation_id}"
        assert request.url.params["client_turn_id"] == f"eq.{turn_id}"
        assert request.url.params["limit"] == "3"
        return httpx.Response(
            200,
            json=private_rows(
                user_id,
                [
                    {
                        "id": str(user_message_id),
                        "conversation_id": str(conversation_id),
                        "client_turn_id": str(turn_id),
                        "role": "user",
                        "content": "我想整理今天。",
                        "response_source": None,
                        "support_mode": None,
                        "risk_level": None,
                        **message_provenance("user"),
                        "created_at": NOW,
                    },
                    {
                        "id": str(assistant_message_id),
                        "conversation_id": str(conversation_id),
                        "client_turn_id": str(turn_id),
                        "role": "assistant",
                        "content": "你想先从哪一部分开始？",
                        "response_source": "review",
                        "support_mode": "reflection",
                        "risk_level": "none",
                        **message_provenance("assistant"),
                        "created_at": NOW,
                    },
                ],
            ),
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    saved = asyncio.run(
        persistence.get_saved_turn(
            user,
            conversation_id=conversation_id,
            client_turn_id=turn_id,
            user_content="我想整理今天。",
        )
    )

    assert saved is not None
    assert saved.user_message_id == user_message_id
    assert saved.assistant_message_id == assistant_message_id
    assert saved.already_saved is True
    assert calls == ["GET", "GET", "GET"]


def test_legacy_single_review_turn_cannot_replay_as_current_success() -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    turn_id = uuid4()
    calls: list[str] = []

    message_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal message_reads
        calls.append(request.method)
        assert request.method == "GET"
        message_reads += 1
        if request.url.params["select"] == OWNED_TURN_LOCATOR_SELECT:
            assert request.headers["authorization"] == "Bearer user-token"
            return httpx.Response(
                200,
                json=turn_locator_rows(conversation_id, turn_id),
            )
        assert request.url.params["select"] == PRIVATE_MESSAGE_SELECT
        assert request.headers["apikey"] == "sb_secret_test"
        return httpx.Response(
            200,
            json=private_rows(user_id, [
                {
                    "id": str(uuid4()),
                    "conversation_id": str(conversation_id),
                    "client_turn_id": str(turn_id),
                    "role": "user",
                    "content": "旧版原文",
                    "response_source": None,
                    "support_mode": None,
                    "risk_level": None,
                    **message_provenance("user"),
                    "created_at": NOW,
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(conversation_id),
                    "client_turn_id": str(turn_id),
                    "role": "assistant",
                    "content": "只经过旧版单门 Review 的回应",
                    "response_source": "review",
                    "support_mode": "reflection",
                    "risk_level": "none",
                    **message_provenance("assistant", legacy=True),
                    "created_at": NOW,
                },
            ]),
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    with pytest.raises(PersistenceConflict, match="current release contracts"):
        asyncio.run(
            persistence.get_saved_turn(
                user,
                client_turn_id=turn_id,
                user_content="旧版原文",
            )
        )

    assert message_reads == 2
    assert calls == ["GET", "GET"]


def test_turn_lookup_is_global_before_rejecting_a_different_conversation() -> None:
    user_id = uuid4()
    requested_conversation_id = uuid4()
    existing_conversation_id = uuid4()
    turn_id = uuid4()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/conversations"):
            assert request.url.params["id"] == f"eq.{requested_conversation_id}"
            return httpx.Response(
                200,
                json=[conversation_row(requested_conversation_id)],
            )

        assert request.url.path.endswith("/messages")
        assert request.url.params["client_turn_id"] == f"eq.{turn_id}"
        assert "conversation_id" not in request.url.params
        return httpx.Response(
            200,
            json=turn_locator_rows(existing_conversation_id, turn_id),
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    with pytest.raises(PersistenceConflict, match="expected conversation"):
        asyncio.run(
            persistence.get_saved_turn(
                user,
                conversation_id=requested_conversation_id,
                client_turn_id=turn_id,
                user_content="旧版原文",
            )
        )

    assert len(calls) == 2


def test_turn_id_reuse_with_different_content_is_rejected() -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    turn_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/conversations"):
            return httpx.Response(200, json=[conversation_row(conversation_id)])
        if request.url.params["select"] == OWNED_TURN_LOCATOR_SELECT:
            return httpx.Response(
                200,
                json=turn_locator_rows(conversation_id, turn_id),
            )
        return httpx.Response(
            200,
            json=private_rows(user_id, [
                {
                    "id": str(uuid4()),
                    "conversation_id": str(conversation_id),
                    "client_turn_id": str(turn_id),
                    "role": "user",
                    "content": "原来的表达",
                    "response_source": None,
                    "support_mode": None,
                    "risk_level": None,
                    **message_provenance("user"),
                    "created_at": NOW,
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(conversation_id),
                    "client_turn_id": str(turn_id),
                    "role": "assistant",
                    "content": "审核后的回应",
                    "response_source": "review",
                    "support_mode": "reflection",
                    "risk_level": "none",
                    **message_provenance("assistant"),
                    "created_at": NOW,
                },
            ]),
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    with pytest.raises(PersistenceConflict):
        asyncio.run(
            persistence.get_saved_turn(
                user,
                conversation_id=conversation_id,
                client_turn_id=turn_id,
                user_content="不同的表达",
            )
        )


def test_rls_hidden_turn_never_reaches_the_private_read_channel() -> None:
    user_id = uuid4()
    turn_id = uuid4()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path.endswith("/messages")
        assert request.url.params["select"] == OWNED_TURN_LOCATOR_SELECT
        assert request.headers["authorization"] == "Bearer user-token"
        assert request.headers["apikey"] == "publishable-key"
        assert "user_id" not in request.url.params
        return httpx.Response(200, json=[])

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    saved = asyncio.run(
        persistence.get_saved_turn(
            user,
            client_turn_id=turn_id,
            user_content="另一个用户的原文",
        )
    )

    assert saved is None
    assert len(requests) == 1


def test_private_turn_read_rejects_rows_outside_verified_user_scope() -> None:
    user_id = uuid4()
    other_user_id = uuid4()
    conversation_id = uuid4()
    turn_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["select"] == OWNED_TURN_LOCATOR_SELECT:
            return httpx.Response(
                200,
                json=turn_locator_rows(conversation_id, turn_id),
            )
        assert request.url.params["select"] == PRIVATE_MESSAGE_SELECT
        assert request.url.params["user_id"] == f"eq.{user_id}"
        return httpx.Response(
            200,
            json=private_rows(
                other_user_id,
                [
                    {
                        "id": str(uuid4()),
                        "conversation_id": str(conversation_id),
                        "client_turn_id": str(turn_id),
                        "role": "user",
                        "content": "原文",
                        "response_source": None,
                        "support_mode": None,
                        "risk_level": None,
                        **message_provenance("user"),
                        "created_at": NOW,
                    },
                    {
                        "id": str(uuid4()),
                        "conversation_id": str(conversation_id),
                        "client_turn_id": str(turn_id),
                        "role": "assistant",
                        "content": "回应",
                        "response_source": "review",
                        "support_mode": "reflection",
                        "risk_level": "none",
                        **message_provenance("assistant"),
                        "created_at": NOW,
                    },
                ],
            ),
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    with pytest.raises(PersistenceConflict, match="ownership scope"):
        asyncio.run(
            persistence.get_saved_turn(
                user,
                client_turn_id=turn_id,
                user_content="原文",
            )
        )


def test_context_for_non_owner_fails_before_private_read() -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path.endswith("/conversations")
        assert request.headers["authorization"] == "Bearer user-token"
        return httpx.Response(200, json=[])

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    with pytest.raises(ResourceNotFound, match="Conversation not found"):
        asyncio.run(persistence.list_context_messages(user, conversation_id))

    assert len(requests) == 1


def test_private_context_without_server_secret_fails_without_network() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("A private read without a secret must fail closed.")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=uuid4(), access_token="user-token")

    with pytest.raises(PersistenceUnavailable):
        asyncio.run(persistence.list_context_messages(user, uuid4()))


def test_model_context_is_newest_first_at_storage_but_returned_as_complete_turns() -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    newest_turn_id = uuid4()
    older_turn_id = uuid4()
    legacy_turn_id = uuid4()

    def row(
        *,
        role: str,
        content: str,
        turn_id: UUID,
        legacy: bool = False,
        bounded_response_kind: str | None = None,
    ) -> dict[str, str | None]:
        return {
            "id": str(uuid4()),
            "conversation_id": str(conversation_id),
            "user_id": str(user_id),
            "client_turn_id": str(turn_id),
            "role": role,
            "content": content,
            "response_source": "review" if role == "assistant" else None,
            "support_mode": "reflection" if role == "assistant" else None,
            "risk_level": "none" if role == "assistant" else None,
            **message_provenance(
                role,
                legacy=legacy and role == "assistant",
                bounded_response_kind=bounded_response_kind,
            ),
            "created_at": NOW,
        }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/conversations"):
            assert request.headers["authorization"] == "Bearer user-token"
            return httpx.Response(200, json=[conversation_row(conversation_id)])
        assert request.headers["apikey"] == "sb_secret_test"
        assert "authorization" not in request.headers
        assert request.url.params["select"] == PRIVATE_MESSAGE_SELECT
        assert request.url.params["user_id"] == f"eq.{user_id}"
        assert request.url.params["conversation_id"] == f"eq.{conversation_id}"
        assert request.url.params["client_turn_id"] == "not.is.null"
        assert request.url.params["role"] == "in.(user,assistant)"
        assert request.url.params["order"] == "created_at.desc,role.asc,id.desc"
        assert request.url.params["limit"] == "12"
        return httpx.Response(
            200,
            json=[
                row(
                    role="assistant",
                    content="新回应",
                    turn_id=newest_turn_id,
                    bounded_response_kind="unavailable_cross_chat_context",
                ),
                row(role="user", content="新表达", turn_id=newest_turn_id),
                row(role="assistant", content="旧回应", turn_id=older_turn_id),
                row(role="user", content="旧表达", turn_id=older_turn_id),
                row(
                    role="assistant",
                    content="旧版单门回应",
                    turn_id=legacy_turn_id,
                    legacy=True,
                ),
                row(
                    role="user",
                    content="旧版单门表达",
                    turn_id=legacy_turn_id,
                    legacy=True,
                ),
            ],
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    messages = asyncio.run(
        persistence.list_context_messages(user, conversation_id)
    )

    assert [(message.role, message.content) for message in messages] == [
        ("user", "旧表达"),
        ("assistant", "旧回应"),
        ("user", "新表达"),
        ("assistant", "新回应"),
    ]


def test_history_preserves_legacy_reviewed_turns_and_excludes_orphans() -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    reviewed_turn_id = uuid4()
    orphan_turn_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer user-token"
        assert request.url.params["select"] == PUBLIC_MESSAGE_SELECT
        assert "user_id" not in request.url.params
        assert "review_contract_version" not in request.url.params["select"]
        assert "verification_contract_version" not in request.url.params["select"]
        assert "bounded_response_kind" not in request.url.params["select"]
        assert request.url.params["order"] == "created_at.desc,role.asc,id.desc"
        assert request.url.params["limit"] == "400"
        return httpx.Response(
            200,
            json=[
                {
                    "id": str(uuid4()),
                    "conversation_id": str(conversation_id),
                    "client_turn_id": str(orphan_turn_id),
                    "role": "user",
                    "content": "孤立的客户端写入",
                    "response_source": None,
                    "support_mode": None,
                    "risk_level": None,
                    "created_at": NOW,
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(conversation_id),
                    "client_turn_id": str(reviewed_turn_id),
                    "role": "user",
                    "content": "完整原话",
                    "response_source": None,
                    "support_mode": None,
                    "risk_level": None,
                    "created_at": NOW,
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(conversation_id),
                    "client_turn_id": str(reviewed_turn_id),
                    "role": "assistant",
                    "content": "已审核回应",
                    "response_source": "review",
                    "support_mode": "reflection",
                    "risk_level": "none",
                    "created_at": NOW,
                },
            ],
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    messages = asyncio.run(persistence.list_messages(user, conversation_id))

    assert [message.content for message in messages] == ["完整原话", "已审核回应"]


def test_history_keeps_each_turn_adjacent_when_timestamps_collide() -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    turn_a = uuid4()
    turn_b = uuid4()

    def row(role: str, content: str, turn_id: UUID) -> dict[str, str | None]:
        return {
            "id": str(uuid4()),
            "conversation_id": str(conversation_id),
            "client_turn_id": str(turn_id),
            "role": role,
            "content": content,
            "response_source": "review" if role == "assistant" else None,
            "support_mode": "reflection" if role == "assistant" else None,
            "risk_level": "none" if role == "assistant" else None,
            "created_at": NOW,
        }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                row("assistant", "A 回应", turn_a),
                row("assistant", "B 回应", turn_b),
                row("user", "A 原文", turn_a),
                row("user", "B 原文", turn_b),
            ],
        )

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    messages = asyncio.run(persistence.list_messages(user, conversation_id))

    contents = [message.content for message in messages]
    assert contents in (
        ["A 原文", "A 回应", "B 原文", "B 回应"],
        ["B 原文", "B 回应", "A 原文", "A 回应"],
    )


@pytest.mark.parametrize(
    (
        "response_source",
        "support_mode",
        "risk_level",
        "review_contract_version",
        "verification_contract_version",
        "bounded_response_kind",
        "expected",
    ),
    [
        ("review", "reflection", "none", "2", "2", None, True),
        (
            "review",
            "reflection",
            "none",
            "2",
            "2",
            "single_chat_diagnostic_request",
            True,
        ),
        (
            "review",
            "reflection",
            "none",
            "2",
            "2",
            "unavailable_cross_chat_context",
            True,
        ),
        ("review", "reflection", "none", "2", "1", None, False),
        ("review", "reflection", "none", "legacy", "legacy", None, False),
        ("review", "reflection", "none", "2", "legacy", None, False),
        ("review", "reflection", "none", "2", "2", "unknown_kind", False),
        ("safety_guard", "support", "urgent", "2", "2", None, False),
        (
            "review_safety_envelope",
            "support",
            "concerning",
            "2",
            "2",
            None,
            False,
        ),
        ("safe_fallback", "support", None, "2", "2", None, False),
    ],
)
def test_only_normal_reviewed_response_is_persistable(
    response_source: str,
    support_mode: str,
    risk_level: str | None,
    review_contract_version: str,
    verification_contract_version: str,
    bounded_response_kind: str | None,
    expected: bool,
) -> None:
    assert (
        should_persist_response(
            response_source=response_source,
            support_mode=support_mode,
            risk_level=risk_level,
            review_contract_version=review_contract_version,
            verification_contract_version=verification_contract_version,
            bounded_response_kind=bounded_response_kind,
        )
        is expected
    )


@pytest.mark.parametrize(
    "bounded_kind",
    ["third_party_private_state", "unavailable_cross_chat_context"],
)
def test_save_reviewed_turn_bulk_inserts_only_public_pair(
    bounded_kind: str,
) -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    turn_id = uuid4()
    user_message_id = uuid4()
    assistant_message_id = uuid4()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path.endswith("/messages"):
            return httpx.Response(200, json=[])
        if request.method == "GET" and request.url.path.endswith("/conversations"):
            return httpx.Response(200, json=[conversation_row(conversation_id)])
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/messages"
        assert request.headers["apikey"] == "sb_secret_test"
        assert "authorization" not in request.headers
        payload = json.loads(request.content)
        assert isinstance(payload, list) and len(payload) == 2
        assert {row["role"] for row in payload} == {"user", "assistant"}
        assert all(row["user_id"] == str(user_id) for row in payload)
        assert all(row["conversation_id"] == str(conversation_id) for row in payload)
        assert all(row["client_turn_id"] == str(turn_id) for row in payload)
        assert set(payload[0]) == set(payload[1])
        user_row = next(row for row in payload if row["role"] == "user")
        assistant_row = next(row for row in payload if row["role"] == "assistant")
        assert user_row["response_source"] is None
        assert user_row["support_mode"] is None
        assert user_row["risk_level"] is None
        assert user_row["review_contract_version"] is None
        assert user_row["verification_contract_version"] is None
        assert user_row["bounded_response_kind"] is None
        assert assistant_row["review_contract_version"] == "2"
        assert assistant_row["verification_contract_version"] == "2"
        assert assistant_row["bounded_response_kind"] == bounded_kind
        assert "SENTINEL_DRAFT" not in request.content.decode()
        assert "SENTINEL_RATIONALE" not in request.content.decode()

        returned = []
        for row in payload:
            returned.append(
                {
                    **row,
                    "id": str(
                        user_message_id
                        if row["role"] == "user"
                        else assistant_message_id
                    ),
                }
            )
        return httpx.Response(201, json=returned)

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    saved = asyncio.run(
        persistence.save_reviewed_turn(
            user,
            conversation_id=conversation_id,
            client_turn_id=turn_id,
            user_message="用户实际原文",
            final_response="Review 后最终回复",
            response_source="review",
            support_mode="reflection",
            risk_level="none",
            review_contract_version=CURRENT_REVIEW_CONTRACT_VERSION,
            verification_contract_version=CURRENT_VERIFICATION_CONTRACT_VERSION,
            bounded_response_kind=bounded_kind,
        )
    )

    assert saved.already_saved is False
    assert saved.user_message_id == user_message_id
    assert saved.assistant_message_id == assistant_message_id
    assert [request.method for request in requests] == ["GET", "GET", "POST"]


def test_save_reviewed_turn_rejects_support_before_any_network_call() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Support content must never reach persistence.")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("server-secret"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=uuid4(), access_token="user-token")

    with pytest.raises(PersistenceNotAllowed):
        asyncio.run(
            persistence.save_reviewed_turn(
                user,
                client_turn_id=uuid4(),
                user_message="高风险原文",
                final_response="固定安全支持回复",
                response_source="safety_guard",
                support_mode="support",
                risk_level="urgent",
                review_contract_version=CURRENT_REVIEW_CONTRACT_VERSION,
                verification_contract_version=CURRENT_VERIFICATION_CONTRACT_VERSION,
                bounded_response_kind=None,
            )
        )


def test_missing_server_secret_fails_before_creating_conversation() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        assert request.method == "GET"
        return httpx.Response(200, json=[])

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=uuid4(), access_token="user-token")

    with pytest.raises(PersistenceUnavailable):
        asyncio.run(
            persistence.save_reviewed_turn(
                user,
                client_turn_id=uuid4(),
                user_message="普通表达",
                final_response="审核后回应",
                response_source="review",
                support_mode="reflection",
                risk_level="none",
                review_contract_version=CURRENT_REVIEW_CONTRACT_VERSION,
                verification_contract_version=CURRENT_VERIFICATION_CONTRACT_VERSION,
                bounded_response_kind=None,
                conversation_title="普通表达",
            )
        )

    assert methods == []


def test_failed_first_turn_write_removes_the_empty_conversation() -> None:
    user_id = uuid4()
    conversation_id: UUID | None = None
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json=[])
        if request.method == "POST" and request.url.path.endswith("/conversations"):
            nonlocal conversation_id
            conversation_id = UUID(json.loads(request.content)["id"])
            return httpx.Response(201, json=[conversation_row(conversation_id)])
        if request.method == "POST" and request.url.path.endswith("/messages"):
            return httpx.Response(503, json={"message": "unavailable"})
        if request.method == "DELETE":
            assert conversation_id is not None
            return httpx.Response(200, json=[conversation_row(conversation_id)])
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("server-secret"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    with pytest.raises(PersistenceUnavailable):
        asyncio.run(
            persistence.save_reviewed_turn(
                user,
                client_turn_id=uuid4(),
                user_message="普通表达",
                final_response="审核后回应",
                response_source="review",
                support_mode="reflection",
                risk_level="none",
                review_contract_version=CURRENT_REVIEW_CONTRACT_VERSION,
                verification_contract_version=CURRENT_VERIFICATION_CONTRACT_VERSION,
                bounded_response_kind=None,
                conversation_title="普通表达",
            )
        )

    assert methods == ["GET", "POST", "POST", "GET", "DELETE"]


def test_concurrent_first_turn_returns_winner_and_cleans_temporary_conversation() -> None:
    user_id = uuid4()
    winner_conversation_id = uuid4()
    turn_id = uuid4()
    winner_user_id = uuid4()
    winner_assistant_id = uuid4()
    temporary_conversation_id: UUID | None = None
    message_reads = 0
    methods: list[str] = []

    def winner_rows() -> list[dict[str, str | None]]:
        return [
            {
                "id": str(winner_user_id),
                "conversation_id": str(winner_conversation_id),
                "client_turn_id": str(turn_id),
                "role": "user",
                "content": "同一条普通表达",
                "response_source": None,
                "support_mode": None,
                "risk_level": None,
                **message_provenance("user"),
                "created_at": NOW,
            },
            {
                "id": str(winner_assistant_id),
                "conversation_id": str(winner_conversation_id),
                "client_turn_id": str(turn_id),
                "role": "assistant",
                "content": "赢家的审核后回应",
                "response_source": "review",
                "support_mode": "reflection",
                "risk_level": "none",
                **message_provenance("assistant"),
                "created_at": NOW,
            },
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal message_reads, temporary_conversation_id
        methods.append(request.method)
        if request.method == "GET" and request.url.path.endswith("/messages"):
            if request.url.params["select"] == OWNED_TURN_LOCATOR_SELECT:
                message_reads += 1
                return httpx.Response(
                    200,
                    json=(
                        []
                        if message_reads == 1
                        else turn_locator_rows(winner_conversation_id, turn_id)
                    ),
                )
            assert request.url.params["select"] == PRIVATE_MESSAGE_SELECT
            assert request.headers["apikey"] == "sb_secret_test"
            assert request.url.params["user_id"] == f"eq.{user_id}"
            assert (
                request.url.params["conversation_id"]
                == f"eq.{winner_conversation_id}"
            )
            return httpx.Response(
                200,
                json=private_rows(user_id, winner_rows()),
            )
        if request.method == "POST" and request.url.path.endswith("/conversations"):
            temporary_conversation_id = UUID(json.loads(request.content)["id"])
            return httpx.Response(
                201,
                json=[conversation_row(temporary_conversation_id)],
            )
        if request.method == "POST" and request.url.path.endswith("/messages"):
            return httpx.Response(409, json={"message": "duplicate"})
        if request.method == "DELETE":
            assert temporary_conversation_id is not None
            return httpx.Response(
                200,
                json=[conversation_row(temporary_conversation_id)],
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    saved = asyncio.run(
        persistence.save_reviewed_turn(
            user,
            client_turn_id=turn_id,
            user_message="同一条普通表达",
            final_response="输家的审核后回应",
            response_source="review",
            support_mode="reflection",
            risk_level="none",
            review_contract_version=CURRENT_REVIEW_CONTRACT_VERSION,
            verification_contract_version=CURRENT_VERIFICATION_CONTRACT_VERSION,
            bounded_response_kind=None,
            conversation_title="同一条普通表达",
        )
    )

    assert saved.already_saved is True
    assert saved.conversation_id == winner_conversation_id
    assert saved.response == "赢家的审核后回应"
    assert methods == ["GET", "POST", "POST", "GET", "GET", "DELETE"]


def test_ambiguous_write_recovers_committed_turn_without_deleting_it() -> None:
    user_id = uuid4()
    turn_id = uuid4()
    conversation_id: UUID | None = None
    committed_rows: list[dict[str, str | None]] = []
    message_reads = 0
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal conversation_id, committed_rows, message_reads
        methods.append(request.method)
        if request.method == "GET" and request.url.path.endswith("/messages"):
            if request.url.params["select"] == OWNED_TURN_LOCATOR_SELECT:
                message_reads += 1
                return httpx.Response(
                    200,
                    json=(
                        []
                        if message_reads == 1
                        else turn_locator_rows(conversation_id, turn_id)
                    ),
                )
            assert request.url.params["select"] == PRIVATE_MESSAGE_SELECT
            assert conversation_id is not None
            return httpx.Response(
                200,
                json=private_rows(user_id, committed_rows),
            )
        if request.method == "POST" and request.url.path.endswith("/conversations"):
            conversation_id = UUID(json.loads(request.content)["id"])
            return httpx.Response(201, json=[conversation_row(conversation_id)])
        if request.method == "POST" and request.url.path.endswith("/messages"):
            assert conversation_id is not None
            payload = json.loads(request.content)
            committed_rows = [
                {**row, "id": str(uuid4())}
                for row in payload
            ]
            raise httpx.ReadTimeout("response lost", request=request)
        if request.method == "DELETE":
            raise AssertionError("A confirmed committed turn must not be deleted.")
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    saved = asyncio.run(
        persistence.save_reviewed_turn(
            user,
            client_turn_id=turn_id,
            user_message="普通表达",
            final_response="审核后回应",
            response_source="review",
            support_mode="reflection",
            risk_level="none",
            review_contract_version=CURRENT_REVIEW_CONTRACT_VERSION,
            verification_contract_version=CURRENT_VERIFICATION_CONTRACT_VERSION,
            bounded_response_kind=None,
            conversation_title="普通表达",
        )
    )

    assert saved.already_saved is True
    assert saved.conversation_id == conversation_id
    assert methods == ["GET", "POST", "POST", "GET", "GET"]


def test_success_response_cannot_replace_the_review_final() -> None:
    user_id = uuid4()
    conversation_id = uuid4()
    turn_id = uuid4()
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "GET" and request.url.path.endswith("/messages"):
            return httpx.Response(200, json=[])
        if request.method == "GET" and request.url.path.endswith("/conversations"):
            return httpx.Response(200, json=[conversation_row(conversation_id)])
        if request.method == "POST" and request.url.path.endswith("/messages"):
            payload = json.loads(request.content)
            payload[1]["content"] = "ALTERED_NOT_REVIEW_FINAL"
            return httpx.Response(
                201,
                json=[{**row, "id": str(uuid4())} for row in payload],
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    persistence = SupabasePersistence(
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-key",
        secret_key=SecretStr("sb_secret_test"),
        transport=httpx.MockTransport(handler),
    )
    user = AuthenticatedUser(id=user_id, access_token="user-token")

    with pytest.raises(PersistenceConflict):
        asyncio.run(
            persistence.save_reviewed_turn(
                user,
                conversation_id=conversation_id,
                client_turn_id=turn_id,
                user_message="普通表达",
                final_response="REVIEW_FINAL",
                response_source="review",
                support_mode="reflection",
                risk_level="none",
                review_contract_version=CURRENT_REVIEW_CONTRACT_VERSION,
                verification_contract_version=CURRENT_VERIFICATION_CONTRACT_VERSION,
                bounded_response_kind=None,
            )
        )

    assert methods == ["GET", "GET", "POST"]
