from collections.abc import Sequence

from app.ai.context import ConversationContextMessage, reflection_input
from app.ai.gateway import LanguageModelGateway


class ReflectionAgent:
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

    async def respond(
        self,
        user_message: str,
        *,
        conversation_history: Sequence[ConversationContextMessage] = (),
    ) -> str:
        return await self._gateway.generate_text(
            model=self._model,
            instructions=self._instructions,
            user_input=reflection_input(user_message, conversation_history),
            reasoning_effort=self._reasoning_effort,
        )
