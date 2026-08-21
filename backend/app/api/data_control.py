from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import AuthenticatedUser, require_authenticated_user
from app.config import Settings, get_settings
from app.persistence import (
    ConversationRecord,
    MemoryConfidence,
    MemoryKind,
    MemoryRecord,
    MemorySettingsRecord,
    MessageRecord,
    PersistenceConflict,
    PersistenceNotAllowed,
    PersistenceUnauthorized,
    PersistenceUnavailable,
    ProfileExportRecord,
    ResourceNotFound,
    SupabasePersistence,
    ThemeRecord,
    get_persistence,
)


router = APIRouter(prefix="/data-control", tags=["data control"])
CurrentUser = Annotated[AuthenticatedUser, Depends(require_authenticated_user)]
Persistence = Annotated[SupabasePersistence, Depends(get_persistence)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
MAX_EXPORT_CONVERSATIONS = 5_000
MAX_EXPORT_MEMORIES = 5_000
MAX_EXPORT_THEMES = 5_000
ACCOUNT_DELETE_CONFIRMATION = "删除我的 PAS 账户"


class MemorySettingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class ConfirmMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_message_id: UUID
    kind: MemoryKind
    content: str = Field(min_length=1, max_length=8000)
    confidence: MemoryConfidence

    @field_validator("content")
    @classmethod
    def require_visible_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A confirmed memory cannot be blank.")
        return value


class ReviseMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def require_visible_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A memory revision cannot be blank.")
        return value


class MemoryStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "paused"]


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["删除我的 PAS 账户"]


class DataControlState(BaseModel):
    memory_enabled: bool
    memory_enabled_at: datetime | None
    memory_feature_available: bool
    temporary_sessions_supported: Literal[True] = True
    stored_memories_used_as_model_context: Literal[False] = False
    memories: list[MemoryRecord]


class ExportedConversation(BaseModel):
    conversation: ConversationRecord
    messages: list[MessageRecord]


class UserDataExport(BaseModel):
    schema_version: Literal["1"] = "1"
    exported_at: datetime
    user_id: UUID
    account_email: str | None
    profile: ProfileExportRecord | None
    memory_setting: MemorySettingsRecord
    conversations: list[ExportedConversation]
    memory_versions: list[MemoryRecord]
    themes: list[ThemeRecord]
    scope_note: str = (
        "This export contains active PAS database records only. It does not "
        "claim deletion or export of provider logs, backups, or files already "
        "downloaded to a user-controlled device."
    )


def _translate_error(error: Exception) -> HTTPException:
    if isinstance(error, PersistenceUnauthorized):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已经失效，请重新登录。",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if isinstance(error, ResourceNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到这条属于你的记录。",
        )
    if isinstance(error, PersistenceConflict):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="这条记录已经发生变化，请刷新后重试。",
        )
    if isinstance(error, PersistenceNotAllowed):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前数据控制状态不允许这次保存。",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="PAS 暂时无法完成这项数据控制操作，请稍后重试。",
    )


async def _all_conversations(
    persistence: SupabasePersistence,
    user: AuthenticatedUser,
) -> list[ConversationRecord]:
    items: list[ConversationRecord] = []
    while len(items) < MAX_EXPORT_CONVERSATIONS:
        batch = await persistence.list_conversations(
            user,
            limit=100,
            offset=len(items),
        )
        items.extend(batch)
        if len(batch) < 100:
            return items
    raise PersistenceUnavailable("The account export is too large to complete safely.")


async def _all_memories(
    persistence: SupabasePersistence,
    user: AuthenticatedUser,
) -> list[MemoryRecord]:
    items: list[MemoryRecord] = []
    while len(items) < MAX_EXPORT_MEMORIES:
        batch = await persistence.list_memories(
            user,
            limit=100,
            offset=len(items),
        )
        items.extend(batch)
        if len(batch) < 100:
            return items
    raise PersistenceUnavailable("The memory export is too large to complete safely.")


async def _all_themes(
    persistence: SupabasePersistence,
    user: AuthenticatedUser,
) -> list[ThemeRecord]:
    items: list[ThemeRecord] = []
    while len(items) < MAX_EXPORT_THEMES:
        batch = await persistence.list_themes(
            user,
            limit=100,
            offset=len(items),
        )
        items.extend(batch)
        if len(batch) < 100:
            return items
    raise PersistenceUnavailable("The theme export is too large to complete safely.")


@router.get("", response_model=DataControlState)
async def get_data_control_state(
    user: CurrentUser,
    persistence: Persistence,
    settings: CurrentSettings,
) -> DataControlState:
    try:
        memory_setting = await persistence.get_memory_settings(user)
        memories = await _all_memories(persistence, user)
    except (
        PersistenceConflict,
        PersistenceUnauthorized,
        PersistenceUnavailable,
    ) as error:
        raise _translate_error(error) from error
    return DataControlState(
        memory_enabled=memory_setting.memory_enabled,
        memory_enabled_at=memory_setting.memory_enabled_at,
        memory_feature_available=settings.memory_agent_enabled,
        memories=memories,
    )


