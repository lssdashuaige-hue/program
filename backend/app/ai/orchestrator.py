import asyncio
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Literal, TypeVar

from app.ai.bounded_responses import bounded_response_candidate
from app.ai.context import (
    ConversationContextMessage,
    ResponsePreference,
    permitted_review_source_bases,
)
from app.ai.final_verifier_agent import FinalVerifierAgent
from app.ai.gateway import (
    GatewayDiagnostic,
    PipelineStage,
    diagnostic_from_exception,
)
from app.ai.limits import (
    MEMORY_STAGE_TIMEOUT_SECONDS,
    REFLECTION_STAGE_TIMEOUT_SECONDS,
    REVIEW_STAGE_TIMEOUT_SECONDS,
    VERIFIER_STAGE_TIMEOUT_SECONDS,
)
from app.ai.memory_agent import MemoryAgent
from app.ai.models import (
    AgentResult,
    REVIEW_FINAL_FINDINGS,
    VERIFIER_REJECTION_FINDINGS,
    ReviewFinalFinding,
    VerifierRejectionFinding,
    bounded_response_health_boundary_is_satisfied,
    conservative_named_guess_count,
    final_response_digest,
    personal_lifespan_review_finding,
    primary_review_final_finding,
    response_has_at_most_one_question,
    review_disposition_matches_draft,
    unavailable_cross_chat_checks_are_exact,
)
from app.ai.reflection_agent import ReflectionAgent
from app.ai.review_agent import ReviewAgent
from app.ai.safety import preflight_safety_result, review_safety_envelope_result


PipelineContractFailureCode = Literal[
    "draft_disposition_mismatch",
    "source_basis_unavailable",
    "final_checks_not_release_ready",
    "question_limit_exceeded",
    "bounded_candidate_not_accepted",
    "verifier_unavailable",
    "verifier_rejected",
    "verifier_digest_mismatch",
]

_REVIEW_CONTRACT_FAILURE_CODES = frozenset(
    {
        "draft_disposition_mismatch",
        "source_basis_unavailable",
        "final_checks_not_release_ready",
        "question_limit_exceeded",
        "bounded_candidate_not_accepted",
    }
)
_VERIFIER_CONTRACT_FAILURE_CODES = frozenset(
    {
        "verifier_unavailable",
        "verifier_rejected",
        "verifier_digest_mismatch",
    }
)
_PIPELINE_CONTRACT_FAILURE_CODES = (
    _REVIEW_CONTRACT_FAILURE_CODES | _VERIFIER_CONTRACT_FAILURE_CODES
)


class AgentPipelineError(RuntimeError):
    """Raised when PAS cannot safely complete the reviewed response pipeline."""

    def __init__(
        self,
        *,
        stage: PipelineStage,
        diagnostic: GatewayDiagnostic,
        reason: Literal["gateway_error", "review_contract_violation"] = "gateway_error",
        contract_failure_code: PipelineContractFailureCode | None = None,
        review_final_finding: ReviewFinalFinding | None = None,
        verifier_finding: VerifierRejectionFinding | None = None,
    ) -> None:
        review_final_rejection = (
            stage == "review"
            and reason == "review_contract_violation"
            and contract_failure_code == "final_checks_not_release_ready"
            and diagnostic.code == "invalid_schema"
        )
        if review_final_rejection != (review_final_finding is not None):
            raise ValueError(
                "Live Review final-check failures require exactly one fixed finding."
            )
        if (
            review_final_finding is not None
            and review_final_finding not in REVIEW_FINAL_FINDINGS
        ):
            raise ValueError("Review final finding is not allowlisted.")
        verifier_rejection = (
            stage == "review_verifier"
            and reason == "review_contract_violation"
            and contract_failure_code == "verifier_rejected"
            and diagnostic.code == "invalid_schema"
        )
        if verifier_rejection != (verifier_finding is not None):
            raise ValueError(
                "Live verifier rejections require exactly one fixed finding."
            )
        if (
            verifier_finding is not None
            and verifier_finding not in VERIFIER_REJECTION_FINDINGS
        ):
            raise ValueError("Verifier finding is not allowlisted.")
        if reason == "gateway_error":
            if contract_failure_code is not None:
                raise ValueError(
                    "Gateway failures cannot contain a contract failure code."
                )
        else:
            if contract_failure_code is None:
                raise ValueError(
                    "Review contract failures require a fixed failure code."
                )
            if contract_failure_code not in _PIPELINE_CONTRACT_FAILURE_CODES:
                raise ValueError("Review contract failure code is not allowlisted.")
            if diagnostic.code != "invalid_schema":
                raise ValueError(
                    "Review contract failures require an invalid-schema diagnostic."
                )
            if (
                contract_failure_code in _REVIEW_CONTRACT_FAILURE_CODES
                and stage != "review"
            ):
                raise ValueError(
                    "Primary Review contract failures require the Review stage."
                )
            if (
                contract_failure_code in _VERIFIER_CONTRACT_FAILURE_CODES
                and stage != "review_verifier"
            ):
                raise ValueError(
                    "Verifier contract failures require the Final Verifier stage."
                )
        super().__init__("PAS reviewed pipeline failed.")
        self.stage = stage
        self.diagnostic = diagnostic
        self.reason = reason
        self.contract_failure_code = contract_failure_code
        self.review_final_finding = review_final_finding
        self.verifier_finding = verifier_finding


