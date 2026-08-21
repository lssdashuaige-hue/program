from collections.abc import Sequence

from app.ai.context import ConversationContextMessage, verification_input
from app.ai.gateway import LanguageModelGateway
from app.ai.models import BoundedResponseKind, FinalVerificationDecision


def default_final_verifier_model(review_model: str) -> str:
    """Use bounded DeepSeek Flash; retain the configured Review model otherwise."""

    if review_model.casefold().startswith("deepseek-"):
        return "deepseek-v4-flash"
    return review_model


class FinalVerifierAgent:
    def __init__(
        self,
        *,
        gateway: LanguageModelGateway,
        model: str,
        instructions: str,
        reasoning_effort: str,
        thinking_enabled: bool = False,
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._instructions = instructions
        self._reasoning_effort = reasoning_effort
        self._thinking_enabled = thinking_enabled

    async def verify(
        self,
        user_message: str,
        candidate_response: str,
        *,
        conversation_history: Sequence[ConversationContextMessage] = (),
        bounded_response_kind: BoundedResponseKind | None = None,
    ) -> FinalVerificationDecision:
        decision = await self._gateway.generate_structured(
            model=self._model,
            instructions=self._instructions,
            user_input=verification_input(
                user_message,
                candidate_response,
                conversation_history,
                bounded_response_kind=bounded_response_kind,
            ),
            reasoning_effort=self._reasoning_effort,
            output_type=FinalVerificationDecision,
            thinking_enabled=self._thinking_enabled,
        )
        if not isinstance(decision, FinalVerificationDecision):
            raise TypeError("Final Verifier gateway returned an unexpected output type.")
        return decision