@router.patch("/memory", response_model=MemorySettingsRecord)
async def update_memory_setting(
    request: MemorySettingRequest,
    user: CurrentUser,
    persistence: Persistence,
) -> MemorySettingsRecord:
    try:
        return await persistence.set_memory_enabled(user, enabled=request.enabled)
    except (
        PersistenceConflict,
        PersistenceUnauthorized,
        PersistenceUnavailable,
    ) as error:
        raise _translate_error(error) from error


@router.post(
    "/memories",
    response_model=MemoryRecord,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_memory(
    request: ConfirmMemoryRequest,
    user: CurrentUser,
    persistence: Persistence,
) -> MemoryRecord:
    try:
        return await persistence.create_confirmed_memory(
            user,
            source_message_id=request.source_message_id,
            kind=request.kind,
            content=request.content,
            confidence=request.confidence,
        )
    except (
        PersistenceConflict,
        PersistenceNotAllowed,
        PersistenceUnauthorized,
        PersistenceUnavailable,
        ResourceNotFound,
    ) as error:
        raise _translate_error(error) from error


@router.post("/memories/{memory_id}/revisions", response_model=MemoryRecord)
async def revise_memory(
    memory_id: UUID,
    request: ReviseMemoryRequest,
    user: CurrentUser,
    persistence: Persistence,
) -> MemoryRecord:
    try:
        memory = await persistence.revise_memory(
            user,
            memory_id=memory_id,
            expected_version=request.expected_version,
            content=request.content,
        )
    except (
        PersistenceConflict,
        PersistenceNotAllowed,
        PersistenceUnauthorized,
        PersistenceUnavailable,
    ) as error:
        raise _translate_error(error) from error
    if memory is None:
        raise _translate_error(ResourceNotFound("Memory not found."))
    return memory


@router.patch("/memories/{memory_id}/status", response_model=MemoryRecord)
async def update_memory_status(
    memory_id: UUID,
    request: MemoryStatusRequest,
    user: CurrentUser,
    persistence: Persistence,
) -> MemoryRecord:
    try:
        memory = await persistence.set_memory_status(
            user,
            memory_id=memory_id,
            memory_status=request.status,
        )
    except (
        PersistenceConflict,
        PersistenceUnauthorized,
        PersistenceUnavailable,
    ) as error:
        raise _translate_error(error) from error
    if memory is None:
        raise _translate_error(ResourceNotFound("Memory not found."))
    return memory


@router.delete(
    "/memories/{lineage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_memory(
    lineage_id: UUID,
    user: CurrentUser,
    persistence: Persistence,
) -> Response:
    try:
        deleted = await persistence.delete_memory_lineage(user, lineage_id)
    except (
        PersistenceConflict,
        PersistenceUnauthorized,
        PersistenceUnavailable,
    ) as error:
        raise _translate_error(error) from error
    if not deleted:
        raise _translate_error(ResourceNotFound("Memory not found."))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export", response_model=UserDataExport)
async def export_user_data(
    response: Response,
    user: CurrentUser,
    persistence: Persistence,
) -> UserDataExport:
    try:
        profile = await persistence.get_export_profile(user)
        memory_setting = await persistence.get_memory_settings(user)
        conversations = await _all_conversations(persistence, user)
        exported_conversations = [
            ExportedConversation(
                conversation=conversation,
                messages=await persistence.list_export_messages(
                    user,
                    conversation.id,
                ),
            )
            for conversation in conversations
        ]
        memories = await _all_memories(persistence, user)
        themes = await _all_themes(persistence, user)
    except (
        PersistenceConflict,
        PersistenceUnauthorized,
        PersistenceUnavailable,
    ) as error:
        raise _translate_error(error) from error

    response.headers["Content-Disposition"] = (
        'attachment; filename="pas-data-export.json"'
    )
    response.headers["Cache-Control"] = "no-store"
    return UserDataExport(
        exported_at=datetime.now(timezone.utc),
        user_id=user.id,
        account_email=user.email,
        profile=profile,
        memory_setting=memory_setting,
        conversations=exported_conversations,
        memory_versions=memories,
        themes=themes,
    )


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    request: DeleteAccountRequest,
    user: CurrentUser,
    persistence: Persistence,
) -> Response:
    if request.confirmation != ACCOUNT_DELETE_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="账户删除确认文字不匹配。",
        )
    try:
        await persistence.delete_account(user)
    except (PersistenceUnauthorized, PersistenceUnavailable) as error:
        raise _translate_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
