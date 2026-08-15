import asyncio
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ai.context import ConversationContextMessage, ResponsePreference
from app.ai.gateway import DeepSeekChatGateway, OpenAIResponsesGateway
from app.ai.limits import PIPELINE_TIMEOUT_SECONDS
from app.ai.memory_agent import MemoryAgent
from app.ai.models import AgentMode, MemoryCandidate, ResponseSource, SupportMode
from app.ai.orchestrator import AgentPipelineError, MultiAgentOrchestrator
from app.ai.prompts import (
    memory_instructions,
    reflection_instructions,
    review_instructions,
)
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.ai.safety import preflight_safety_result, safe_fallback_result
from app.auth import optional_authenticated_user
from app.config import Settings, get_settings
from app.persistence import (
    PersistenceConflict,
    PersistenceNotAllowed,
    PersistenceUnauthorized,
    PersistenceUnavailable,
    ResourceNotFound,
    SavedReviewedTurn,
    SupabasePersistence,
    get_optional_persistence,
)

router = APIRouter(prefix="/chat", tags=["reflection"])
CHAT_TIMEOUT_SECONDS = PIPELINE_TIMEOUT_SECONDS


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)
    response_preference: ResponsePreference | None = None
    conversation_id: UUID | None = None
    client_turn_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def require_meaningful_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A chat message cannot contain only whitespace.")
        return value

    @model_validator(mode="after")
    def resumed_conversation_requires_turn_id(self) -> "ChatRequest":
        if self.conversation_id is not None and self.client_turn_id is None:
            raise ValueError("A resumed conversation requires a client turn ID.")
        return self


class PersistenceNotRequested(BaseModel):
    status: Literal["not_requested"] = "not_requested"


class PersistenceSaved(BaseModel):
    status: Literal["saved", "already_saved"]
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID


class PersistenceNotSaved(BaseModel):
    status: Literal["not_saved_support", "not_saved_fallback"]
    conversation_id: UUID | None = None


class PersistenceFailed(BaseModel):
    status: Literal["failed"] = "failed"
    conversation_id: UUID | None = None


PersistenceResult = (
    PersistenceNotRequested
    | PersistenceSaved
    | PersistenceNotSaved
    | PersistenceFailed
)


class ChatResponse(BaseModel):
    response: str
    mode: AgentMode
    support_mode: SupportMode
    response_source: ResponseSource
    persistence: PersistenceResult
    memory_candidate: MemoryCandidate | None = None


OptionalPersistence = Annotated[
    SupabasePersistence | None,
    Depends(get_optional_persistence),
]
ChatCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Security(HTTPBearer(auto_error=False)),
]
ChatSettings = Annotated[Settings, Depends(get_settings)]


def _conversation_title(message: str) -> str:
    normalized = " ".join(message.split())
    return f"{normalized[:36]}…" if len(normalized) > 36 else normalized


def _saved_persistence(saved: SavedReviewedTurn) -> PersistenceSaved:
    return PersistenceSaved(
        status="already_saved" if saved.already_saved else "saved",
        conversation_id=saved.conversation_id,
        user_message_id=saved.user_message_id,
        assistant_message_id=saved.assistant_message_id,
    )


def _history_error(error: Exception) -> HTTPException:
    if isinstance(error, ResourceNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到这段探索记录。",
        )
    if isinstance(error, PersistenceConflict):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="这次重试与已经保存的记录不一致。",
        )
    if isinstance(error, PersistenceUnauthorized):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已经失效，请重新登录。",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="PAS 暂时无法读取探索记录，请稍后重试。",
    )


