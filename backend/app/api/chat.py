from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.gateway import DeepSeekChatGateway, OpenAIResponsesGateway
from app.ai.memory_agent import MemoryAgent
from app.ai.models import AgentMode, MemoryCandidate, SupportMode
from app.ai.orchestrator import AgentPipelineError, MultiAgentOrchestrator
from app.ai.prompts import (
    memory_instructions,
    reflection_instructions,
    review_instructions,
)
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.config import get_settings

router = APIRouter(prefix="/chat", tags=["reflection"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    response: str
    mode: AgentMode
    support_mode: SupportMode
    memory_candidate: MemoryCandidate | None = None


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
    orchestrator: MultiAgentOrchestrator | None = Depends(get_orchestrator),
) -> ChatResponse:
    if orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAS 的 AI 与安全审核尚未配置，当前无法开始探索。",
        )

    try:
        result = await orchestrator.respond(request.message)
    except AgentPipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAS 暂时无法完成安全审核，请稍后再试。",
        ) from exc

    return ChatResponse(
        response=result.response,
        mode=result.mode,
        support_mode=result.support_mode,
        memory_candidate=result.memory_candidate,
    )
