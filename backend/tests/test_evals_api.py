import asyncio
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ai.bounded_responses import bounded_response_candidate
from app.ai.gateway import GatewayDiagnostic
from app.ai.models import (
    AgentResult,
    FinalVerificationDecision,
    final_response_digest,
)
from app.ai.orchestrator import AgentPipelineError
from app.api.chat import get_orchestrator
from app.api.evals import run_evals
from app.config import Settings, get_settings
from app.evals.assertions import evaluate_success
from app.evals.models import (
    EVAL_CASE_TIMEOUT_SECONDS,
    EVAL_RUN_TIMEOUT_MARGIN_SECONDS,
    MAX_EVAL_CASES,
    MAX_EVAL_CONCURRENCY,
    MAX_EVAL_HISTORY_MESSAGES,
    MAX_EVAL_INPUT_LENGTH,
    EvalCaseSpec,
    EvalRunRequest,
    SuiteName,
)
from app.evals.runner import EvalRunner
from app.evals.suites import get_suite
from app.main import app
from tests.review_fixtures import review_decision, safe_final_checks


ADMIN_TOKEN = "pas-evals-admin-token-32-characters"
OPENAI_SECRET = "provider-openai-secret-value"
DEEPSEEK_SECRET = "provider-deepseek-secret-value"


class StaticOrchestrator:
    async def respond(self, user_message: str, **kwargs: Any) -> AgentResult:
        bounded_candidate = bounded_response_candidate(user_message)
        final = (
            bounded_candidate.response
            if bounded_candidate is not None
            else "我听见你正在整理这段体验。哪部分最需要先看清？"
        )
        review = review_decision(
            final_response=final,
            final_checks=(
                safe_final_checks(
                    source_bases=("current_user_message", "general_knowledge"),
                    cross_chat_boundary="satisfied",
                )
                if bounded_candidate is not None
                and bounded_candidate.kind == "unavailable_cross_chat_context"
                else None
            ),
            rationale="Safe synthetic fixture.",
        )
        return AgentResult(
            response=final,
            mode="dual-agent",
            support_mode="reflection",
            reflection_draft=final,
            review=review,
            verification=FinalVerificationDecision(
                contract_version="2",
                target_digest=final_response_digest(final),
                gate_action="release_candidate",
                primary_finding="none",
                named_guess_count=0,
                rationale="Internal verifier fixture must not enter the report.",
            ),
            bounded_response_kind=(
                bounded_candidate.kind if bounded_candidate is not None else None
            ),
        )


class RecordingOrchestrator(StaticOrchestrator):
    def __init__(self) -> None:
        self.calls = 0

    async def respond(self, user_message: str, **kwargs: Any) -> AgentResult:
        self.calls += 1
        return await super().respond(user_message, **kwargs)


class BlockingOrchestrator(StaticOrchestrator):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def respond(self, user_message: str, **kwargs: Any) -> AgentResult:
        self.started.set()
        await self.release.wait()
        return await super().respond(user_message, **kwargs)


class ContractFailureOrchestrator:
    async def respond(self, user_message: str, **kwargs: Any) -> AgentResult:
        raise AgentPipelineError(
            stage="review_verifier",
            diagnostic=GatewayDiagnostic(
                code="invalid_schema",
                content_present=True,
            ),
            reason="review_contract_violation",
            contract_failure_code="verifier_rejected",
            verifier_finding="health_boundary",
        )


class ReviewContractFailureOrchestrator:
    async def respond(self, user_message: str, **kwargs: Any) -> AgentResult:
        raise AgentPipelineError(
            stage="review",
            diagnostic=GatewayDiagnostic(
                code="invalid_schema",
                content_present=True,
            ),
            reason="review_contract_violation",
            contract_failure_code="final_checks_not_release_ready",
            review_final_finding="diagnostic_self_screening",
        )


def eval_settings(*, enabled: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        pas_evals_enabled=enabled,
        pas_evals_admin_token=ADMIN_TOKEN,
        openai_api_key=OPENAI_SECRET,
        deepseek_api_key=DEEPSEEK_SECRET,
    )


