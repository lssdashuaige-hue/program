from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.gateway import DeepSeekChatGateway, OpenAIResponsesGateway
from app.ai.orchestrator import AgentPipelineError, MultiAgentOrchestrator
from app.ai.prompts import reflection_instructions, review_instructions
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.config import get_settings

router = APIRouter(prefix="/chat", tags=["reflection"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    response: str
    mode: str = "scaffold"


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
    )


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    orchestrator: MultiAgentOrchestrator | None = Depends(get_orchestrator),
) -> ChatResponse:
    if orchestrator is None:
        return ChatResponse(
            response=(
                "我听见你正在尝试描述一段对你重要的体验。"
                "在继续寻找原因之前，你愿意先说说："
                "这件事发生时最明显的感受是什么吗？"
            )
        )

    try:
        result = await orchestrator.respond(request.message)
    except AgentPipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PAS 暂时无法完成安全审核，请稍后再试。",
        ) from exc

    return ChatResponse(response=result.response, mode=result.mode)
