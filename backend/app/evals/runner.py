import asyncio
from collections.abc import Sequence
from time import perf_counter

from app.ai.gateway import (
    GatewayDiagnostic,
    PipelineStage,
    gateway_error_retryable,
)
from app.ai.context import ConversationContextMessage
from app.ai.models import ReviewFinalFinding, VerifierRejectionFinding
from app.ai.orchestrator import (
    AgentPipelineError,
    MultiAgentOrchestrator,
    PipelineContractFailureCode,
    PipelineRunState,
)
from app.evals.assertions import evaluate_failure, evaluate_success
from app.evals.models import (
    EVAL_CASE_TIMEOUT_SECONDS,
    MAX_EVAL_CONCURRENCY,
    EvalCaseReport,
    EvalCaseSpec,
    EvalErrorCode,
    EvalFinalVerificationReport,
    EvalFinalResponseChecksReport,
    EvalPipelineFailureReason,
    EvalPipelineFailureReport,
    EvalReviewReport,
    EvalRunReport,
    EvalRunScope,
    SuiteName,
    contains_obvious_secret,
)


def _redact_possible_secret(value: str) -> str:
    if contains_obvious_secret(value):
        return "[redacted: possible credential]"
    return value


def _redact_optional(value: str | None) -> str | None:
    return _redact_possible_secret(value) if value is not None else None


def _case_timeout_diagnostic(
    run_state: PipelineRunState,
) -> GatewayDiagnostic | None:
    """Describe an outer case deadline without exposing exception text."""

    if run_state.current_stage is None:
        return None

    elapsed_ms = None
    if run_state.stage_started_at is not None:
        elapsed_ms = min(
            max(round((perf_counter() - run_state.stage_started_at) * 1000), 0),
            3_600_000,
        )
    stage_timeout_ms = None
    if run_state.stage_timeout_seconds is not None:
        stage_timeout_ms = min(
            max(round(run_state.stage_timeout_seconds * 1000), 1),
            3_600_000,
        )
    return GatewayDiagnostic(
        code="provider_timeout",
        timeout_origin="case_deadline",
        stage_elapsed_ms=elapsed_ms,
        stage_timeout_ms=stage_timeout_ms,
    )