def authorize(settings: Settings, orchestrator: Any = None) -> None:
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator


def auth_headers(token: str = ADMIN_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Any:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_evals_are_disabled_by_default() -> None:
    authorize(eval_settings(enabled=False))

    response = TestClient(app).get(
        "/internal/evals/suites",
        headers=auth_headers(),
    )

    assert response.status_code == 404
    assert "eval" not in response.text.casefold()


def test_missing_and_bad_admin_tokens_are_rejected() -> None:
    authorize(eval_settings())
    client = TestClient(app)

    missing = client.get("/internal/evals/suites")
    invalid = client.get(
        "/internal/evals/suites",
        headers=auth_headers("wrong-token-that-is-long-enough"),
    )

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.status_code == 403
    assert ADMIN_TOKEN not in invalid.text


def test_health_and_suite_metadata_are_protected_and_read_only() -> None:
    authorize(eval_settings(), StaticOrchestrator())
    client = TestClient(app)

    health = client.get("/internal/evals/health", headers=auth_headers())
    suites = client.get("/internal/evals/suites", headers=auth_headers())

    assert health.status_code == 200
    assert health.json()["provider_ready"] is True
    assert health.json()["limits"]["max_cases"] == MAX_EVAL_CASES
    assert health.json()["limits"]["max_concurrency"] == 2
    assert (
        health.json()["limits"]["max_history_messages"]
        == MAX_EVAL_HISTORY_MESSAGES
    )
    required_run_budget = (
        (MAX_EVAL_CASES + MAX_EVAL_CONCURRENCY - 1) // MAX_EVAL_CONCURRENCY
    ) * EVAL_CASE_TIMEOUT_SECONDS + EVAL_RUN_TIMEOUT_MARGIN_SECONDS
    assert health.json()["limits"]["run_timeout_seconds"] >= required_run_budget
    assert suites.status_code == 200
    suite_payload = {item["name"]: item for item in suites.json()}
    assert set(suite_payload) == {"pas-core-v0.1", "pas-dialogue-v0.1"}
    assert suite_payload["pas-core-v0.1"]["case_count"] == MAX_EVAL_CASES
    assert suite_payload["pas-dialogue-v0.1"]["case_count"] == MAX_EVAL_CASES


def test_run_requires_a_configured_reviewed_pipeline() -> None:
    authorize(eval_settings(), None)

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={"suite": "pas-core-v0.1"},
    )

    assert response.status_code == 503


def test_dialogue_suite_dispatches_through_the_internal_api() -> None:
    authorize(eval_settings(), StaticOrchestrator())

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={"suite": "pas-dialogue-v0.1"},
    )

    assert response.status_code == 200
    assert response.json()["suite"] == "pas-dialogue-v0.1"
    assert response.json()["run_scope"] == "full_suite"
    assert response.json()["total_suite_case_count"] == MAX_EVAL_CASES
    assert response.json()["case_count"] == MAX_EVAL_CASES


@pytest.mark.parametrize(
    ("suite", "requested_case_ids"),
    [
        (
            "pas-core-v0.1",
            ["privacy_memory_boundary", "diagnosis_temptation"],
        ),
        (
            "pas-dialogue-v0.1",
            ["observer_keeps_imported_provenance", "short_followup_uses_history"],
        ),
    ],
)
def test_suite_subset_uses_original_specs_and_suite_order(
    suite: SuiteName,
    requested_case_ids: list[str],
) -> None:
    orchestrator = StaticOrchestrator()
    authorize(eval_settings(), orchestrator)
    original_suite = get_suite(suite)
    selected_ids = set(requested_case_ids)
    expected_cases = [case for case in original_suite if case.case_id in selected_ids]

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={"suite": suite, "case_ids": requested_case_ids},
    )
    report = response.json()

    assert response.status_code == 200
    assert report["suite"] == suite
    assert report["run_scope"] == "suite_subset"
    assert report["total_suite_case_count"] == len(original_suite)
    assert report["case_count"] == len(expected_cases)
    assert [case["case_id"] for case in report["cases"]] == [
        case.case_id for case in expected_cases
    ]

    for returned, original in zip(report["cases"], expected_cases, strict=True):
        expected_result = asyncio.run(orchestrator.respond(original.input))
        expected_assertions = [
            assertion.model_dump()
            for assertion in evaluate_success(original, expected_result)
        ]
        assert returned["input"] == original.input
        assert returned["conversation_history"] == [
            message.model_dump() for message in original.conversation_history
        ]
        assert returned["hard_assertions"] == expected_assertions


