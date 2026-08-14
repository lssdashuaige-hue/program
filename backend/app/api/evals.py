import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.orchestrator import MultiAgentOrchestrator
from app.api.chat import get_orchestrator
from app.evals.models import (
    EVAL_RUN_TIMEOUT_SECONDS,
    EvalHealthReport,
    EvalRunReport,
    EvalRunRequest,
    EvalSuiteMetadata,
)
from app.evals.runner import EvalRunner
from app.evals.security import require_evals_admin
from app.evals.suites import get_suite, get_suite_metadata


router = APIRouter(
    prefix="/internal/evals",
    tags=["internal-evals"],
    include_in_schema=False,
)


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
) -> EvalRunReport:
    if orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The reviewed PAS pipeline is not configured.",
        )

    cases = list(get_suite(request.suite)) if request.suite else request.cases
    if cases is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No synthetic evaluation cases were selected.",
        )

    try:
        return await asyncio.wait_for(
            EvalRunner(orchestrator).run(cases, suite=request.suite),
            timeout=EVAL_RUN_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The evaluation run exceeded its safe time limit.",
        ) from exc
