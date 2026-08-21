from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Mapping
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr

from app.auth import AuthenticatedUser
from app.config import Settings, get_settings


PERSISTENCE_REQUEST_TIMEOUT_SECONDS = 8.0
MAX_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARACTERS = 16_000
MAX_HISTORY_MESSAGES = 400
ConversationStatus = Literal["active", "archived"]
MessageRole = Literal["user", "assistant", "system"]
StoredResponseSource = Literal["review"]
StoredSupportMode = Literal["reflection"]
StoredRiskLevel = Literal["none"]
StoredReviewContractVersion = Literal["legacy", "2"]
StoredVerificationContractVersion = Literal["legacy", "1", "2"]
StoredBoundedResponseKind = Literal[
    "third_party_private_state",
    "single_chat_diagnostic_request",
    "personal_lifespan_conversion",
    "unavailable_cross_chat_context",
]
CURRENT_REVIEW_CONTRACT_VERSION: Literal["2"] = "2"
CURRENT_VERIFICATION_CONTRACT_VERSION: Literal["2"] = "2"
PUBLIC_MESSAGE_SELECT = (
    "id,conversation_id,client_turn_id,role,content,"
    "response_source,support_mode,risk_level,created_at"
)
PRIVATE_MESSAGE_SELECT = (
    "id,conversation_id,user_id,client_turn_id,role,content,"
    "response_source,support_mode,risk_level,"
    "review_contract_version,verification_contract_version,"
    "bounded_response_kind,created_at"
)
OWNED_TURN_LOCATOR_SELECT = "conversation_id,client_turn_id,role"


class PersistenceUnavailable(RuntimeError):
    """Raised when PAS cannot safely read or write durable user data."""


class PersistenceUnauthorized(RuntimeError):
    """Raised when Supabase rejects a user-scoped database request."""


class PersistenceConflict(RuntimeError):
    """Raised when a client turn ID is reused for different content."""


class PersistenceNotAllowed(RuntimeError):
    """Raised when a response lacks the current durable release provenance."""


class ResourceNotFound(RuntimeError):
    """Raised for a missing resource or one hidden by RLS."""


class ConversationRecord(BaseModel):
    id: UUID
    title: str | None = None
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime


class MessageRecord(BaseModel):
    id: UUID
    conversation_id: UUID
    client_turn_id: UUID | None = None
    role: MessageRole
    content: str
    response_source: StoredResponseSource | None = None
    support_mode: StoredSupportMode | None = None
    risk_level: StoredRiskLevel | None = None
    review_contract_version: StoredReviewContractVersion | None = Field(
        default=None,
        exclude=True,
    )
    verification_contract_version: StoredVerificationContractVersion | None = Field(
        default=None,
        exclude=True,
    )
    bounded_response_kind: StoredBoundedResponseKind | None = Field(
        default=None,
        exclude=True,
    )
    created_at: datetime


class PrivateMessageRecord(MessageRecord):
    """Server-only message shape used to validate durable release provenance."""

    user_id: UUID = Field(exclude=True)


class OwnedTurnLocator(BaseModel):
    """Public-column projection used only to prove ownership through RLS."""

    conversation_id: UUID
    client_turn_id: UUID
    role: MessageRole


@dataclass(frozen=True, slots=True)
class SavedReviewedTurn:
    conversation_id: UUID
    client_turn_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    response: str
    already_saved: bool = True


def should_persist_response(
    *,
    response_source: str,
    support_mode: str,
    risk_level: str | None,
    review_contract_version: str,
    verification_contract_version: str,
    bounded_response_kind: str | None,
) -> bool:
    """Return true only for a normal response released by both current gates."""

    return (
        response_source == "review"
        and support_mode == "reflection"
        and risk_level == "none"
        and review_contract_version == CURRENT_REVIEW_CONTRACT_VERSION
        and verification_contract_version
        == CURRENT_VERIFICATION_CONTRACT_VERSION
        and bounded_response_kind
        in {
            None,
            "third_party_private_state",
            "single_chat_diagnostic_request",
            "personal_lifespan_conversion",
            "unavailable_cross_chat_context",
        }
    )


