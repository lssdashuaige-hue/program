from app.ai.memory_agent import MemoryAgent
from app.ai.models import AgentResult
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent


class AgentPipelineError(RuntimeError):
    """Raised when PAS cannot safely complete the reviewed response pipeline."""


class MultiAgentOrchestrator:
    def __init__(
        self,
        *,
        reflection_agent: ReflectionAgent,
        review_agent: ReviewAgent,
        memory_agent: MemoryAgent | None = None,
    ) -> None:
        self._reflection_agent = reflection_agent
        self._review_agent = review_agent
        self._memory_agent = memory_agent

    async def respond(self, user_message: str) -> AgentResult:
        try:
            draft = await self._reflection_agent.respond(user_message)
            decision = await self._review_agent.review(user_message, draft)
        except Exception as exc:
            raise AgentPipelineError(
                "PAS could not complete both required agent stages."
            ) from exc

        final_response = decision.final_response.strip()
        if not final_response:
            raise AgentPipelineError("Review Agent produced an empty final response.")

        memory_candidate = None
        if self._memory_agent is not None and decision.risk_level == "none":
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
            support_mode=(
                "reflection" if decision.risk_level == "none" else "support"
            ),
            memory_candidate=memory_candidate,
        )
