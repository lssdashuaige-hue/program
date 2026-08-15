import asyncio
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ai.models import AgentResult, ReviewDecision
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
    EvalRunRequest,
    SuiteName,
)
from app.evals.runner import EvalRunner
from app.evals.suites import get_suite
from app.main import app


ADMIN_TOKEN = "pas-evals-admin-token-32-characters"
OPENAI_SECRET = "provider-openai-secret-value"
DEEPSEEK_SECRET = "provider-deepseek-secret-value"


class StaticOrchestrator:
    async def respond(self, user_message: str, **kwargs: Any) -> AgentResult:
        final = "我听见你正在整理这段体验。哪部分最需要先看清？"
        review = ReviewDecision(
            approved=True,
            final_response=final,
            issues=[],
            risk_level="none",
            rationale="Safe synthetic fixture.",
        )
        return AgentResult(
            response=final,
            mode="dual-agent",
            support_mode="reflection",
            reflection_draft=final,
            review=review,
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
    assert case["review"]["rationale"] == "Safe synthetic fixture."
    assert case["hard_assertions"]
    assert ADMIN_TOKEN not in response.text
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
