import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.context import ConversationContextMessage
from app.ai.gateway import (
    GatewayDiagnostic,
    PipelineStage,
    diagnostic_from_exception,
)
from app.ai.limits import (
    REFLECTION_STAGE_TIMEOUT_SECONDS,
    REVIEW_STAGE_TIMEOUT_SECONDS,
)
from app.ai.memory_agent import MemoryAgent
from app.ai.models import AgentResult
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.ai.safety import preflight_safety_result, review_safety_envelope_result


class AgentPipelineError(RuntimeError):
    """Raised when PAS cannot safely complete the reviewed response pipeline."""

    def __init__(
        self,
        *,
        stage: PipelineStage,
        diagnostic: GatewayDiagnostic,
    ) -> None:
        super().__init__("PAS reviewed pipeline failed.")
        self.stage = stage
        self.diagnostic = diagnostic


@dataclass
class PipelineRunState:
    current_stage: PipelineStage | None = None


_MEMORY_OPT_OUT_MARKERS = (
    "不要记住",
    "别记住",
    "不要保存",
    "别保存",
    "不要写入记忆",
    "不允许保存",
    "do not remember",
    "don't remember",
    "do not save",
    "don't save",
)


def memory_opt_out_requested(user_message: str) -> bool:
    normalized = user_message.casefold()
    return any(marker in normalized for marker in _MEMORY_OPT_OUT_MARKERS)


class MultiAgentOrchestrator:
    def __init__(
        self,
        *,
        reflection_agent: ReflectionAgent,
        review_agent: ReviewAgent,
        memory_agent: MemoryAgent | None = None,
        reflection_timeout_seconds: float = REFLECTION_STAGE_TIMEOUT_SECONDS,
        review_timeout_seconds: float = REVIEW_STAGE_TIMEOUT_SECONDS,
    ) -> None:
        if reflection_timeout_seconds <= 0 or review_timeout_seconds <= 0:
            raise ValueError("Pipeline stage timeouts must be positive.")
        self._reflection_agent = reflection_agent
        self._review_agent = review_agent
        self._memory_agent = memory_agent
        self._reflection_timeout_seconds = reflection_timeout_seconds
        self._review_timeout_seconds = review_timeout_seconds

    async def respond(
        self,
        user_message: str,
        *,
        run_state: PipelineRunState | None = None,
        conversation_history: Sequence[ConversationContextMessage] = (),
    ) -> AgentResult:
        preflight_result = preflight_safety_result(user_message)
        if preflight_result is not None:
            return preflight_result

        if run_state is not None:
            run_state.current_stage = "reflection"
        try:
            reflection_call = (
                self._reflection_agent.respond(
                    user_message,
                    conversation_history=conversation_history,
                )
                if conversation_history
                else self._reflection_agent.respond(user_message)
            )
            draft = await asyncio.wait_for(
                reflection_call,
                timeout=self._reflection_timeout_seconds,
            )
        except Exception as error:
            raise AgentPipelineError(
                stage="reflection",
                diagnostic=diagnostic_from_exception(error),
            ) from None

        if run_state is not None:
            run_state.current_stage = "review"
        try:
            review_call = (
                self._review_agent.review(
                    user_message,
                    draft,
                    conversation_history=conversation_history,
                )
                if conversation_history
                else self._review_agent.review(user_message, draft)
            )
            decision = await asyncio.wait_for(
                review_call,
                timeout=self._review_timeout_seconds,
            )
        except Exception as error:
            raise AgentPipelineError(
                stage="review",
                diagnostic=diagnostic_from_exception(error),
            ) from None
        if run_state is not None:
            run_state.current_stage = None

        if decision.risk_level in {"concerning", "urgent"}:
            return review_safety_envelope_result(
                user_message=user_message,
                reflection_draft=draft,
                review=decision,
            )

        final_response = decision.final_response.strip()
        if not final_response:
            raise AgentPipelineError(
                stage="review",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
            ) from None

        memory_candidate = None
        if (
            self._memory_agent is not None
            and decision.risk_level == "none"
            and not memory_opt_out_requested(user_message)
        ):
            try:
                memory_decision = await self._memory_agent.evaluate(
                    user_message=user_message,
                    risk_level=decision.risk_level,
                )
                memory_candidate = memory_decision.public_candidate()
            except Exception:
                # Memory is optional. A failure must never leak an unreviewed
                # response or block the user's reviewed conversation.
                memory_candidate = None

        return AgentResult(
            response=final_response,
            mode="multi-agent" if self._memory_agent is not None else "dual-agent",
            support_mode="reflection",
            memory_candidate=memory_candidate,
            response_source="review",
            risk_level=decision.risk_level,
            reflection_draft=draft,
            review=decision,
        )