def test_unknown_suite_subset_case_id_is_rejected_before_provider_use() -> None:
    orchestrator = RecordingOrchestrator()
    authorize(eval_settings(), orchestrator)

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={
            "suite": "pas-core-v0.1",
            "case_ids": ["normal_reflection", "unknown_synthetic_case"],
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Unknown evaluation case IDs for pas-core-v0.1: "
            "unknown_synthetic_case."
        )
    }
    assert orchestrator.calls == 0


@pytest.mark.parametrize(
    "body",
    [
        {"suite": "pas-core-v0.1", "case_ids": []},
        {
            "suite": "pas-core-v0.1",
            "case_ids": ["normal_reflection", "normal_reflection"],
        },
        {
            "suite": "pas-core-v0.1",
            "case_ids": [
                f"synthetic_case_{index}"
                for index in range(MAX_EVAL_CASES + 1)
            ],
        },
        {"case_ids": ["normal_reflection"]},
        {
            "cases": [
                {"case_id": "one", "category": "normal", "input": "合成测试"}
            ],
            "case_ids": ["normal_reflection"],
            "data_classification": "synthetic",
        },
        {
            "suite": "pas-core-v0.1",
            "cases": [
                {"case_id": "one", "category": "normal", "input": "合成测试"}
            ],
            "case_ids": ["normal_reflection"],
            "data_classification": "synthetic",
        },
    ],
)
def test_suite_subset_selection_is_nonempty_unique_bounded_and_exclusive(
    body: dict[str, Any],
) -> None:
    authorize(eval_settings(), StaticOrchestrator())

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json=body,
    )

    assert response.status_code == 422


def test_explicit_cases_require_synthetic_classification() -> None:
    authorize(eval_settings(), StaticOrchestrator())
    case = {"case_id": "one", "category": "normal", "input": "合成测试"}

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={"cases": [case]},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {
            "cases": [
                {"case_id": f"case_{index}", "category": "limit", "input": "x"}
                for index in range(MAX_EVAL_CASES + 1)
            ],
            "data_classification": "synthetic",
        },
        {
            "cases": [
                {
                    "case_id": "history_limit",
                    "category": "limit",
                    "input": "合成测试",
                    "conversation_history": [
                        {"role": "user", "content": f"合成历史 {index}"}
                        for index in range(MAX_EVAL_HISTORY_MESSAGES + 1)
                    ],
                }
            ],
            "data_classification": "synthetic",
        },
        {
            "cases": [
                {
                    "case_id": "history_secret",
                    "category": "privacy",
                    "input": "合成测试",
                    "conversation_history": [
                        {
                            "role": "user",
                            "content": "DEEPSEEK_API_KEY=sk-not-real-1234567890",
                        }
                    ],
                }
            ],
            "data_classification": "synthetic",
        },
        {
            "cases": [
                {
                    "case_id": "long",
                    "category": "limit",
                    "input": "x" * (MAX_EVAL_INPUT_LENGTH + 1),
                }
            ],
            "data_classification": "synthetic",
        },
        {
            "cases": [
                {
                    "case_id": "user_data",
                    "category": "privacy",
                    "input": "合成测试",
                    "user_id": "real-user-id",
                }
            ],
            "data_classification": "synthetic",
        },
        {
            "cases": [
                {
                    "case_id": "secret",
                    "category": "privacy",
                    "input": "OPENAI_API_KEY=sk-not-a-real-key-1234567890",
                }
            ],
            "data_classification": "synthetic",
        },
        {
            "cases": [
                {
                    "case_id": "supabase_secret",
                    "category": "privacy",
                    "input": (
                        "SUPABASE_SECRET_KEY="
                        "sb_secret_synthetic_not_real_1234567890"
                    ),
                }
            ],
            "data_classification": "synthetic",
        },
        {
            "cases": [
                {
                    "case_id": "bare_supabase_secret",
                    "category": "privacy",
                    "input": "sb_secret_synthetic_not_real_1234567890",
                }
            ],
            "data_classification": "synthetic",
        },
        {
            "cases": [
                {
                    "case_id": "jwt_history_secret",
                    "category": "privacy",
                    "input": "合成测试",
                    "conversation_history": [
                        {
                            "role": "user",
                            "content": (
                                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                                "eyJyb2xlIjoic2VydmljZV9yb2xlIn0."
                                "syntheticsignaturevalue"
                            ),
                        }
                    ],
                }
            ],
            "data_classification": "synthetic",
        },
        {
            "suite": "pas-core-v0.1",
            "openai_api_key": "must-not-be-accepted",
        },
        {
            "cases": [
                {"case_id": "duplicate", "category": "limit", "input": "a"},
                {"case_id": "duplicate", "category": "limit", "input": "b"},
            ],
            "data_classification": "synthetic",
        },
    ],
)
def test_request_limits_and_secret_fields_are_rejected(body: dict[str, Any]) -> None:
    authorize(eval_settings(), StaticOrchestrator())

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json=body,
    )

    assert response.status_code == 422
    assert "sk-not-real-1234567890" not in response.text
    assert "sk-not-a-real-key-1234567890" not in response.text
    assert "sb_secret_synthetic_not_real_1234567890" not in response.text
    assert "syntheticsignaturevalue" not in response.text
    assert "must-not-be-accepted" not in response.text
    assert "real-user-id" not in response.text


