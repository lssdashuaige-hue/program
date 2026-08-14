import asyncio
from collections.abc import Sequence
from time import perf_counter

from app.ai.orchestrator import AgentPipelineError, MultiAgentOrchestrator
from app.evals.assertions import evaluate_failure, evaluate_success
from app.evals.models import (
    EVAL_CASE_TIMEOUT_SECONDS,
    MAX_EVAL_CONCURRENCY,
    EvalCaseReport,
    EvalCaseSpec,
    EvalErrorCode,
    EvalReviewReport,
    EvalRunReport,
    SuiteName,
    contains_obvious_secret,
)


def _redact_possible_secret(value: str) -> str:
    if contains_obvious_secret(value):
        return "[redacted: possible credential]"
    return value


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
    ) -> EvalRunReport:
        started = perf_counter()
        semaphore = asyncio.Semaphore(self._max_concurrency)
        reports = await asyncio.gather(
            *(self._run_case(case, semaphore) for case in cases)
        )
        pass_count = sum(report.passed for report in reports)
        return EvalRunReport(
            suite=suite,
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
        try:
            async with semaphore:
                result = await asyncio.wait_for(
                    self._orchestrator.respond(case.input),
                    timeout=self._case_timeout_seconds,
                )
        except TimeoutError:
            return self._failure_report(case, started, "timeout")
        except AgentPipelineError:
            return self._failure_report(case, started, "pipeline_failed_closed")
        except Exception:
            return self._failure_report(case, started, "internal_error")

        assertions = evaluate_success(case, result)
        return EvalCaseReport(
            case_id=case.case_id,
            category=case.category,
            input=case.input,
            reflection_draft=_redact_possible_secret(result.reflection_draft),
            final_response=_redact_possible_secret(result.response),
            mode=result.mode,
            support_mode=result.support_mode,
            memory_candidate_present=result.memory_candidate is not None,
            memory_candidate_confidence=(
                result.memory_candidate.confidence
                if result.memory_candidate is not None
                else None
            ),
            review_completed=True,
            review=EvalReviewReport(
                approved=result.review.approved,
                issues=result.review.issues,
                risk_level=result.review.risk_level,
                rationale=_redact_possible_secret(result.review.rationale),
            ),
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
    ) -> EvalCaseReport:
        return EvalCaseReport(
            case_id=case.case_id,
            category=case.category,
            input=case.input,
            review_completed=False,
            hard_assertions=evaluate_failure(error),
            passed=False,
            latency_ms=round((perf_counter() - started) * 1000),
            error=error,
        )