@lru_cache
def get_orchestrator() -> MultiAgentOrchestrator | None:
    settings = get_settings()
    provider = settings.llm_provider

    if provider == "auto":
        if settings.deepseek_api_key:
            provider = "deepseek"
        elif settings.openai_api_key:
            provider = "openai"
        else:
            return None

    if provider == "deepseek":
        if not settings.deepseek_api_key:
            return None
        gateway = DeepSeekChatGateway(
            settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        reflection_model = settings.deepseek_reflection_model
        review_model = settings.deepseek_review_model
        reflection_effort = settings.deepseek_reflection_reasoning_effort
        review_effort = settings.deepseek_review_reasoning_effort
    else:
        if not settings.openai_api_key:
            return None
        gateway = OpenAIResponsesGateway(settings.openai_api_key)
        reflection_model = settings.openai_reflection_model
        review_model = settings.openai_review_model
        reflection_effort = settings.openai_reflection_reasoning_effort
        review_effort = settings.openai_review_reasoning_effort

    memory_agent = None
    if settings.memory_agent_enabled:
        memory_agent = MemoryAgent(
            gateway=gateway,
            model=review_model,
            instructions=memory_instructions(),
            reasoning_effort=review_effort,
        )

    return MultiAgentOrchestrator(
        reflection_agent=ReflectionAgent(
            gateway=gateway,
            model=reflection_model,
            instructions=reflection_instructions(),
            reasoning_effort=reflection_effort,
        ),
        review_agent=ReviewAgent(
            gateway=gateway,
            model=review_model,
            instructions=review_instructions(),
            reasoning_effort=review_effort,
        ),
        memory_agent=memory_agent,
    )


@router.post("", response_model=ChatResponse, response_model_exclude_none=True)
async def chat(
    request: ChatRequest,
    credentials: ChatCredentials,
    settings: ChatSettings,
    orchestrator: MultiAgentOrchestrator | None = Depends(get_orchestrator),
    persistence: OptionalPersistence = None,
) -> ChatResponse:
    safety_result = preflight_safety_result(request.message)
    if safety_result is not None:
        return ChatResponse(
            response=safety_result.response,
            mode=safety_result.mode,
            support_mode=safety_result.support_mode,
            response_source=safety_result.response_source,
            persistence=(
                PersistenceNotSaved(
                    status="not_saved_support",
                )
                if credentials is not None
                else PersistenceNotRequested()
            ),
        )

    user = await optional_authenticated_user(credentials, settings)

    if request.conversation_id is not None and user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录后再继续这段探索。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    conversation_history: tuple[ConversationContextMessage, ...] = ()
    if user is not None and request.client_turn_id is not None:
        if persistence is None:
            if request.conversation_id is not None:
                raise _history_error(PersistenceUnavailable("Not configured."))
        else:
            try:
                existing = await persistence.get_saved_turn(
                    user,
                    client_turn_id=request.client_turn_id,
                    user_content=request.message,
                    conversation_id=request.conversation_id,
                )
                if existing is not None:
                    return ChatResponse(
                        response=existing.response,
                        mode="dual-agent",
                        support_mode="reflection",
                        response_source="review",
                        persistence=_saved_persistence(existing),
                    )
                if request.conversation_id is not None:
                    context_messages = await persistence.list_context_messages(
                        user,
                        request.conversation_id,
                    )
                    conversation_history = tuple(
                        ConversationContextMessage(
                            role=message.role,
                            content=message.content,
                        )
                        for message in context_messages
                        if message.role in {"user", "assistant"}
                    )
            except (
                PersistenceConflict,
                PersistenceUnauthorized,
                PersistenceUnavailable,
                ResourceNotFound,
            ) as error:
                raise _history_error(error) from error

    if orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAS 的 AI 与安全审核尚未配置，当前无法开始探索。",
        )

    try:
        response_kwargs: dict[str, object] = {}
        if conversation_history:
            response_kwargs["conversation_history"] = conversation_history
        if request.response_preference is not None:
            response_kwargs["response_preference"] = request.response_preference
        response_call = orchestrator.respond(
            request.message,
            **response_kwargs,
        )
        result = await asyncio.wait_for(
            response_call,
            timeout=CHAT_TIMEOUT_SECONDS,
        )
    except (AgentPipelineError, TimeoutError):
        result = safe_fallback_result(request.message)

    if user is None or request.client_turn_id is None:
        return ChatResponse(
            response=result.response,
            mode=result.mode,
            support_mode=result.support_mode,
            response_source=result.response_source,
            persistence=PersistenceNotRequested(),
            memory_candidate=result.memory_candidate,
        )

    if result.response_source in {"safety_guard", "review_safety_envelope"}:
        return ChatResponse(
            response=result.response,
            mode=result.mode,
            support_mode=result.support_mode,
            response_source=result.response_source,
            persistence=PersistenceNotSaved(
                status="not_saved_support",
                conversation_id=request.conversation_id,
            ),
        )

    if result.response_source == "safe_fallback":
        return ChatResponse(
            response=result.response,
            mode=result.mode,
            support_mode=result.support_mode,
            response_source=result.response_source,
            persistence=PersistenceNotSaved(
                status="not_saved_fallback",
                conversation_id=request.conversation_id,
            ),
        )

    if persistence is None:
        return ChatResponse(
            response=result.response,
            mode=result.mode,
            support_mode=result.support_mode,
            response_source=result.response_source,
            persistence=PersistenceFailed(
                conversation_id=request.conversation_id,
            ),
        )

    try:
        saved = await persistence.save_reviewed_turn(
            user,
            client_turn_id=request.client_turn_id,
            user_message=request.message,
            final_response=result.response,
            response_source=result.response_source,
            support_mode=result.support_mode,
            risk_level=result.risk_level,
            conversation_id=request.conversation_id,
            conversation_title=_conversation_title(request.message),
        )
    except PersistenceConflict as error:
        raise _history_error(error) from error
    except (
        PersistenceNotAllowed,
        PersistenceUnauthorized,
        PersistenceUnavailable,
        ResourceNotFound,
    ):
        return ChatResponse(
            response=result.response,
            mode=result.mode,
            support_mode=result.support_mode,
            response_source=result.response_source,
            persistence=PersistenceFailed(
                conversation_id=request.conversation_id,
            ),
        )

    return ChatResponse(
        response=saved.response,
        mode=result.mode,
        support_mode=result.support_mode,
        response_source=result.response_source,
        persistence=_saved_persistence(saved),
        memory_candidate=(
            None if saved.already_saved else result.memory_candidate
        ),
    )