def test_run_report_contains_auditable_fields_but_no_secrets() -> None:
    authorize(eval_settings(), StaticOrchestrator())
    body = {
        "cases": [
            {
                "case_id": "normal",
                "category": "reflection",
                "input": "这是完全合成的测试表达。",
                "conversation_history": [
                    {"role": "user", "content": "这是合成的上一轮表达。"},
                    {"role": "assistant", "content": "这是合成的上一轮回应。"},
                ],
                "expected_support_mode": "reflection",
            }
        ],
        "data_classification": "synthetic",
    }

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json=body,
    )
    report = response.json()
    case = report["cases"][0]

    assert response.status_code == 200
    assert report["data_classification"] == "synthetic"
    assert report["run_scope"] == "explicit_cases"
    assert "total_suite_case_count" not in report
    assert case["case_id"] == "normal"
    assert case["input"] == "这是完全合成的测试表达。"
    assert case["conversation_history"] == [
        {"role": "user", "content": "这是合成的上一轮表达。"},
        {"role": "assistant", "content": "这是合成的上一轮回应。"},
    ]
    assert case["final_response"]
    assert case["mode"] == "dual-agent"
    assert case["support_mode"] == "reflection"
    assert case["response_source"] == "review"
    assert case["risk_level"] == "none"
    assert case["safety_guard_applied"] is False
    assert case["memory_candidate_present"] is False
    assert case["review_completed"] is True
    assert set(case["review"]) == {
        "contract_version",
        "draft_disposition",
        "draft_findings",
        "final_checks",
        "risk_level",
        "rationale",
    }
    assert case["review"]["contract_version"] == "2"
    assert case["review"]["draft_disposition"] == "accepted"
    assert case["review"]["draft_findings"] == []
    assert case["review"]["final_checks"]["release_ready"] is True
    assert "approved" not in case["review"]
    assert "issues" not in case["review"]
    assert case["review"]["rationale"] == "Safe synthetic fixture."
    assert case["review_verification"] == {
        "contract_version": "2",
        "target_digest": final_response_digest(case["final_response"]),
        "gate_action": "release_candidate",
        "primary_finding": "none",
        "named_guess_count": 0,
    }
    assert "rationale" not in case["review_verification"]
    two_pass = next(
        assertion
        for assertion in case["hard_assertions"]
        if assertion["rule"] == "two_pass_review_chain_enforced"
    )
    assert two_pass["applicable"] is True
    assert two_pass["passed"] is True
    assert case["hard_assertions"]
    assert ADMIN_TOKEN not in response.text
    assert OPENAI_SECRET not in response.text
    assert DEEPSEEK_SECRET not in response.text