class SupabasePersistence:
    """RLS-scoped public reads plus narrow server-only provenance access."""

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        secret_key: SecretStr | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._supabase_url = supabase_url.rstrip("/")
        self._publishable_key = publishable_key
        self._secret_key = secret_key
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: Settings) -> "SupabasePersistence":
        if not settings.supabase_url or not settings.supabase_publishable_key:
            raise PersistenceUnavailable("Supabase persistence is not configured.")
        return cls(
            supabase_url=settings.supabase_url,
            publishable_key=settings.supabase_publishable_key,
            secret_key=settings.supabase_secret_key,
        )

    def _user_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "apikey": self._publishable_key,
            "Authorization": f"Bearer {access_token}",
        }

    def _secret_headers(self) -> dict[str, str]:
        if self._secret_key is None:
            raise PersistenceUnavailable(
                "The server-side Supabase key is not configured."
            )
        secret = self._secret_key.get_secret_value()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
            "apikey": secret,
        }
        if not secret.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    async def _insert_reviewed_turn(
        self,
        *,
        user: AuthenticatedUser,
        conversation_id: UUID,
        client_turn_id: UUID,
        user_message: str,
        final_response: str,
        review_contract_version: Literal["2"],
        verification_contract_version: Literal["2"],
        bounded_response_kind: StoredBoundedResponseKind | None,
    ) -> httpx.Response:
        """Insert one public reviewed turn with the server-only credential.

        This deliberately narrow method accepts only the two public message
        strings and their release provenance scalars. Agent drafts, Review
        rationale, verification rationale, and memory decisions cannot cross
        this boundary.
        """

        created_at = datetime.now(timezone.utc)
        rows = [
            {
                "conversation_id": str(conversation_id),
                "user_id": str(user.id),
                "client_turn_id": str(client_turn_id),
                "role": "user",
                "content": user_message,
                "response_source": None,
                "support_mode": None,
                "risk_level": None,
                "review_contract_version": None,
                "verification_contract_version": None,
                "bounded_response_kind": None,
                "created_at": created_at.isoformat(),
            },
            {
                "conversation_id": str(conversation_id),
                "user_id": str(user.id),
                "client_turn_id": str(client_turn_id),
                "role": "assistant",
                "content": final_response,
                "response_source": "review",
                "support_mode": "reflection",
                "risk_level": "none",
                "review_contract_version": review_contract_version,
                "verification_contract_version": verification_contract_version,
                "bounded_response_kind": bounded_response_kind,
                "created_at": (created_at + timedelta(microseconds=1)).isoformat(),
            },
        ]
        try:
            async with httpx.AsyncClient(
                timeout=PERSISTENCE_REQUEST_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                return await client.post(
                    f"{self._supabase_url}/rest/v1/messages",
                    headers=self._secret_headers(),
                    json=rows,
                )
        except httpx.RequestError as error:
            raise PersistenceUnavailable(
                "Supabase persistence could not save the reviewed turn."
            ) from error

    async def _request(
        self,
        method: str,
        resource: str,
        *,
        access_token: str,
        params: Mapping[str, str | int] | None = None,
        json_body: Any | None = None,
        return_representation: bool = False,
    ) -> httpx.Response:
        headers = self._user_headers(access_token)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if return_representation:
            headers["Prefer"] = "return=representation"

        request_kwargs: dict[str, Any] = {
            "headers": headers,
            "params": params,
        }
        if json_body is not None:
            request_kwargs["json"] = json_body

        try:
            async with httpx.AsyncClient(
                timeout=PERSISTENCE_REQUEST_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                return await client.request(
                    method,
                    f"{self._supabase_url}/rest/v1/{resource}",
                    **request_kwargs,
                )
        except httpx.RequestError as error:
            raise PersistenceUnavailable(
                "Supabase persistence could not be reached."
            ) from error

    async def _read_private_messages(
        self,
        *,
        user: AuthenticatedUser,
        conversation_id: UUID,
        client_turn_id: UUID | None = None,
        context_only: bool = False,
    ) -> list[PrivateMessageRecord]:
        """Read provenance only after an RLS-scoped ownership check.

        This is deliberately not a general service-role request method. It can
        read only messages for one already-verified user and conversation, and
        it always uses an explicit private projection.
        """

        if context_only == (client_turn_id is not None):
            raise ValueError(
                "A private message read must be either context or one saved turn."
            )

        params: dict[str, str | int] = {
            "select": PRIVATE_MESSAGE_SELECT,
            "conversation_id": f"eq.{conversation_id}",
            "user_id": f"eq.{user.id}",
            "client_turn_id": "not.is.null",
        }
        if context_only:
            params.update(
                {
                    "role": "in.(user,assistant)",
                    "order": "created_at.desc,role.asc,id.desc",
                    "limit": MAX_CONTEXT_MESSAGES,
                }
            )
        else:
            params.update(
                {
                    "client_turn_id": f"eq.{client_turn_id}",
                    "order": "role.desc,id.asc",
                    "limit": 3,
                }
            )

        try:
            async with httpx.AsyncClient(
                timeout=PERSISTENCE_REQUEST_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"{self._supabase_url}/rest/v1/messages",
                    headers=self._secret_headers(),
                    params=params,
                )
        except httpx.RequestError as error:
            raise PersistenceUnavailable(
                "Supabase could not read private message provenance."
            ) from error

        if response.status_code != status.HTTP_200_OK:
            raise PersistenceUnavailable(
                "Supabase rejected the private message provenance read."
            )
        rows = self._parse_rows(response, PrivateMessageRecord)
        if any(
            row.user_id != user.id
            or row.conversation_id != conversation_id
            or (
                client_turn_id is not None
                and row.client_turn_id != client_turn_id
            )
            for row in rows
        ):
            raise PersistenceConflict(
                "The private message read crossed its verified ownership scope."
            )
        return rows

    @staticmethod
    def _validate_status(
        response: httpx.Response,
        *,
        allowed: set[int],
    ) -> None:
        if response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }:
            raise PersistenceUnauthorized(
                "Supabase rejected the scoped persistence request."
            )
        if response.status_code == status.HTTP_409_CONFLICT:
            raise PersistenceConflict("The durable record already exists.")
        if response.status_code not in allowed:
            raise PersistenceUnavailable(
                "Supabase persistence returned an unexpected response."
            )

    @staticmethod
    def _parse_rows(
        response: httpx.Response,
        model: type[BaseModel],
    ) -> list[Any]:
        try:
            payload = response.json()
            if not isinstance(payload, list):
                raise TypeError("PostgREST response must be a list.")
            return [model.model_validate(item) for item in payload]
        except (TypeError, ValueError) as error:
            raise PersistenceUnavailable(
                "Supabase persistence returned invalid data."
            ) from error

    @staticmethod
    def _complete_reviewed_turn_messages(
        messages: list[MessageRecord],
        *,
        current_contracts_only: bool = False,
    ) -> list[MessageRecord]:
        grouped: dict[UUID, list[MessageRecord]] = {}
        for message in messages:
            if message.client_turn_id is None:
                continue
            grouped.setdefault(message.client_turn_id, []).append(message)

        reviewed: list[MessageRecord] = []
        for group in grouped.values():
            user_messages = [item for item in group if item.role == "user"]
            assistant_messages = [item for item in group if item.role == "assistant"]
            if len(group) != 2 or len(user_messages) != 1 or len(assistant_messages) != 1:
                continue
            user_message = user_messages[0]
            assistant_message = assistant_messages[0]
            if (
                user_message.conversation_id != assistant_message.conversation_id
                or user_message.response_source is not None
                or user_message.support_mode is not None
                or user_message.risk_level is not None
                or user_message.review_contract_version is not None
                or user_message.verification_contract_version is not None
                or user_message.bounded_response_kind is not None
                or assistant_message.response_source != "review"
                or assistant_message.support_mode != "reflection"
                or assistant_message.risk_level != "none"
            ):
                continue
            current_contracts = (
                assistant_message.review_contract_version
                == CURRENT_REVIEW_CONTRACT_VERSION
                and assistant_message.verification_contract_version
                == CURRENT_VERIFICATION_CONTRACT_VERSION
            )
            legacy_contracts = (
                (
                    assistant_message.review_contract_version == "legacy"
                    and assistant_message.verification_contract_version == "legacy"
                    and assistant_message.bounded_response_kind is None
                )
                or (
                    assistant_message.review_contract_version == "2"
                    and assistant_message.verification_contract_version == "1"
                )
            )
            if not current_contracts and (
                current_contracts_only or not legacy_contracts
            ):
                continue
            reviewed.extend((user_message, assistant_message))
        return reviewed

    @staticmethod
    def _complete_public_reviewed_turn_messages(
        messages: list[MessageRecord],
    ) -> list[MessageRecord]:
        """Keep complete public pairs after the database enforced provenance."""

        grouped: dict[UUID, list[MessageRecord]] = {}
        for message in messages:
            if message.client_turn_id is None:
                continue
            grouped.setdefault(message.client_turn_id, []).append(message)

        reviewed: list[MessageRecord] = []
        for group in grouped.values():
            user_messages = [item for item in group if item.role == "user"]
            assistant_messages = [item for item in group if item.role == "assistant"]
            if len(group) != 2 or len(user_messages) != 1 or len(assistant_messages) != 1:
                continue
            user_message = user_messages[0]
            assistant_message = assistant_messages[0]
            if (
                user_message.conversation_id != assistant_message.conversation_id
                or user_message.response_source is not None
                or user_message.support_mode is not None
                or user_message.risk_level is not None
                or assistant_message.response_source != "review"
                or assistant_message.support_mode != "reflection"
                or assistant_message.risk_level != "none"
            ):
                continue
            reviewed.extend((user_message, assistant_message))
        return reviewed

    async def _locate_owned_turn_conversation(
        self,
        user: AuthenticatedUser,
        client_turn_id: UUID,
    ) -> UUID | None:
        """Use the user's token and RLS to locate an owned durable turn."""

        response = await self._request(
            "GET",
            "messages",
            access_token=user.access_token,
            params={
                "select": OWNED_TURN_LOCATOR_SELECT,
                "client_turn_id": f"eq.{client_turn_id}",
                "order": "role.desc",
                "limit": 3,
            },
        )
        self._validate_status(response, allowed={status.HTTP_200_OK})
        locators = self._parse_rows(response, OwnedTurnLocator)
        if not locators:
            return None
        if any(item.client_turn_id != client_turn_id for item in locators):
            raise PersistenceConflict("The durable turn lookup returned another turn.")
        conversation_ids = {item.conversation_id for item in locators}
        if len(conversation_ids) != 1:
            raise PersistenceConflict(
                "The client turn ID belongs to multiple conversations."
            )
        return next(iter(conversation_ids))

    @staticmethod
    def _saved_turn_from_rows(
        rows: list[MessageRecord],
        *,
        client_turn_id: UUID,
        user_content: str,
        conversation_id: UUID | None,
        already_saved: bool,
        expected_response: str | None = None,
    ) -> SavedReviewedTurn:
        user_messages = [message for message in rows if message.role == "user"]
        assistant_messages = [
            message for message in rows if message.role == "assistant"
        ]
        if len(rows) != 2 or len(user_messages) != 1 or len(assistant_messages) != 1:
            raise PersistenceConflict("The durable turn is incomplete or ambiguous.")

        user_message = user_messages[0]
        assistant_message = assistant_messages[0]
        durable_conversation_id = user_message.conversation_id
        if (
            user_message.client_turn_id != client_turn_id
            or assistant_message.client_turn_id != client_turn_id
            or assistant_message.conversation_id != durable_conversation_id
            or (
                conversation_id is not None
                and durable_conversation_id != conversation_id
            )
        ):
            raise PersistenceConflict(
                "The durable turn does not belong to the expected conversation."
            )
        if user_message.content != user_content:
            raise PersistenceConflict(
                "The client turn ID belongs to different user content."
            )
        if (
            expected_response is not None
            and assistant_message.content != expected_response
        ):
            raise PersistenceConflict(
                "The saved assistant response does not match the reviewed response."
            )
        if (
            user_message.response_source is not None
            or user_message.support_mode is not None
            or user_message.risk_level is not None
            or user_message.review_contract_version is not None
            or user_message.verification_contract_version is not None
            or user_message.bounded_response_kind is not None
            or assistant_message.response_source != "review"
            or assistant_message.support_mode != "reflection"
            or assistant_message.risk_level != "none"
            or assistant_message.review_contract_version
            != CURRENT_REVIEW_CONTRACT_VERSION
            or assistant_message.verification_contract_version
            != CURRENT_VERIFICATION_CONTRACT_VERSION
        ):
            raise PersistenceConflict(
                "The existing turn did not pass the current release contracts."
            )

        return SavedReviewedTurn(
            conversation_id=durable_conversation_id,
            client_turn_id=client_turn_id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            response=assistant_message.content,
            already_saved=already_saved,
        )

    async def _cleanup_created_conversation(
        self,
        user: AuthenticatedUser,
        conversation_id: UUID,
    ) -> None:
        try:
            deleted = await self.delete_conversation(user, conversation_id)
        except (
            PersistenceConflict,
            PersistenceUnauthorized,
            PersistenceUnavailable,
        ) as error:
            raise PersistenceUnavailable(
                "PAS could not clean up an incomplete conversation."
            ) from error
        if not deleted:
            raise PersistenceUnavailable(
                "PAS could not clean up an incomplete conversation."
            )

    async def create_conversation(
        self,
        user: AuthenticatedUser,
        *,
        title: str | None,
    ) -> ConversationRecord:
        conversation_id = uuid4()
        try:
            response = await self._request(
                "POST",
                "conversations",
                access_token=user.access_token,
                json_body={
                    "id": str(conversation_id),
                    "user_id": str(user.id),
                    "title": title,
                    "status": "active",
                },
                return_representation=True,
            )
            self._validate_status(
                response,
                allowed={status.HTTP_200_OK, status.HTTP_201_CREATED},
            )
            rows = self._parse_rows(response, ConversationRecord)
            if len(rows) != 1 or rows[0].id != conversation_id:
                raise PersistenceUnavailable(
                    "Conversation creation returned an invalid record."
                )
            return rows[0]
        except PersistenceUnavailable as error:
            # The explicit ID lets PAS remove an ambiguously committed empty
            # conversation even when the create response was lost.
            try:
                await self.delete_conversation(user, conversation_id)
            except (
                PersistenceConflict,
                PersistenceUnauthorized,
                PersistenceUnavailable,
            ) as cleanup_error:
                raise PersistenceUnavailable(
                    "PAS could not reconcile an incomplete conversation create."
                ) from cleanup_error
            raise error

    async def list_conversations(
        self,
        user: AuthenticatedUser,
        *,
        conversation_status: ConversationStatus | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> list[ConversationRecord]:
        params: dict[str, str | int] = {
            "select": "id,title,status,created_at,updated_at",
            "user_id": f"eq.{user.id}",
            "order": "updated_at.desc,id.desc",
            "limit": limit,
            "offset": offset,
        }
        if conversation_status is not None:
            params["status"] = f"eq.{conversation_status}"

        response = await self._request(
            "GET",
            "conversations",
            access_token=user.access_token,
            params=params,
        )
        self._validate_status(response, allowed={status.HTTP_200_OK})
        return self._parse_rows(response, ConversationRecord)

    async def get_conversation(
        self,
        user: AuthenticatedUser,
        conversation_id: UUID,
    ) -> ConversationRecord | None:
        response = await self._request(
            "GET",
            "conversations",
            access_token=user.access_token,
            params={
                "select": "id,title,status,created_at,updated_at",
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user.id}",
                "limit": 1,
            },
        )
        self._validate_status(response, allowed={status.HTTP_200_OK})
        rows = self._parse_rows(response, ConversationRecord)
        return rows[0] if rows else None

    async def update_conversation(
        self,
        user: AuthenticatedUser,
        conversation_id: UUID,
        changes: Mapping[str, str | None],
    ) -> ConversationRecord | None:
        allowed_changes = {
            key: value
            for key, value in changes.items()
            if key in {"title", "status"}
        }
        if not allowed_changes or len(allowed_changes) != len(changes):
            raise ValueError("A conversation update requires only title or status.")

        response = await self._request(
            "PATCH",
            "conversations",
            access_token=user.access_token,
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user.id}",
            },
            json_body={
                **allowed_changes,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            return_representation=True,
        )
        self._validate_status(response, allowed={status.HTTP_200_OK})
        rows = self._parse_rows(response, ConversationRecord)
        return rows[0] if rows else None

    async def delete_conversation(
        self,
        user: AuthenticatedUser,
        conversation_id: UUID,
    ) -> bool:
        response = await self._request(
            "DELETE",
            "conversations",
            access_token=user.access_token,
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user.id}",
                "select": "id,title,status,created_at,updated_at",
            },
            return_representation=True,
        )
        self._validate_status(response, allowed={status.HTTP_200_OK})
        rows = self._parse_rows(response, ConversationRecord)
        return bool(rows)

    async def list_messages(
        self,
        user: AuthenticatedUser,
        conversation_id: UUID,
    ) -> list[MessageRecord]:
        response = await self._request(
            "GET",
            "messages",
            access_token=user.access_token,
            params={
                "select": PUBLIC_MESSAGE_SELECT,
                "conversation_id": f"eq.{conversation_id}",
                "client_turn_id": "not.is.null",
                "order": "created_at.desc,role.asc,id.desc",
                "limit": MAX_HISTORY_MESSAGES,
            },
        )
        self._validate_status(response, allowed={status.HTTP_200_OK})
        reviewed = self._complete_public_reviewed_turn_messages(
            self._parse_rows(response, MessageRecord)
        )
        newest_pairs = [
            reviewed[index : index + 2]
            for index in range(0, len(reviewed), 2)
        ]
        return [
            message
            for pair in reversed(newest_pairs)
            for message in pair
        ]

    async def list_context_messages(
        self,
        user: AuthenticatedUser,
        conversation_id: UUID,
    ) -> list[MessageRecord]:
        """Load only the newest reviewed turn context needed by the agents."""

        self._secret_headers()
        if await self.get_conversation(user, conversation_id) is None:
            raise ResourceNotFound("Conversation not found.")
        rows = await self._read_private_messages(
            user=user,
            conversation_id=conversation_id,
            context_only=True,
        )
        newest_first = self._complete_reviewed_turn_messages(
            list(reversed(rows)),
            current_contracts_only=True,
        )
        newest_first = list(reversed(newest_first))
        chronological = list(reversed(newest_first))

        selected_groups_reversed: list[list[MessageRecord]] = []
        used_characters = 0
        cursor = len(chronological) - 1
        while cursor >= 0:
            turn_id = chronological[cursor].client_turn_id
            group_reversed: list[MessageRecord] = []
            while cursor >= 0 and chronological[cursor].client_turn_id == turn_id:
                group_reversed.append(chronological[cursor])
                cursor -= 1
            group = list(reversed(group_reversed))
            group_characters = sum(len(message.content) for message in group)
            if used_characters + group_characters > MAX_CONTEXT_CHARACTERS:
                break
            selected_groups_reversed.append(group)
            used_characters += group_characters

        selected: list[MessageRecord] = []
        for group in reversed(selected_groups_reversed):
            selected.extend(group)
        return selected

    async def get_saved_turn(
        self,
        user: AuthenticatedUser,
        *,
        client_turn_id: UUID,
        user_content: str,
        conversation_id: UUID | None = None,
    ) -> SavedReviewedTurn | None:
        self._secret_headers()
        if (
            conversation_id is not None
            and await self.get_conversation(user, conversation_id) is None
        ):
            raise ResourceNotFound("Conversation not found.")

        owned_conversation_id = await self._locate_owned_turn_conversation(
            user,
            client_turn_id,
        )
        if owned_conversation_id is None:
            return None
        if (
            conversation_id is not None
            and owned_conversation_id != conversation_id
        ):
            raise PersistenceConflict(
                "The durable turn does not belong to the expected conversation."
            )
        rows = await self._read_private_messages(
            user=user,
            conversation_id=owned_conversation_id,
            client_turn_id=client_turn_id,
        )
        if not rows:
            raise PersistenceConflict(
                "The owned durable turn disappeared before provenance validation."
            )

        return self._saved_turn_from_rows(
            rows,
            client_turn_id=client_turn_id,
            user_content=user_content,
            conversation_id=owned_conversation_id,
            already_saved=True,
        )

    async def save_reviewed_turn(
        self,
        user: AuthenticatedUser,
        *,
        client_turn_id: UUID,
        user_message: str,
        final_response: str,
        response_source: str,
        support_mode: str,
        risk_level: str | None,
        review_contract_version: Literal["2"],
        verification_contract_version: Literal["2"],
        bounded_response_kind: StoredBoundedResponseKind | None,
        conversation_id: UUID | None = None,
        conversation_title: str | None = None,
    ) -> SavedReviewedTurn:
        """Persist exactly one normal dual-gate-released public turn."""

        if not should_persist_response(
            response_source=response_source,
            support_mode=support_mode,
            risk_level=risk_level,
            review_contract_version=review_contract_version,
            verification_contract_version=verification_contract_version,
            bounded_response_kind=bounded_response_kind,
        ):
            raise PersistenceNotAllowed(
                "Only a response released by the current Review and verification "
                "contracts may be persisted."
            )

        existing = await self.get_saved_turn(
            user,
            client_turn_id=client_turn_id,
            user_content=user_message,
        )
        if existing is not None:
            if (
                conversation_id is not None
                and existing.conversation_id != conversation_id
            ):
                raise PersistenceConflict(
                    "The client turn ID belongs to another conversation."
                )
            return existing

        # Fail before creating an empty conversation when the server-only
        # credential has not been configured.
        self._secret_headers()

        requested_conversation_id = conversation_id
        created_conversation_id: UUID | None = None
        if conversation_id is None:
            conversation = await self.create_conversation(
                user,
                title=conversation_title,
            )
            conversation_id = conversation.id
            created_conversation_id = conversation.id
        elif await self.get_conversation(user, conversation_id) is None:
            raise ResourceNotFound("Conversation not found.")

        async def cleanup_created_conversation() -> None:
            nonlocal created_conversation_id
            if created_conversation_id is None:
                return
            cleanup_id = created_conversation_id
            await self._cleanup_created_conversation(user, cleanup_id)
            created_conversation_id = None

        insert_attempted = False
        strict_response_mismatch = False
        try:
            insert_attempted = True
            response = await self._insert_reviewed_turn(
                user=user,
                conversation_id=conversation_id,
                client_turn_id=client_turn_id,
                user_message=user_message,
                final_response=final_response,
                review_contract_version=review_contract_version,
                verification_contract_version=verification_contract_version,
                bounded_response_kind=bounded_response_kind,
            )
            if response.status_code == status.HTTP_409_CONFLICT:
                winner = await self.get_saved_turn(
                    user,
                    client_turn_id=client_turn_id,
                    user_content=user_message,
                )
                if winner is None:
                    await cleanup_created_conversation()
                    raise PersistenceConflict(
                        "The reviewed turn conflicted with another durable write."
                    )
                if (
                    requested_conversation_id is not None
                    and winner.conversation_id != requested_conversation_id
                ):
                    await cleanup_created_conversation()
                    raise PersistenceConflict(
                        "The client turn ID belongs to another conversation."
                    )
                if created_conversation_id is not None:
                    if winner.conversation_id == created_conversation_id:
                        created_conversation_id = None
                    else:
                        await cleanup_created_conversation()
                return winner

            if response.status_code not in {
                status.HTTP_200_OK,
                status.HTTP_201_CREATED,
            }:
                raise PersistenceUnavailable(
                    "Supabase rejected the reviewed turn write."
                )
            rows = self._parse_rows(response, MessageRecord)
            try:
                return self._saved_turn_from_rows(
                    rows,
                    client_turn_id=client_turn_id,
                    user_content=user_message,
                    conversation_id=conversation_id,
                    already_saved=False,
                    expected_response=final_response,
                )
            except PersistenceConflict:
                strict_response_mismatch = True
                raise
        except (
            PersistenceConflict,
            PersistenceUnauthorized,
            PersistenceUnavailable,
        ) as error:
            if strict_response_mismatch:
                await cleanup_created_conversation()
                raise
            if insert_attempted:
                try:
                    recovered = await self.get_saved_turn(
                        user,
                        client_turn_id=client_turn_id,
                        user_content=user_message,
                    )
                except (PersistenceUnauthorized, PersistenceUnavailable) as lookup_error:
                    # Do not delete an ambiguously committed write when PAS cannot
                    # yet reconcile it. The same turn ID can recover it on retry.
                    raise PersistenceUnavailable(
                        "PAS could not confirm whether the reviewed turn was saved."
                    ) from lookup_error
                except PersistenceConflict:
                    # An existing but invalid/partial turn must not be silently
                    # deleted or treated as a completed reviewed response.
                    raise error

                if recovered is not None:
                    if (
                        requested_conversation_id is not None
                        and recovered.conversation_id
                        != requested_conversation_id
                    ):
                        await cleanup_created_conversation()
                        raise PersistenceConflict(
                            "The client turn ID belongs to another conversation."
                        ) from error
                    if created_conversation_id is not None:
                        if recovered.conversation_id == created_conversation_id:
                            created_conversation_id = None
                        else:
                            await cleanup_created_conversation()
                    return recovered

            await cleanup_created_conversation()
            raise


def get_persistence(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SupabasePersistence:
    try:
        return SupabasePersistence.from_settings(settings)
    except PersistenceUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAS 的探索记录服务尚未配置。",
        ) from error


def get_optional_persistence(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SupabasePersistence | None:
    """Keep anonymous chat independent from optional durable-history config."""

    try:
        return SupabasePersistence.from_settings(settings)
    except PersistenceUnavailable:
        return None