@dataclass
class PipelineRunState:
    current_stage: PipelineStage | None = None
    stage_started_at: float | None = None
    stage_timeout_seconds: float | None = None

    def enter(self, stage: PipelineStage, timeout_seconds: float) -> None:
        self.current_stage = stage
        self.stage_started_at = perf_counter()
        self.stage_timeout_seconds = timeout_seconds

    def clear(self) -> None:
        self.current_stage = None
        self.stage_started_at = None
        self.stage_timeout_seconds = None


StageResult = TypeVar("StageResult")


class StageDeadlineError(TimeoutError):
    """Raised only when PAS's own per-stage deadline expires."""


async def _await_stage(
    awaitable: Awaitable[StageResult],
    *,
    timeout_seconds: float,
) -> StageResult:
    """Keep a provider-raised TimeoutError distinct from the PAS deadline."""

    task = asyncio.ensure_future(awaitable)
    try:
        done, _pending = await asyncio.wait({task}, timeout=timeout_seconds)
        if task in done:
            return task.result()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise StageDeadlineError("PAS stage deadline expired.")
    except BaseException:
        if not task.done():
            task.cancel()
        raise


def _stage_failure_diagnostic(
    error: Exception,
    *,
    started_at: float,
    timeout_seconds: float,
) -> GatewayDiagnostic:
    """Attach bounded stage timing without exposing provider error details."""

    elapsed_seconds = max(0.0, perf_counter() - started_at)
    diagnostic = diagnostic_from_exception(error)
    if isinstance(error, StageDeadlineError):
        elapsed_seconds = max(elapsed_seconds, timeout_seconds)
        diagnostic = replace(diagnostic, timeout_origin="stage_deadline")
    return replace(
        diagnostic,
        stage_elapsed_ms=min(round(elapsed_seconds * 1000), 3_600_000),
        stage_timeout_ms=min(max(round(timeout_seconds * 1000), 1), 3_600_000),
    )


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
        final_verifier_agent: FinalVerifierAgent | None = None,
        memory_agent: MemoryAgent | None = None,
        reflection_timeout_seconds: float = REFLECTION_STAGE_TIMEOUT_SECONDS,
        review_timeout_seconds: float = REVIEW_STAGE_TIMEOUT_SECONDS,
        verifier_timeout_seconds: float = VERIFIER_STAGE_TIMEOUT_SECONDS,
        memory_timeout_seconds: float = MEMORY_STAGE_TIMEOUT_SECONDS,
    ) -> None:
        if not 0 < reflection_timeout_seconds <= 3_600:
            raise ValueError("Reflection timeout is outside the safe range.")
        if not 0 < review_timeout_seconds <= 3_600:
            raise ValueError("Review timeout is outside the safe range.")
        if not 0 < verifier_timeout_seconds <= 3_600:
            raise ValueError("Final Verifier timeout is outside the safe range.")
        if not 0 < memory_timeout_seconds <= 3_600:
            raise ValueError("Memory timeout is outside the safe range.")
        self._reflection_agent = reflection_agent
        self._review_agent = review_agent
        self._final_verifier_agent = final_verifier_agent
        if self._final_verifier_agent is None and isinstance(review_agent, ReviewAgent):
            self._final_verifier_agent = review_agent.build_final_verifier()
        self._memory_agent = memory_agent
        self._reflection_timeout_seconds = reflection_timeout_seconds
        self._review_timeout_seconds = review_timeout_seconds
        self._verifier_timeout_seconds = verifier_timeout_seconds
        self._memory_timeout_seconds = memory_timeout_seconds

    async def respond(
        self,
        user_message: str,
        *,
        run_state: PipelineRunState | None = None,
        conversation_history: Sequence[ConversationContextMessage] = (),
        response_preference: ResponsePreference | None = None,
        allow_memory: bool = True,
    ) -> AgentResult:
        preflight_result = preflight_safety_result(user_message)
        if preflight_result is not None:
            return preflight_result

        bounded_candidate = bounded_response_candidate(user_message)
        if bounded_candidate is not None:
            draft = bounded_candidate.response
        else:
            reflection_started_at = perf_counter()
            if run_state is not None:
                run_state.enter("reflection", self._reflection_timeout_seconds)
            try:
                reflection_kwargs: dict[str, object] = {}
                if conversation_history:
                    reflection_kwargs["conversation_history"] = conversation_history
                if response_preference is not None:
                    reflection_kwargs["response_preference"] = response_preference
                reflection_call = self._reflection_agent.respond(
                    user_message,
                    **reflection_kwargs,
                )
                draft = await _await_stage(
                    reflection_call,
                    timeout_seconds=self._reflection_timeout_seconds,
                )
            except Exception as error:
                raise AgentPipelineError(
                    stage="reflection",
                    diagnostic=_stage_failure_diagnostic(
                        error,
                        started_at=reflection_started_at,
                        timeout_seconds=self._reflection_timeout_seconds,
                    ),
                ) from None

        review_started_at = perf_counter()
        if run_state is not None:
            run_state.enter("review", self._review_timeout_seconds)
        try:
            review_kwargs: dict[str, object] = {}
            if conversation_history:
                review_kwargs["conversation_history"] = conversation_history
            if response_preference is not None:
                review_kwargs["response_preference"] = response_preference
            if bounded_candidate is not None:
                review_kwargs["bounded_response_kind"] = bounded_candidate.kind
            review_call = self._review_agent.review(
                user_message,
                draft,
                **review_kwargs,
            )
            decision = await _await_stage(
                review_call,
                timeout_seconds=self._review_timeout_seconds,
            )
        except Exception as error:
            raise AgentPipelineError(
                stage="review",
                diagnostic=_stage_failure_diagnostic(
                    error,
                    started_at=review_started_at,
                    timeout_seconds=self._review_timeout_seconds,
                ),
            ) from None
        if run_state is not None:
            run_state.clear()

        if (
            bounded_candidate is not None
            and decision.risk_level == "none"
            and (
                decision.draft_disposition != "accepted"
                or decision.final_response != bounded_candidate.response
            )
        ):
            raise AgentPipelineError(
                stage="review",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="bounded_candidate_not_accepted",
            )

        # A Review-classified safety risk always moves to the deterministic
        # envelope. Contract inconsistencies in the model-authored draft/final
        # metadata must not block the safer response path.
        if decision.risk_level in {"concerning", "urgent"}:
            return review_safety_envelope_result(
                user_message=user_message,
                reflection_draft=draft,
                review=decision,
            )

        if not review_disposition_matches_draft(decision, draft):
            raise AgentPipelineError(
                stage="review",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="draft_disposition_mismatch",
            )

        permitted_source_bases = set(
            permitted_review_source_bases(conversation_history)
        )
        if not set(decision.final_checks.source_bases).issubset(
            permitted_source_bases
        ):
            raise AgentPipelineError(
                stage="review",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="source_basis_unavailable",
            )

        if (
            bounded_candidate is not None
            and not bounded_response_health_boundary_is_satisfied(
                bounded_candidate.kind,
                decision.final_checks.health_boundary,
            )
        ):
            raise AgentPipelineError(
                stage="review",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="final_checks_not_release_ready",
                review_final_finding="health_boundary",
            )

        if not decision.final_checks.release_ready:
            review_final_finding = primary_review_final_finding(
                decision.final_checks
            )
            if review_final_finding is None:
                raise RuntimeError(
                    "Review release state and fixed failure finding diverged."
                )
            raise AgentPipelineError(
                stage="review",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="final_checks_not_release_ready",
                review_final_finding=review_final_finding,
            )

        if (
            bounded_candidate is not None
            and bounded_candidate.kind == "unavailable_cross_chat_context"
            and not unavailable_cross_chat_checks_are_exact(
                source_bases=list(decision.final_checks.source_bases),
                named_guess_count=decision.final_checks.named_guess_count,
                diagnostic_self_screening_present=(
                    decision.final_checks.diagnostic_self_screening_present
                ),
                health_boundary=decision.final_checks.health_boundary,
                cross_chat_boundary=decision.final_checks.cross_chat_boundary,
            )
        ):
            raise AgentPipelineError(
                stage="review",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="final_checks_not_release_ready",
                review_final_finding="cross_chat_boundary",
            )

        if (
            bounded_candidate is not None
            and bounded_candidate.kind == "personal_lifespan_conversion"
        ):
            lifespan_finding = personal_lifespan_review_finding(
                source_bases=list(decision.final_checks.source_bases),
                named_guess_count=decision.final_checks.named_guess_count,
                diagnostic_self_screening_present=(
                    decision.final_checks.diagnostic_self_screening_present
                ),
                health_boundary=decision.final_checks.health_boundary,
                cross_chat_boundary=decision.final_checks.cross_chat_boundary,
            )
            if lifespan_finding is not None:
                raise AgentPipelineError(
                    stage="review",
                    diagnostic=GatewayDiagnostic(
                        code="invalid_schema",
                        content_present=True,
                    ),
                    reason="review_contract_violation",
                    contract_failure_code="final_checks_not_release_ready",
                    review_final_finding=lifespan_finding,
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

        if not response_has_at_most_one_question(final_response):
            raise AgentPipelineError(
                stage="review",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="question_limit_exceeded",
            )

        if self._final_verifier_agent is None:
            raise AgentPipelineError(
                stage="review_verifier",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=False,
                ),
                reason="review_contract_violation",
                contract_failure_code="verifier_unavailable",
            )

        verifier_started_at = perf_counter()
        if run_state is not None:
            run_state.enter("review_verifier", self._verifier_timeout_seconds)
        try:
            verifier_kwargs: dict[str, object] = {}
            if conversation_history:
                verifier_kwargs["conversation_history"] = conversation_history
            if bounded_candidate is not None:
                verifier_kwargs["bounded_response_kind"] = bounded_candidate.kind
            verification_call = self._final_verifier_agent.verify(
                user_message,
                final_response,
                **verifier_kwargs,
            )
            verification = await _await_stage(
                verification_call,
                timeout_seconds=self._verifier_timeout_seconds,
            )
        except Exception as error:
            raise AgentPipelineError(
                stage="review_verifier",
                diagnostic=_stage_failure_diagnostic(
                    error,
                    started_at=verifier_started_at,
                    timeout_seconds=self._verifier_timeout_seconds,
                ),
            ) from None
        if run_state is not None:
            run_state.clear()

        if verification.target_digest != final_response_digest(final_response):
            raise AgentPipelineError(
                stage="review_verifier",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="verifier_digest_mismatch",
            )

        if (
            verification.gate_action != "release_candidate"
            or verification.primary_finding != "none"
        ):
            raise AgentPipelineError(
                stage="review_verifier",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="verifier_rejected",
                verifier_finding=verification.primary_finding,
            )

        if (
            conservative_named_guess_count(
                decision.final_checks.named_guess_count,
                verification.named_guess_count,
                final_response,
            )
            > 2
        ):
            raise AgentPipelineError(
                stage="review_verifier",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="verifier_rejected",
                verifier_finding="guess_limit",
            )

        if (
            bounded_candidate is not None
            and bounded_candidate.kind == "unavailable_cross_chat_context"
            and verification.named_guess_count != 0
        ):
            raise AgentPipelineError(
                stage="review_verifier",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="verifier_rejected",
                verifier_finding="guess_limit",
            )

        if (
            bounded_candidate is not None
            and bounded_candidate.kind == "personal_lifespan_conversion"
            and verification.named_guess_count != 0
        ):
            raise AgentPipelineError(
                stage="review_verifier",
                diagnostic=GatewayDiagnostic(
                    code="invalid_schema",
                    content_present=True,
                ),
                reason="review_contract_violation",
                contract_failure_code="verifier_rejected",
                verifier_finding="guess_limit",
            )

        memory_candidate = None
        if (
            self._memory_agent is not None
            and allow_memory
            and decision.risk_level == "none"
            and bounded_candidate is None
            and not memory_opt_out_requested(user_message)
        ):
            try:
                memory_decision = await _await_stage(
                    self._memory_agent.evaluate(
                        user_message=user_message,
                        risk_level=decision.risk_level,
                    ),
                    timeout_seconds=self._memory_timeout_seconds,
                )
                memory_candidate = memory_decision.sourced_public_candidate(user_message)
            except Exception:
                # Memory is optional. A failure must never leak an unreviewed
                # response or block the user's reviewed conversation.
                memory_candidate = None

        return AgentResult(
            response=final_response,
            # Every released response has independently passed primary Review
            # and Final Verification; the ordinary path also uses Reflection.
            # `dual-agent` remains only as a legacy serialization value.
            mode="multi-agent",
            support_mode="reflection",
            memory_candidate=memory_candidate,
            response_source="review",
            risk_level=decision.risk_level,
            reflection_draft=draft,
            review=decision,
            verification=verification,
            bounded_response_kind=(
                bounded_candidate.kind if bounded_candidate is not None else None
            ),
        )