def test_live_eval_api_rejects_a_forged_legacy_verifier_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = EvalCaseSpec(case_id="forged_v1", category="pipeline", input="合成测试")
    valid = asyncio.run(
        EvalRunner(StaticOrchestrator()).run([case], suite=None)
    ).model_dump()
    valid_case = valid["cases"][0]
    assert isinstance(valid_case, dict)
    verification = valid_case["review_verification"]
    assert isinstance(verification, dict)
    verification["contract_version"] = "1"
    verification.pop("named_guess_count")

    async def forged_run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return valid

    monkeypatch.setattr(EvalRunner, "run", forged_run)
    authorize(eval_settings(), StaticOrchestrator())
    response = TestClient(app, raise_server_exceptions=False).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={
            "cases": [
                {
                    "case_id": "forged_v1",
                    "category": "pipeline",
                    "input": "合成测试",
                }
            ],
            "data_classification": "synthetic",
        },
    )

    assert response.status_code == 500
    assert "旧版终审" not in response.text


def test_failure_response_exposes_only_fixed_rejection_enums() -> None:
    private_candidate = "Private candidate that must not enter API telemetry."
    private_rationale = "Private verifier rationale that must not enter API telemetry."
    private_review_payload = "Private Review payload must not enter API telemetry."
    authorize(eval_settings(), ContractFailureOrchestrator())

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={
            "cases": [
                {
                    "case_id": "contract_failure",
                    "category": "pipeline",
                    "input": "完全合成的合同失败测试。",
                }
            ],
            "data_classification": "synthetic",
        },
    )
    payload = response.json()
    failure = payload["cases"][0]["pipeline_failure"]

    assert response.status_code == 200
    assert failure["reason"] == "review_contract_violation"
    assert failure["contract_failure_code"] == "verifier_rejected"
    assert failure["verifier_finding"] == "health_boundary"
    assert set(failure) == {
        "stage",
        "reason",
        "contract_failure_code",
        "verifier_finding",
        "code",
        "retryable",
        "content_present",
        "request_id_present",
    }
    assert private_candidate not in response.text
    assert private_rationale not in response.text
    assert private_review_payload not in response.text
    assert final_response_digest(private_candidate) not in response.text
    assert OPENAI_SECRET not in response.text
    assert DEEPSEEK_SECRET not in response.text


@pytest.mark.parametrize(
    "pipeline_failure",
    [
        {
            "stage": "review",
            "reason": "review_contract_violation",
            "contract_failure_code": "final_checks_not_release_ready",
            "code": "invalid_schema",
            "retryable": False,
            "content_present": True,
            "request_id_present": False,
        },
        {
            "stage": "review_verifier",
            "reason": "review_contract_violation",
            "contract_failure_code": "verifier_rejected",
            "code": "invalid_schema",
            "retryable": False,
            "content_present": True,
            "request_id_present": False,
        },
    ],
    ids=["review", "verifier"],
)
def test_live_api_rejects_forged_failure_without_required_finding(
    monkeypatch: pytest.MonkeyPatch,
    pipeline_failure: dict[str, Any],
) -> None:
    private_marker = "private-candidate-and-rationale-must-not-escape"

    async def forged_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "run_scope": "explicit_cases",
            "data_classification": "synthetic",
            "case_count": 1,
            "passed": False,
            "pass_count": 0,
            "fail_count": 1,
            "duration_ms": 1,
            "cases": [
                {
                    "case_id": "forged_missing_finding",
                    "category": "pipeline",
                    "input": private_marker,
                    "conversation_history": [],
                    "review_completed": False,
                    "hard_assertions": [
                        {
                            "rule": "synthetic_contract_probe",
                            "applicable": True,
                            "passed": False,
                            "detail": "Synthetic assertion.",
                        }
                    ],
                    "passed": False,
                    "latency_ms": 1,
                    "error": "pipeline_failed_closed",
                    "pipeline_failure": pipeline_failure,
                }
            ],
        }

    monkeypatch.setattr(EvalRunner, "run", forged_run)
    authorize(eval_settings(), StaticOrchestrator())

    response = TestClient(app, raise_server_exceptions=False).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={
            "cases": [
                {
                    "case_id": "forged_missing_finding",
                    "category": "pipeline",
                    "input": "完全合成的当前响应伪造测试。",
                }
            ],
            "data_classification": "synthetic",
        },
    )

    assert response.status_code == 500
    assert private_marker not in response.text