class EvalRunner:
    def __init__(
        self,
        orchestrator: MultiAgentOrchestrator,
        *,
        max_concurrency: int = MAX_EVAL_CONCURRENCY,
        case_timeout_seconds: float = EVAL_CASE_TIMEOUT_SECONDS,
    ) -> None:
        if not 1 <= max_concurrency <= MAX_EVAL_CONCURRENCY:
            raise ValueError("Evaluation concurrency is outside the safe limit.")
        if not 0 < case_timeout_seconds <= EVAL_CASE_TIMEOUT_SECONDS:
            raise ValueError("Evaluation timeout is outside the safe limit.")
        self._orchestrator = orchestrator
        self._max_concurrency = max_concurrency
        self._case_timeout_seconds = case_timeout_seconds

    async def run(
        self,
        cases: Sequence[EvalCaseSpec],
        *,
        suite: SuiteName | None,
        run_scope: EvalRunScope | None = None,
        total_suite_case_count: int | None = None,
    ) -> EvalRunReport:
        if run_scope is None:
            run_scope = "full_suite" if suite is not None else "explicit_cases"
        if run_scope == "explicit_cases":
            total_suite_case_count = None
        elif total_suite_case_count is None:
            total_suite_case_count = len(cases)

        started = perf_counter()
        semaphore = asyncio.Semaphore(self._max_concurrency)
        reports = await asyncio.gather(
            *(self._run_case(case, semaphore) for case in cases)
        )
        pass_count = sum(report.passed for report in reports)
        return EvalRunReport(
            suite=suite,
            run_scope=run_scope,
            total_suite_case_count=total_suite_case_count,
            case_count=len(reports),
            passed=pass_count == len(reports),
            pass_count=pass_count,
            fail_count=len(reports) - pass_count,
            duration_ms=round((perf_counter() - started) * 1000),
            cases=reports,
        )

    async def _run_case(
        self,
        case: EvalCaseSpec,
        semaphore: asyncio.Semaphore,
    ) -> EvalCaseReport:
        started = perf_counter()
        run_state = PipelineRunState()
        conversation_history = tuple(
            ConversationContextMessage(role=item.role, content=item.content)
            for item in case.conversation_history
        )
        try:
            async with semaphore:
                result = await asyncio.wait_for(
                    self._orchestrator.respond(
                        case.input,
                        conversation_history=conversation_history,
                        run_state=run_state,
                    ),
                    timeout=self._case_timeout_seconds,
                )
        except TimeoutError:
            timeout_diagnostic = _case_timeout_diagnostic(run_state)
            return self._failure_report(
                case,
                started,
                "timeout",
                pipeline_stage=run_state.current_stage,
                pipeline_diagnostic=timeout_diagnostic,
            )
        except AgentPipelineError as pipeline_error:
            return self._failure_report(
                case,
                started,
                "pipeline_failed_closed",
                pipeline_stage=pipeline_error.stage,
                pipeline_diagnostic=pipeline_error.diagnostic,
                pipeline_reason=pipeline_error.reason,
                contract_failure_code=pipeline_error.contract_failure_code,
                review_final_finding=pipeline_error.review_final_finding,
                verifier_finding=pipeline_error.verifier_finding,
            )
        except Exception:
            return self._failure_report(case, started, "internal_error")

        assertions = evaluate_success(case, result)
        final_response = _redact_possible_secret(result.response)
        final_response_redacted = final_response != result.response
        review_report = None
        if result.review is not None:
            review_report = EvalReviewReport(
                contract_version=result.review.contract_version,
                draft_disposition=result.review.draft_disposition,
                draft_findings=result.review.draft_findings,
                final_checks=EvalFinalResponseChecksReport(
                    **result.review.final_checks.model_dump(),
                    release_ready=result.review.final_checks.release_ready,
                ),
                risk_level=result.review.risk_level,
                rationale=_redact_possible_secret(result.review.rationale),
            )
        verification_report = None
        if result.verification is not None and not final_response_redacted:
            verification_report = EvalFinalVerificationReport(
                contract_version=result.verification.contract_version,
                target_digest=result.verification.target_digest,
                gate_action=result.verification.gate_action,
                primary_finding=result.verification.primary_finding,
                named_guess_count=result.verification.named_guess_count,
            )
        review_completed = result.review is not None and (
            result.response_source != "review" or verification_report is not None
        )
        return EvalCaseReport(
            case_id=case.case_id,
            category=case.category,
            input=case.input,
            conversation_history=case.conversation_history,
            reflection_draft=_redact_optional(result.reflection_draft),
            final_response=final_response,
            mode=result.mode,
            support_mode=result.support_mode,
            response_source=result.response_source,
            bounded_response_kind=result.bounded_response_kind,
            risk_level=result.risk_level,
            safety_guard_applied=result.response_source in {
                "safety_guard",
                "review_safety_envelope",
                "safe_fallback",
            },
            memory_candidate_present=result.memory_candidate is not None,
            memory_candidate_confidence=(
                result.memory_candidate.confidence
                if result.memory_candidate is not None
                else None
            ),
            review_completed=review_completed,
            review=review_report,
            review_verification=verification_report,
            hard_assertions=assertions,
            passed=all(
                assertion.passed for assertion in assertions if assertion.applicable
            ),
            latency_ms=round((perf_counter() - started) * 1000),
        )

    @staticmethod
    def _failure_report(
        case: EvalCaseSpec,
        started: float,
        error: EvalErrorCode,
        *,
        pipeline_stage: PipelineStage | None = None,
        pipeline_diagnostic: GatewayDiagnostic | None = None,
        pipeline_reason: EvalPipelineFailureReason = "gateway_error",
        contract_failure_code: PipelineContractFailureCode | None = None,
        review_final_finding: ReviewFinalFinding | None = None,
        verifier_finding: VerifierRejectionFinding | None = None,
    ) -> EvalCaseReport:
        pipeline_failure = None
        if pipeline_stage is not None and pipeline_diagnostic is not None:
            pipeline_failure = EvalPipelineFailureReport(
                stage=pipeline_stage,
                reason=pipeline_reason,
                contract_failure_code=contract_failure_code,
                review_final_finding=review_final_finding,
                verifier_finding=verifier_finding,
                code=pipeline_diagnostic.code,
                retryable=gateway_error_retryable(pipeline_diagnostic.code),
                content_present=pipeline_diagnostic.content_present,
                request_id_present=pipeline_diagnostic.request_id_present,
                http_status=pipeline_diagnostic.http_status,
                finish_reason=pipeline_diagnostic.finish_reason,
                timeout_origin=pipeline_diagnostic.timeout_origin,
                attempt_index=pipeline_diagnostic.attempt_index,
                attempt_limit=pipeline_diagnostic.attempt_limit,
                stage_elapsed_ms=pipeline_diagnostic.stage_elapsed_ms,
                stage_timeout_ms=pipeline_diagnostic.stage_timeout_ms,
            )
        return EvalCaseReport(
            case_id=case.case_id,
            category=case.category,
            input=case.input,
            conversation_history=case.conversation_history,
            review_completed=False,
            hard_assertions=evaluate_failure(error, stage=pipeline_stage),
            passed=False,
            latency_ms=round((perf_counter() - started) * 1000),
            error=error,
            pipeline_failure=pipeline_failure,
        )
