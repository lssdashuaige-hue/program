from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.auth import AuthenticatedUser, require_authenticated_user
from app.persistence import (
    ConversationRecord,
    ConversationStatus,
    MessageRecord,
    PersistenceConflict,
    PersistenceUnauthorized,
    PersistenceUnavailable,
    SupabasePersistence,
    get_persistence,
)


router = APIRouter(prefix="/conversations", tags=["conversation history"])
CurrentUser = Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
Persistence = Annotated[SupabasePersistence, Depends(get_persistence)]


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Conversation title cannot be empty.")
        return normalized


class UpdateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)
    status: ConversationStatus | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Conversation title cannot be empty.")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "UpdateConversationRequest":
        if not self.model_fields_set:
            raise ValueError("At least one conversation field is required.")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("Conversation status cannot be null.")
        return self


class ConversationListResponse(BaseModel):
    items: list[ConversationRecord]


class MessageListResponse(BaseModel):
    conversation_id: UUID
    items: list[MessageRecord]


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="没有找到这段探索记录。",
    )


def _translate_persistence_error(error: Exception) -> HTTPException:
    if isinstance(error, PersistenceUnauthorized):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已经失效，请重新登录。",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if isinstance(error, PersistenceConflict):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="这次操作与已经保存的记录冲突，请刷新后重试。",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="PAS 暂时无法访问探索记录，请稍后重试。",
    )


@router.post("", response_model=ConversationRecord, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: CreateConversationRequest,
    user: CurrentUser,
    persistence: Persistence,
) -> ConversationRecord:
    try:
        return await persistence.create_conversation(user, title=request.title)
    except (PersistenceUnauthorized, PersistenceUnavailable, PersistenceConflict) as error:
        raise _translate_persistence_error(error) from error


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    user: CurrentUser,
    persistence: Persistence,
    status_filter: Annotated[
        ConversationStatus | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> ConversationListResponse:
    try:
        items = await persistence.list_conversations(
            user,
            conversation_status=status_filter,
            limit=limit,
            offset=offset,
        )
    except (PersistenceUnauthorized, PersistenceUnavailable, PersistenceConflict) as error:
        raise _translate_persistence_error(error) from error
    return ConversationListResponse(items=items)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def list_conversation_messages(
    conversation_id: UUID,
    user: CurrentUser,
    persistence: Persistence,
) -> MessageListResponse:
    try:
        conversation = await persistence.get_conversation(user, conversation_id)
        if conversation is None:
            raise _not_found()
        items = await persistence.list_messages(user, conversation_id)
    except HTTPException:
        raise
    except (PersistenceUnauthorized, PersistenceUnavailable, PersistenceConflict) as error:
        raise _translate_persistence_error(error) from error
    return MessageListResponse(conversation_id=conversation_id, items=items)


@router.get("/{conversation_id}", response_model=ConversationRecord)
async def get_conversation(
    conversation_id: UUID,
    user: CurrentUser,
    persistence: Persistence,
) -> ConversationRecord:
    try:
        conversation = await persistence.get_conversation(user, conversation_id)
    except (PersistenceUnauthorized, PersistenceUnavailable, PersistenceConflict) as error:
        raise _translate_persistence_error(error) from error
    if conversation is None:
        raise _not_found()
    return conversation


@router.patch("/{conversation_id}", response_model=ConversationRecord)
async def update_conversation(
    conversation_id: UUID,
    request: UpdateConversationRequest,
    user: CurrentUser,
    persistence: Persistence,
) -> ConversationRecord:
    changes: dict[str, Any] = request.model_dump(exclude_unset=True)
    try:
        conversation = await persistence.update_conversation(
            user,
            conversation_id,
            changes,
        )
    except (PersistenceUnauthorized, PersistenceUnavailable, PersistenceConflict) as error:
        raise _translate_persistence_error(error) from error
    if conversation is None:
        raise _not_found()
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    user: CurrentUser,
    persistence: Persistence,
) -> Response:
    try:
        deleted = await persistence.delete_conversation(user, conversation_id)
    except (PersistenceUnauthorized, PersistenceUnavailable, PersistenceConflict) as error:
        raise _translate_persistence_error(error) from error
    if not deleted:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
