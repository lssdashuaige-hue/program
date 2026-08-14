from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.models import AgentResult, ReviewDecision
from app.api.chat import get_orchestrator
from app.config import Settings, get_settings
from app.evals.models import MAX_EVAL_CASES, MAX_EVAL_INPUT_LENGTH
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
    assert suites.status_code == 200
    assert suites.json()[0]["name"] == "pas-core-v0.1"
    assert suites.json()[0]["case_count"] == MAX_EVAL_CASES


def test_run_requires_a_configured_reviewed_pipeline() -> None:
    authorize(eval_settings(), None)

    response = TestClient(app).post(
        "/internal/evals/run",
        headers=auth_headers(),
        json={"suite": "pas-core-v0.1"},
    )

    assert response.status_code == 503


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
    assert "sk-not-a-real-key-1234567890" not in response.text
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
    assert case["case_id"] == "normal"
    assert case["input"] == "这是完全合成的测试表达。"
    assert case["final_response"]
    assert case["mode"] == "dual-agent"
    assert case["support_mode"] == "reflection"
    assert case["memory_candidate_present"] is False
    assert case["review_completed"] is True
    assert case["review"]["rationale"] == "Safe synthetic fixture."
    assert case["hard_assertions"]
    assert ADMIN_TOKEN not in response.text
    assert OPENAI_SECRET not in response.text
    assert DEEPSEEK_SECRET not in response.text


def test_internal_evals_are_hidden_from_public_openapi() -> None:
    paths = app.openapi()["paths"]

    assert "/internal/evals/health" not in paths
    assert "/internal/evals/suites" not in paths
    assert "/internal/evals/run" not in paths
