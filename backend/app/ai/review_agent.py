from collections.abc import Sequence

from app.ai.context import (
    ConversationContextMessage,
    ResponsePreference,
    review_input,
)
from app.ai.gateway import LanguageModelGateway
from app.ai.final_verifier_agent import (
    FinalVerifierAgent,
    default_final_verifier_model,
)
from app.ai.models import BoundedResponseKind, ReviewDecision
from app.ai.prompts import final_verifier_instructions


class ReviewAgent:
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

    def build_final_verifier(self) -> FinalVerifierAgent:
        """Build the bounded second gate from the primary Review transport."""

        return FinalVerifierAgent(
            gateway=self._gateway,
            model=default_final_verifier_model(self._model),
            instructions=final_verifier_instructions(),
            reasoning_effort=self._reasoning_effort,
            thinking_enabled=False,
        )

    async def review(
        self,
        user_message: str,
        reflection_draft: str,
        *,
        conversation_history: Sequence[ConversationContextMessage] = (),
        response_preference: ResponsePreference | None = None,
        bounded_response_kind: BoundedResponseKind | None = None,
    ) -> ReviewDecision:
        decision = await self._gateway.generate_structured(
            model=self._model,
            instructions=self._instructions,
            user_input=review_input(
                user_message,
                reflection_draft,
                conversation_history,
                response_preference,
                bounded_response_kind,
            ),
            reasoning_effort=self._reasoning_effort,
            output_type=ReviewDecision,
            thinking_enabled=self._thinking_enabled,
        )
        if not isinstance(decision, ReviewDecision):
            raise TypeError("Review gateway returned an unexpected output type.")
        return decision
