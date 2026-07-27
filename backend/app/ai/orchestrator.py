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
    ) -> None:
        self._reflection_agent = reflection_agent
        self._review_agent = review_agent

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

        return AgentResult(response=final_response)