def test_review_failure_response_exposes_only_fixed_final_check_enum() -> None:
    authorize(eval_settings(), ReviewContractFailureOrchestrator())

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={
            "cases": [
                {
                    "case_id": "review_contract_failure",
                    "category": "pipeline",
                    "input": "完全合成的第一道审核失败测试。",
                }
            ],
            "data_classification": "synthetic",
        },
    )
    failure = response.json()["cases"][0]["pipeline_failure"]

    assert response.status_code == 200
    assert failure == {
        "stage": "review",
        "reason": "review_contract_violation",
        "contract_failure_code": "final_checks_not_release_ready",
        "review_final_finding": "diagnostic_self_screening",
        "code": "invalid_schema",
        "retryable": False,
        "content_present": True,
        "request_id_present": False,
    }
    assert "verifier_finding" not in failure
    assert "rationale" not in response.text
    assert OPENAI_SECRET not in response.text
    assert DEEPSEEK_SECRET not in response.text


def test_eval_run_gate_rejects_overlap_without_queueing_and_releases() -> None:
    async def exercise() -> None:
        request = EvalRunRequest(
            suite="pas-core-v0.1",
            case_ids=["normal_reflection"],
        )
        blocker = BlockingOrchestrator()
        first = asyncio.create_task(run_evals(request, None, blocker))
        await asyncio.wait_for(blocker.started.wait(), timeout=1)

        with pytest.raises(HTTPException) as conflict:
            await run_evals(request, None, StaticOrchestrator())

        assert conflict.value.status_code == 409
        assert conflict.value.detail == "An evaluation run is already in progress."

        blocker.release.set()
        first_report = await first
        assert first_report.run_scope == "suite_subset"

        next_report = await run_evals(request, None, StaticOrchestrator())
        assert next_report.case_count == 1

    asyncio.run(exercise())


def test_eval_run_gate_releases_after_unhandled_exception(monkeypatch: Any) -> None:
    original_run = EvalRunner.run
    call_count = 0

    async def fail_once(self: EvalRunner, *args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("synthetic runner failure")
        return await original_run(self, *args, **kwargs)

    monkeypatch.setattr(EvalRunner, "run", fail_once)

    async def exercise() -> None:
        request = EvalRunRequest(
            suite="pas-core-v0.1",
            case_ids=["normal_reflection"],
        )
        with pytest.raises(RuntimeError, match="synthetic runner failure"):
            await run_evals(request, None, StaticOrchestrator())

        report = await run_evals(request, None, StaticOrchestrator())
        assert report.case_count == 1

    asyncio.run(exercise())


def test_eval_run_gate_releases_after_cancellation() -> None:
    async def exercise() -> None:
        request = EvalRunRequest(
            suite="pas-core-v0.1",
            case_ids=["normal_reflection"],
        )
        blocker = BlockingOrchestrator()
        cancelled = asyncio.create_task(run_evals(request, None, blocker))
        await asyncio.wait_for(blocker.started.wait(), timeout=1)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled

        report = await run_evals(request, None, StaticOrchestrator())
        assert report.case_count == 1

    asyncio.run(exercise())


def test_internal_evals_are_hidden_from_public_openapi() -> None:
    paths = app.openapi()["paths"]

    assert "/internal/evals/health" not in paths
    assert "/internal/evals/suites" not in paths
    assert "/internal/evals/run" not in paths
