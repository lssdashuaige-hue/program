from collections.abc import Sequence

from app.ai.context import ConversationContextMessage, review_input
from app.ai.gateway import LanguageModelGateway
from app.ai.models import ReviewDecision


class ReviewAgent:
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

    async def review(
        self,
        user_message: str,
        reflection_draft: str,
        *,
        conversation_history: Sequence[ConversationContextMessage] = (),
    ) -> ReviewDecision:
        return await self._gateway.generate_structured(
            model=self._model,
            instructions=self._instructions,
            user_input=review_input(
                user_message,
                reflection_draft,
                conversation_history,
            ),
            reasoning_effort=self._reasoning_effort,
            output_type=ReviewDecision,
        )
