import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ai.gateway import GatewayErrorCode, PipelineStage, SafeFinishReason
from app.ai.models import (
    AgentMode,
    MemoryConfidence,
    ResponseSource,
    ReviewIssue,
    RiskLevel,
    SupportMode,
)


MAX_EVAL_CASES = 12
MAX_EVAL_INPUT_LENGTH = 2000
MAX_EVAL_FORBIDDEN_SUBSTRINGS = 12
MAX_EVAL_CONCURRENCY = 3
EVAL_CASE_TIMEOUT_SECONDS = 30.0
EVAL_RUN_TIMEOUT_MARGIN_SECONDS = 15.0
EVAL_RUN_TIMEOUT_SECONDS = (
    (MAX_EVAL_CASES + MAX_EVAL_CONCURRENCY - 1) // MAX_EVAL_CONCURRENCY
) * EVAL_CASE_TIMEOUT_SECONDS + EVAL_RUN_TIMEOUT_MARGIN_SECONDS

SuiteName = Literal["pas-core-v0.1"]
EvalErrorCode = Literal["pipeline_failed_closed", "timeout", "internal_error"]

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:openai|deepseek|model)[_-]?api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bapi[_ -]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def contains_obvious_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


class EvalCaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    category: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    input: str = Field(min_length=1, max_length=MAX_EVAL_INPUT_LENGTH)
    expected_support_mode: SupportMode | None = None
    expected_risk_level: RiskLevel | None = None
    expected_response_source: ResponseSource | None = None
    expect_memory_candidate: bool | None = None
    forbidden_substrings: list[str] = Field(
        default_factory=list,
        max_length=MAX_EVAL_FORBIDDEN_SUBSTRINGS,
    )

    @field_validator("input")
    @classmethod
    def reject_secrets_in_input(cls, value: str) -> str:
        if contains_obvious_secret(value):
            raise ValueError("Evaluation input must not contain credentials or API keys.")
        return value

    @field_validator("forbidden_substrings")
    @classmethod
    def validate_forbidden_substrings(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip()
            if not item or len(item) > 160:
                raise ValueError(
                    "Forbidden substrings must contain 1 to 160 characters."
                )
            if contains_obvious_secret(item):
                raise ValueError("Assertions must not contain credentials or API keys.")
            normalized.append(item)
        return normalized


class EvalRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: SuiteName | None = None
    cases: list[EvalCaseSpec] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_EVAL_CASES,
    )
    data_classification: Literal["synthetic"] | None = None

    @model_validator(mode="after")
    def select_one_synthetic_source(self) -> "EvalRunRequest":
        if (self.suite is None) == (self.cases is None):
            raise ValueError("Select exactly one built-in suite or explicit case list.")
        if self.cases is not None and self.data_classification != "synthetic":
            raise ValueError(
                "Explicit cases require data_classification='synthetic'."
            )
        if self.cases is not None:
            case_ids = [case.case_id for case in self.cases]
            if len(case_ids) != len(set(case_ids)):
                raise ValueError("Evaluation case IDs must be unique.")
        return self


class EvalLimits(BaseModel):
    max_cases: int = MAX_EVAL_CASES
    max_input_characters: int = MAX_EVAL_INPUT_LENGTH
    max_concurrency: int = MAX_EVAL_CONCURRENCY
    case_timeout_seconds: float = EVAL_CASE_TIMEOUT_SECONDS
    run_timeout_seconds: float = EVAL_RUN_TIMEOUT_SECONDS


class EvalHealthReport(BaseModel):
    status: Literal["ready", "provider_unavailable"]
    provider_ready: bool
    default_suite: SuiteName = "pas-core-v0.1"
    limits: EvalLimits = Field(default_factory=EvalLimits)


class EvalSuiteMetadata(BaseModel):
    name: SuiteName
    description: str
    case_count: int
    case_ids: list[str]
    categories: list[str]


class EvalReviewReport(BaseModel):
    completed: bool = True
    approved: bool
    issues: list[ReviewIssue]
    risk_level: RiskLevel
    rationale: str


class EvalAssertionReport(BaseModel):
    rule: str
    applicable: bool
    passed: bool
    detail: str


class EvalPipelineFailureReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: PipelineStage
    code: GatewayErrorCode
    retryable: bool
    content_present: bool
    request_id_present: bool
    http_status: int | None = Field(default=None, ge=400, le=599)
    finish_reason: SafeFinishReason | None = None


class EvalCaseReport(BaseModel):
    case_id: str
    category: str
    input: str
    reflection_draft: str | None = None
    final_response: str | None = None
    mode: AgentMode | None = None
    support_mode: SupportMode | None = None
    response_source: ResponseSource | None = None
    risk_level: RiskLevel | None = None
    safety_guard_applied: bool = False
    memory_candidate_present: bool = False
    memory_candidate_confidence: MemoryConfidence | None = None
    review_completed: bool
    review: EvalReviewReport | None = None
    hard_assertions: list[EvalAssertionReport]
    passed: bool
    latency_ms: int
    error: EvalErrorCode | None = None
    pipeline_failure: EvalPipelineFailureReport | None = None


class EvalRunReport(BaseModel):
    suite: SuiteName | None = None
    data_classification: Literal["synthetic"] = "synthetic"
    case_count: int
    passed: bool
    pass_count: int
    fail_count: int
    duration_ms: int
    cases: list[EvalCaseReport]
