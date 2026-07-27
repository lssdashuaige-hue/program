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

    async def respond(self, user_message: str) -> str:
        return await self._gateway.generate_text(
            model=self._model,
            instructions=self._instructions,
            user_input=user_message,
            reasoning_effort=self._reasoning_effort,
        )
