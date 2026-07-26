from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/chat", tags=["reflection"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    response: str
    mode: str = "scaffold"


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Return a safe placeholder while the LLM adapter is not configured."""
    return ChatResponse(
        response=(
            "我听见你正在尝试描述一段对你重要的体验。"
            "在继续寻找原因之前，你愿意先说说，"
            "这件事发生时最明显的感受是什么吗？"
        )
    )
