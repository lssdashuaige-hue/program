import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.ai.bounded_responses import bounded_response_candidate
from app.ai.gateway import (
    GatewayErrorCode,
    PipelineStage,
    SafeFinishReason,
    TimeoutOrigin,
)
from app.ai.limits import PIPELINE_TIMEOUT_SECONDS
from app.ai.models import (
    AgentMode,
    BoundedResponseKind,
    BoundaryStatus,
    DraftDisposition,
    FinalVerificationAction,
    FinalVerificationFinding,
    MemoryConfidence,
    ResponseSource,
    ReviewFinalFinding,
    ReviewIssue,
    RiskLevel,
    SourceBasis,
    SupportMode,
    VerifierRejectionFinding,
    explicit_named_guess_lower_bound,
    final_response_digest,
    unavailable_cross_chat_checks_are_exact,
)
from app.ai.orchestrator import PipelineContractFailureCode


MAX_EVAL_CASES = 12
MAX_EVAL_INPUT_LENGTH = 2000
MAX_EVAL_HISTORY_MESSAGES = 8
MAX_EVAL_FORBIDDEN_SUBSTRINGS = 12
MAX_EVAL_REQUIRED_SUBSTRING_GROUPS = 8
MAX_EVAL_REQUIRED_SUBSTRINGS_PER_GROUP = 8
# Two concurrent model pipelines keep the live internal suite below the
# provider-contention level observed with three simultaneous Reflection/Review
# chains, while retaining bounded parallelism.
MAX_EVAL_CONCURRENCY = 2
EVAL_CASE_TIMEOUT_SECONDS = PIPELINE_TIMEOUT_SECONDS
EVAL_RUN_TIMEOUT_MARGIN_SECONDS = 15.0
EVAL_RUN_TIMEOUT_SECONDS = (
    (MAX_EVAL_CASES + MAX_EVAL_CONCURRENCY - 1) // MAX_EVAL_CONCURRENCY
) * EVAL_CASE_TIMEOUT_SECONDS + EVAL_RUN_TIMEOUT_MARGIN_SECONDS

SuiteName = Literal["pas-core-v0.1", "pas-dialogue-v0.1"]
EvalRunScope = Literal["full_suite", "suite_subset", "explicit_cases"]
EvalErrorCode = Literal["pipeline_failed_closed", "timeout", "internal_error"]
EvalPipelineFailureReason = Literal["gateway_error", "review_contract_violation"]
EvalCaseId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    ),
]

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:openai|deepseek|model)[_-]?api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bapi[_ -]?key\s*[:=]\s*\S+"),
    re.compile(
        r"(?i)\bsupabase[_-]?(?:secret|service[_-]?role|publishable|anon)"
        r"[_-]?key\s*[:=]\s*\S+"
    ),
    re.compile(r"(?i)\bsb_(?:secret|publishable)_[a-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
)


def contains_obvious_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


class EvalContextMessageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_EVAL_INPUT_LENGTH)

    @field_validator("content")
    @classmethod
    def validate_synthetic_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Evaluation history content must not be blank.")
        if contains_obvious_secret(value):
            raise ValueError(
                "Evaluation history must not contain credentials or API keys."
            )
        return value


class EvalCaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: EvalCaseId
    category: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    input: str = Field(min_length=1, max_length=MAX_EVAL_INPUT_LENGTH)
    conversation_history: list[EvalContextMessageSpec] = Field(
        default_factory=list,
        max_length=MAX_EVAL_HISTORY_MESSAGES,
    )
    expected_support_mode: SupportMode | None = None
    expected_risk_level: RiskLevel | None = None
    expected_response_source: ResponseSource | None = None
    expected_bounded_response_kind: BoundedResponseKind | None = None
    forbid_bounded_response_path: bool = False
    expect_memory_candidate: bool | None = None
    forbidden_substrings: list[str] = Field(
        default_factory=list,
        max_length=MAX_EVAL_FORBIDDEN_SUBSTRINGS,
    )
    required_any_substring_groups: list[list[str]] = Field(
        default_factory=list,
        max_length=MAX_EVAL_REQUIRED_SUBSTRING_GROUPS,
    )
    expect_tentative_language: bool = False
    expect_cross_conversation_boundary: bool = False
    expect_observer_working_description: bool = False
    forbid_diagnostic_checklist: bool = False
    forbid_unfounded_numeric_precision: bool = False
    forbid_generic_assent_upgrade: bool = False
    forbid_undefined_code_expansion: bool = False
    expected_named_guess_count_min: int | None = Field(default=None, ge=0, le=2)
    expected_named_guess_count_max: int | None = Field(default=None, ge=0, le=2)
    min_response_characters: int = Field(default=0, ge=0, le=500)

    @model_validator(mode="after")
    def validate_bounded_response_expectation(self) -> "EvalCaseSpec":
        if (
            self.expected_bounded_response_kind is not None
            and self.forbid_bounded_response_path
        ):
            raise ValueError(
                "A case cannot both require and forbid the bounded response path."
            )
        if (
            self.expected_bounded_response_kind is not None
            and self.expected_response_source not in {None, "review"}
        ):
            raise ValueError(
                "A bounded response expectation requires the reviewed response source."
            )
        if (
            self.expected_named_guess_count_min is not None
            and self.expected_named_guess_count_max is not None
            and self.expected_named_guess_count_min
            > self.expected_named_guess_count_max
        ):
            raise ValueError(
                "The minimum expected named-guess count cannot exceed the maximum."
            )
        return self

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

    @field_validator("required_any_substring_groups")
    @classmethod
    def validate_required_substring_groups(
        cls,
        groups: list[list[str]],
    ) -> list[list[str]]:
        normalized_groups: list[list[str]] = []
        for group in groups:
            if not group or len(group) > MAX_EVAL_REQUIRED_SUBSTRINGS_PER_GROUP:
                raise ValueError(
                    "Required substring groups must contain 1 to 8 alternatives."
                )
            normalized_group: list[str] = []
            for value in group:
                item = value.strip()
                if not item or len(item) > 160:
                    raise ValueError(
                        "Required substrings must contain 1 to 160 characters."
                    )
                if contains_obvious_secret(item):
                    raise ValueError(
                        "Assertions must not contain credentials or API keys."
                    )
                normalized_group.append(item)
            normalized_groups.append(normalized_group)
        return normalized_groups


class EvalRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: SuiteName | None = None
    cases: list[EvalCaseSpec] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_EVAL_CASES,
    )
    case_ids: list[EvalCaseId] | None = Field(
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
        if self.case_ids is not None:
            if self.suite is None:
                raise ValueError("case_ids can only select cases from a built-in suite.")
            if len(self.case_ids) != len(set(self.case_ids)):
                raise ValueError("Selected evaluation case IDs must be unique.")
        if self.cases is not None:
            case_ids = [case.case_id for case in self.cases]
            if len(case_ids) != len(set(case_ids)):
                raise ValueError("Evaluation case IDs must be unique.")
        return self


class EvalLimits(BaseModel):
    max_cases: int = MAX_EVAL_CASES
    max_input_characters: int = MAX_EVAL_INPUT_LENGTH
    max_history_messages: int = MAX_EVAL_HISTORY_MESSAGES
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


class EvalFinalResponseChecksReport(BaseModel):
    """Serializable, independently validated view of Review's release checks."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source_bases: list[SourceBasis] = Field(min_length=1, max_length=5)
    source_attribution_ok: bool
    adds_unreported_user_fact: bool
    adds_unreported_third_party_fact: bool
    promotes_prior_ai_hypothesis: bool
    named_guess_count: int = Field(ge=0, le=12)
    diagnostic_self_screening_present: bool
    health_boundary: BoundaryStatus
    cross_chat_boundary: BoundaryStatus = Field(
        description=(
            "'satisfied' means relevant cross-chat provenance is handled by an "
            "explicit access denial or accurate attribution to material the user "
            "brought here; neither is a violation. 'violated' means the response "
            "claims unavailable cross-chat material or conclusions were "
            "accessible or used. 'not_applicable' is only for responses where "
            "cross-chat provenance or use is irrelevant."
        )
    )
    other_pas_requirements_ok: bool
    release_ready: bool

    @field_validator("source_bases")
    @classmethod
    def require_unique_source_bases(
        cls,
        values: list[SourceBasis],
    ) -> list[SourceBasis]:
        if len(values) != len(set(values)):
            raise ValueError("Evaluation Review source bases must be unique.")
        return values

    @model_validator(mode="after")
    def validate_release_ready(self) -> "EvalFinalResponseChecksReport":
        derived_release_ready = (
            self.source_attribution_ok
            and not self.adds_unreported_user_fact
            and not self.adds_unreported_third_party_fact
            and not self.promotes_prior_ai_hypothesis
            and self.named_guess_count <= 2
            and not self.diagnostic_self_screening_present
            and self.health_boundary != "violated"
            and self.cross_chat_boundary != "violated"
            and self.other_pas_requirements_ok
        )
        if self.release_ready != derived_release_ready:
            raise ValueError(
                "Evaluation Review release_ready must match its structured checks."
            )
        return self


class EvalReviewReport(BaseModel):
    """Auditable Review v2 data; legacy approval aliases are intentionally absent."""

    model_config = ConfigDict(extra="forbid", strict=True)

    contract_version: Literal["2"]
    draft_disposition: DraftDisposition
    draft_findings: list[ReviewIssue] = Field(max_length=17)
    final_checks: EvalFinalResponseChecksReport
    risk_level: RiskLevel
    rationale: str = Field(min_length=1, max_length=1200)

    @field_validator("draft_findings")
    @classmethod
    def require_unique_draft_findings(
        cls,
        values: list[ReviewIssue],
    ) -> list[ReviewIssue]:
        if len(values) != len(set(values)):
            raise ValueError("Evaluation Review findings must be unique.")
        return values

    @model_validator(mode="after")
    def validate_draft_disposition(self) -> "EvalReviewReport":
        if self.draft_disposition == "accepted" and self.draft_findings:
            raise ValueError("An accepted draft cannot contain findings.")
        if self.draft_disposition == "rewritten" and not self.draft_findings:
            raise ValueError("A rewritten draft requires at least one finding.")
        return self


class EvalFinalVerificationReport(BaseModel):
    """Strict, non-narrative view of the independent final release gate."""

    model_config = ConfigDict(extra="forbid", strict=True)

    contract_version: Literal["1", "2"]
    target_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_action: FinalVerificationAction
    primary_finding: FinalVerificationFinding
    named_guess_count: int | None = Field(default=None, ge=0, le=12)

    @model_validator(mode="after")
    def validate_gate_finding_pair(self) -> "EvalFinalVerificationReport":
        if self.contract_version == "1" and self.named_guess_count is not None:
            raise ValueError(
                "Legacy Final Verification v1 reports cannot claim a v2 guess count."
            )
        if self.contract_version == "2" and self.named_guess_count is None:
            raise ValueError(
                "Final Verification v2 reports require the independent guess count."
            )
        if (
            self.gate_action == "release_candidate"
            and self.primary_finding != "none"
        ):
            raise ValueError("A released candidate cannot contain a finding.")
        if (
            self.gate_action == "reject_candidate"
            and self.primary_finding == "none"
        ):
            raise ValueError("A rejected candidate requires a finding.")
        if (
            self.contract_version == "2"
            and self.gate_action == "release_candidate"
            and self.named_guess_count is not None
            and self.named_guess_count > 2
        ):
            raise ValueError("A v2 release cannot exceed the guess limit.")
        return self


class EvalAssertionReport(BaseModel):
    rule: str
    applicable: bool
    passed: bool
    detail: str


class EvalPipelineFailureReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    stage: PipelineStage
    reason: EvalPipelineFailureReason
    contract_failure_code: PipelineContractFailureCode | None = None
    review_final_finding: ReviewFinalFinding | None = None
    verifier_finding: VerifierRejectionFinding | None = None
    code: GatewayErrorCode
    retryable: bool
    content_present: bool
    request_id_present: bool
    http_status: int | None = Field(default=None, ge=400, le=599)
    finish_reason: SafeFinishReason | None = None
    timeout_origin: TimeoutOrigin | None = None
    attempt_index: int | None = Field(default=None, ge=1, le=8)
    attempt_limit: int | None = Field(default=None, ge=1, le=8)
    stage_elapsed_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    stage_timeout_ms: int | None = Field(default=None, ge=1, le=3_600_000)

    @model_validator(mode="after")
    def validate_safe_diagnostic_shape(
        self,
        info: ValidationInfo,
    ) -> "EvalPipelineFailureReport":
        review_contract_failures = {
            "draft_disposition_mismatch",
            "source_basis_unavailable",
            "final_checks_not_release_ready",
            "question_limit_exceeded",
            "bounded_candidate_not_accepted",
        }
        verifier_contract_failures = {
            "verifier_unavailable",
            "verifier_rejected",
            "verifier_digest_mismatch",
        }
        verifier_rejection = (
            self.stage == "review_verifier"
            and self.reason == "review_contract_violation"
            and self.contract_failure_code == "verifier_rejected"
            and self.code == "invalid_schema"
        )
        review_final_rejection = (
            self.stage == "review"
            and self.reason == "review_contract_violation"
            and self.contract_failure_code == "final_checks_not_release_ready"
            and self.code == "invalid_schema"
        )
        historical_import = (
            isinstance(info.context, dict)
            and info.context.get("eval_report_origin") == "historical_import"
        )
        if (
            self.review_final_finding is not None
            and self.verifier_finding is not None
        ):
            raise ValueError(
                "Evaluation failures cannot contain both Review and verifier findings."
            )
        if self.review_final_finding is not None and not review_final_rejection:
            raise ValueError(
                "Evaluation Review findings require the fixed final-check shape."
            )
        if self.verifier_finding is not None and not verifier_rejection:
            raise ValueError(
                "Evaluation verifier findings require the fixed rejection shape."
            )
        if (
            review_final_rejection
            and self.review_final_finding is None
            and not historical_import
        ):
            raise ValueError(
                "Current Review final-check failures require exactly one fixed finding."
            )
        if (
            verifier_rejection
            and self.verifier_finding is None
            and not historical_import
        ):
            raise ValueError(
                "Current verifier rejections require exactly one fixed finding."
            )
        if self.reason == "gateway_error":
            if self.contract_failure_code is not None:
                raise ValueError(
                    "Evaluation gateway failures cannot contain a contract code."
                )
        else:
            if self.contract_failure_code is None:
                raise ValueError(
                    "Evaluation contract failures require a fixed failure code."
                )
            if self.code != "invalid_schema":
                raise ValueError(
                    "Evaluation contract failures require invalid-schema diagnostics."
                )
            if (
                self.contract_failure_code in review_contract_failures
                and self.stage != "review"
            ):
                raise ValueError(
                    "Evaluation Review contract codes require the Review stage."
                )
            if (
                self.contract_failure_code in verifier_contract_failures
                and self.stage != "review_verifier"
            ):
                raise ValueError(
                    "Evaluation verifier contract codes require its own stage."
                )
        if (self.attempt_index is None) != (self.attempt_limit is None):
            raise ValueError(
                "Evaluation attempt index and limit must be provided together."
            )
        if (
            self.attempt_index is not None
            and self.attempt_limit is not None
            and self.attempt_index > self.attempt_limit
        ):
            raise ValueError("Evaluation attempt index cannot exceed its limit.")
        if self.timeout_origin is not None and self.code != "provider_timeout":
            raise ValueError(
                "Evaluation timeout origin requires a provider timeout code."
            )
        return self


class EvalCaseReport(BaseModel):
    case_id: str
    category: str
    input: str
    conversation_history: list[EvalContextMessageSpec] = Field(default_factory=list)
    reflection_draft: str | None = None
    final_response: str | None = None
    mode: AgentMode | None = None
    support_mode: SupportMode | None = None
    response_source: ResponseSource | None = None
    bounded_response_kind: BoundedResponseKind | None = None
    risk_level: RiskLevel | None = None
    safety_guard_applied: bool = False
    memory_candidate_present: bool = False
    memory_candidate_confidence: MemoryConfidence | None = None
    review_completed: bool
    review: EvalReviewReport | None = None
    review_verification: EvalFinalVerificationReport | None = None
    hard_assertions: list[EvalAssertionReport]
    passed: bool
    latency_ms: int
    error: EvalErrorCode | None = None
    pipeline_failure: EvalPipelineFailureReport | None = None

    @model_validator(mode="after")
    def validate_review_completion(self) -> "EvalCaseReport":
        reconstructed_candidate = (
            bounded_response_candidate(self.input)
            if self.response_source == "review"
            else None
        )
        reconstructed_kind = (
            reconstructed_candidate.kind
            if reconstructed_candidate is not None
            else None
        )
        if self.response_source == "review":
            if self.bounded_response_kind != reconstructed_kind:
                raise ValueError(
                    "Evaluation bounded provenance must match the case input."
                )
            if reconstructed_candidate is not None and (
                self.reflection_draft != reconstructed_candidate.response
                or self.final_response != reconstructed_candidate.response
            ):
                raise ValueError(
                    "Evaluation bounded output must preserve the exact candidate."
                )

        if self.response_source == "review":
            if (
                self.final_response is not None
                and explicit_named_guess_lower_bound(self.final_response) > 2
            ):
                raise ValueError(
                    "A current evaluation response cannot contain an explicit "
                    "three-or-more causal list missed by both model gates."
                )
            if (
                self.review_verification is not None
                and self.review_verification.contract_version != "2"
            ):
                raise ValueError(
                    "Legacy Final Verification reports cannot enter a current "
                    "evaluation case."
                )
            complete = (
                self.review is not None
                and self.review_verification is not None
                and self.final_response is not None
                and self.review_verification.contract_version == "2"
                and self.review_verification.gate_action == "release_candidate"
                and self.review_verification.primary_finding == "none"
                and self.review_verification.named_guess_count is not None
                and self.review_verification.named_guess_count <= 2
                and self.review_verification.target_digest
                == final_response_digest(self.final_response)
            )
        elif self.response_source == "review_safety_envelope":
            complete = self.review is not None and self.review_verification is None
        else:
            complete = False
            if self.review_verification is not None:
                raise ValueError(
                    "Only the normal Review path can contain Final Verification."
                )

        if self.review_completed != complete:
            raise ValueError(
                "Evaluation review_completed must reflect the applicable release chain."
            )
        if self.bounded_response_kind is not None:
            bounded_provenance_valid = (
                self.response_source == "review"
                and self.review_completed
                and self.review is not None
                and self.review.draft_disposition == "accepted"
                and not self.review.draft_findings
                and self.review.final_checks.release_ready
                and self.review.risk_level == "none"
                and self.reflection_draft is not None
                and self.reflection_draft == self.final_response
                and not self.memory_candidate_present
                and self.memory_candidate_confidence is None
            )
            if not bounded_provenance_valid:
                raise ValueError(
                    "A bounded response report requires exact accepted provenance and no memory."
                )
            if self.bounded_response_kind == "unavailable_cross_chat_context":
                if (
                    not unavailable_cross_chat_checks_are_exact(
                        source_bases=list(self.review.final_checks.source_bases),
                        named_guess_count=self.review.final_checks.named_guess_count,
                        diagnostic_self_screening_present=(
                            self.review.final_checks.diagnostic_self_screening_present
                        ),
                        health_boundary=self.review.final_checks.health_boundary,
                        cross_chat_boundary=(
                            self.review.final_checks.cross_chat_boundary
                        ),
                    )
                    or self.review_verification is None
                    or self.review_verification.named_guess_count != 0
                ):
                    raise ValueError(
                        "The unavailable cross-chat report requires the exact "
                        "structured two-gate boundary."
                    )
        return self


class EvalRunReport(BaseModel):
    suite: SuiteName | None = None
    run_scope: EvalRunScope
    total_suite_case_count: int | None = Field(
        default=None,
        ge=1,
        le=MAX_EVAL_CASES,
    )
    data_classification: Literal["synthetic"] = "synthetic"
    case_count: int
    passed: bool
    pass_count: int
    fail_count: int
    duration_ms: int
    cases: list[EvalCaseReport]

    @model_validator(mode="after")
    def validate_run_scope(self) -> "EvalRunReport":
        derived_pass_count = sum(case.passed for case in self.cases)
        if self.case_count != len(self.cases):
            raise ValueError("Evaluation case_count must match the case list.")
        if self.pass_count != derived_pass_count:
            raise ValueError("Evaluation pass_count must count passing cases.")
        if self.fail_count != self.case_count - self.pass_count:
            raise ValueError("Evaluation fail_count must count failing cases.")
        if self.passed != (self.pass_count == self.case_count):
            raise ValueError("Evaluation run status must match its case counts.")

        if self.run_scope == "explicit_cases":
            if self.suite is not None or self.total_suite_case_count is not None:
                raise ValueError(
                    "Explicit-case reports cannot claim built-in suite coverage."
                )
            return self

        if self.suite is None or self.total_suite_case_count is None:
            raise ValueError("Suite reports require suite coverage metadata.")
        if self.total_suite_case_count < self.case_count:
            raise ValueError("Suite coverage cannot be smaller than the run case count.")
        if (
            self.run_scope == "full_suite"
            and self.total_suite_case_count != self.case_count
        ):
            raise ValueError("Full-suite reports must cover every case in the suite.")
        return self
