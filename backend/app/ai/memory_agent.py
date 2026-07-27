import json

from app.ai.gateway import LanguageModelGateway
from app.ai.models import MemoryDecision, RiskLevel


class MemoryAgent:
    def __init__(
        self,
        *,
        gateway: LanguageModelGateway,
        model: str,
        instructions: str,
        reasoning_effort: str,
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._instructions = instructions
        self._reasoning_effort = reasoning_effort

    async def evaluate(
        self,
        *,
        user_message: str,
        risk_level: RiskLevel,
    ) -> MemoryDecision:
        memory_input = json.dumps(
            {
                "user_message": user_message,
                "review_risk_level": risk_level,
            },
            ensure_ascii=False,
        )
        return await self._gateway.generate_structured(
            model=self._model,
            instructions=self._instructions,
            user_input=memory_input,
            reasoning_effort=self._reasoning_effort,
            output_type=MemoryDecision,
        )
