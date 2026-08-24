import asyncio
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.orchestrator import MultiAgentOrchestrator
from app.api.chat import get_orchestrator
from app.config import Settings, get_settings
from app.evals.models import (
    EVAL_RUN_TIMEOUT_SECONDS,
    EvalHealthReport,
    EvalRunReport,
    EvalRunRequest,
    EvalSuiteMetadata,
)
from app.evals.runner import EvalRunner
from app.evals.report_store import (
    EvalReportPersistenceError,
    safe_report_persistence_reason,
    write_full_suite_report,
)
from app.evals.security import require_evals_admin
from app.evals.suites import get_suite, get_suite_metadata


router = APIRouter(
    prefix="/internal/evals",
    tags=["internal-evals"],
    include_in_schema=False,
)

_eval_run_gate = Lock()


@router.get("/health", response_model=EvalHealthReport)
async def eval_health(
    _authorized: Annotated[None, Depends(require_evals_admin)],
    orchestrator: Annotated[
        MultiAgentOrchestrator | None,
        Depends(get_orchestrator),
    ],
) -> EvalHealthReport:
    provider_ready = orchestrator is not None
    return EvalHealthReport(
        status="ready" if provider_ready else "provider_unavailable",
        provider_ready=provider_ready,
    )


@router.get("/suites", response_model=list[EvalSuiteMetadata])
async def eval_suites(
    _authorized: Annotated[None, Depends(require_evals_admin)],
) -> list[EvalSuiteMetadata]:
    return get_suite_metadata()


@router.post("/run", response_model=EvalRunReport, response_model_exclude_none=True)
async def run_evals(
    request: EvalRunRequest,
    _authorized: Annotated[None, Depends(require_evals_admin)],
    orchestrator: Annotated[
        MultiAgentOrchestrator | None,
        Depends(get_orchestrator),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EvalRunReport:
    if orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The reviewed PAS pipeline is not configured.",
        )

    total_suite_case_count = None
    if request.suite is not None:
        suite_cases = get_suite(request.suite)
        total_suite_case_count = len(suite_cases)
        if request.case_ids is None:
            cases = list(suite_cases)
            run_scope = "full_suite"
        else:
            requested_ids = set(request.case_ids)
            known_ids = {case.case_id for case in suite_cases}
            unknown_ids = sorted(requested_ids - known_ids)
            if unknown_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Unknown evaluation case IDs for "
                        f"{request.suite}: {', '.join(unknown_ids)}."
                    ),
                )
            cases = [case for case in suite_cases if case.case_id in requested_ids]
            run_scope = "suite_subset"
    else:
        cases = request.cases
        run_scope = "explicit_cases"

    if cases is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No synthetic evaluation cases were selected.",
        )

    if not _eval_run_gate.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An evaluation run is already in progress.",
        )

    try:
        try:
            raw_report = await asyncio.wait_for(
                EvalRunner(orchestrator).run(
                    cases,
                    suite=request.suite,
                    run_scope=run_scope,
                    total_suite_case_count=total_suite_case_count,
                ),
                timeout=EVAL_RUN_TIMEOUT_SECONDS,
            )
            report = EvalRunReport.model_validate(raw_report)
            if run_scope == "full_suite":
                try:
                    write_full_suite_report(
                        report,
                        settings.pas_evals_report_dir,
                    )
                except EvalReportPersistenceError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=(
                            "The complete evaluation report could not be "
                            "safely archived."
                        ),
                        headers={
                            "X-PAS-Eval-Archive-Reason": (
                                safe_report_persistence_reason(exc.reason_code)
                            )
                        },
                    ) from exc
            return report
        except TimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="The evaluation run exceeded its safe time limit.",
            ) from exc
    finally:
        _eval_run_gate.release()
