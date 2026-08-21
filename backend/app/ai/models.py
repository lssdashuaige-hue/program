import hashlib
import re
import unicodedata
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ReviewIssue = Literal[
    "diagnosis",
    "labeling",
    "overcertainty",
    "negative_belief_reinforcement",
    "dependency",
    "autonomy_violation",
    "reality_detachment",
    "crisis_mishandling",
    "pas_principle_violation",
    "source_attribution",
    "unreported_user_fact",
    "unreported_third_party_fact",
    "prior_ai_hypothesis_promotion",
    "guess_limit",
    "diagnostic_self_screening",
    "health_boundary",
    "cross_chat_boundary",
]

DraftDisposition = Literal["accepted", "rewritten"]
SourceBasis = Literal[
    "current_user_message",
    "supplied_user_history",
    "supplied_assistant_history_as_ai_output",
    "tentative_inference",
    "general_knowledge",
]
BoundaryStatus = Literal["not_applicable", "satisfied", "violated"]

RiskLevel = Literal["none", "concerning", "urgent"]
AgentMode = Literal["dual-agent", "multi-agent", "safety-guard"]
BoundedResponseKind = Literal[
    "third_party_private_state",
    "single_chat_diagnostic_request",
    "personal_lifespan_conversion",
    "unavailable_cross_chat_context",
]
_HEALTH_BOUNDARY_BOUNDED_RESPONSE_KINDS = frozenset(
    {
        "single_chat_diagnostic_request",
        "personal_lifespan_conversion",
    }
)
ResponseSource = Literal[
    "review",
    "safety_guard",
    "review_safety_envelope",
    "safe_fallback",
]
SupportMode = Literal["reflection", "support"]
MemoryKind = Literal["experience", "reflection", "pattern", "need"]
MemoryConfidence = Literal["low", "medium"]
FinalVerificationAction = Literal["release_candidate", "reject_candidate"]
VerifierRejectionFinding = Literal[
    "source_attribution",
    "unreported_user_fact",
    "unreported_third_party_fact",
    "prior_ai_hypothesis_promotion",
    "guess_limit",
    "health_boundary",
    "cross_chat_boundary",
    "autonomy_violation",
    "pas_principle_violation",
]
FinalVerificationFinding = Literal["none"] | VerifierRejectionFinding
VERIFIER_REJECTION_FINDINGS = frozenset(get_args(VerifierRejectionFinding))
ReviewFinalFinding = Literal[
    "source_attribution",
    "unreported_user_fact",
    "unreported_third_party_fact",
    "prior_ai_hypothesis_promotion",
    "guess_limit",
    "diagnostic_self_screening",
    "health_boundary",
    "cross_chat_boundary",
    "pas_principle_violation",
]
REVIEW_FINAL_FINDINGS = frozenset(get_args(ReviewFinalFinding))


class FinalResponseChecks(BaseModel):
    """Review's structured audit of its own final response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source_bases: list[SourceBasis] = Field(min_length=1, max_length=5)
    source_attribution_ok: bool
    adds_unreported_user_fact: bool = Field(
        description=(
            "True only when the final response adds an experience, symptom, "
            "duration, motive, history, preference, endorsement, bodily state, "
            "or other fact that the user did not report. The smallest obvious "
            "character or Chinese/pinyin lexical repair is not a new user fact "
            "when the response preserves only the reported states and leaves "
            "their relationship and cause unknown."
        )
    )
    adds_unreported_third_party_fact: bool = Field(
        description=(
            "True only when the final response adds an unsourced fact, history, "
            "motive, intention, private state, or fixed capacity about a "
            "concrete, user-related, or identifiable third person. A correctly "
            "sourced group-level methodological limitation or a conditional "
            "reference to a generic professional role is not itself a third-party "
            "fact; it must still pass source-attribution and all other PAS checks."
        )
    )
    promotes_prior_ai_hypothesis: bool
    named_guess_count: int = Field(
        ge=0,
        le=12,
        description=(
            "Count only explanatory possibilities, causes, mechanisms, or "
            "alternative domains proposed by the assistant in final_response. "
            "Do not count states faithfully repeated from the current user "
            "message, the smallest obvious character or Chinese/pinyin lexical "
            "repair, or an explicit statement that the relationship and cause "
            "remain unknown. A response that only preserves several reported "
            "states and adds no explanation has count zero."
        ),
    )
    diagnostic_self_screening_present: bool
    health_boundary: BoundaryStatus
    cross_chat_boundary: BoundaryStatus = Field(
        description=(
            "Use 'satisfied' when cross-chat provenance is relevant and the final "
            "response either explicitly denies access to unavailable chats and "
            "relies only on material visible or supplied here, or accurately "
            "attributes imported material to the user's report without claiming "
            "access. An access denial, an invitation to paste or summarize, and "
            "accurate user attribution satisfy the boundary; they are not "
            "violations. Use 'violated' only when the response claims unavailable "
            "cross-chat material or a conclusion from it is accessible or was "
            "used. Use 'not_applicable' only when cross-chat provenance or use is "
            "not relevant to the response."
        )
    )
    other_pas_requirements_ok: bool = Field(
        description=(
            "True only when every remaining PAS requirement passes. Do not set "
            "this false merely because a response makes an obvious low-risk "
            "character or Chinese/pinyin repair while preserving only the "
            "user-reported states, keeping their relationship and cause unknown, "
            "and optionally allowing correction. Added facts, causes, mechanisms, "
            "multiple questions, or other PAS violations still require false."
        )
    )

    @field_validator("source_bases")
    @classmethod
    def require_unique_source_bases(
        cls,
        values: list[SourceBasis],
    ) -> list[SourceBasis]:
        if len(values) != len(set(values)):
            raise ValueError("Final response source bases must be unique.")
        return values

    @property
    def release_ready(self) -> bool:
        return (
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


def unavailable_cross_chat_checks_are_exact(
    *,
    source_bases: list[str],
    named_guess_count: int,
    diagnostic_self_screening_present: bool,
    health_boundary: str,
    cross_chat_boundary: str,
) -> bool:
    """Require the structured Review fields implied by the fixed candidate."""

    return (
        set(source_bases) == {"current_user_message", "general_knowledge"}
        and named_guess_count == 0
        and not diagnostic_self_screening_present
        and health_boundary == "not_applicable"
        and cross_chat_boundary == "satisfied"
    )


def personal_lifespan_review_finding(
    *,
    source_bases: list[str],
    named_guess_count: int,
    diagnostic_self_screening_present: bool,
    health_boundary: str,
    cross_chat_boundary: str,
) -> ReviewFinalFinding | None:
    """Return the first mismatch in the fixed lifespan candidate metadata."""

    if set(source_bases) != {"current_user_message", "general_knowledge"}:
        return "source_attribution"
    if named_guess_count != 0:
        return "guess_limit"
    if diagnostic_self_screening_present:
        return "diagnostic_self_screening"
    if health_boundary != "satisfied":
        return "health_boundary"
    if cross_chat_boundary != "not_applicable":
        return "cross_chat_boundary"
    return None


def personal_lifespan_checks_are_exact(
    *,
    source_bases: list[str],
    named_guess_count: int,
    diagnostic_self_screening_present: bool,
    health_boundary: str,
    cross_chat_boundary: str,
) -> bool:
    """Require every deterministic Review field implied by the fixed answer."""

    return personal_lifespan_review_finding(
        source_bases=source_bases,
        named_guess_count=named_guess_count,
        diagnostic_self_screening_present=diagnostic_self_screening_present,
        health_boundary=health_boundary,
        cross_chat_boundary=cross_chat_boundary,
    ) is None


def bounded_response_health_boundary_is_satisfied(
    bounded_response_kind: BoundedResponseKind | None,
    health_boundary: BoundaryStatus,
) -> bool:
    """Require explicit health-boundary satisfaction for health fixed routes."""

    return (
        bounded_response_kind not in _HEALTH_BOUNDARY_BOUNDED_RESPONSE_KINDS
        or health_boundary == "satisfied"
    )


def primary_review_final_finding(
    checks: FinalResponseChecks,
) -> ReviewFinalFinding | None:
    """Reduce failed Review checks to one fixed, non-content diagnostic."""

    if not checks.source_attribution_ok:
        return "source_attribution"
    if checks.adds_unreported_user_fact:
        return "unreported_user_fact"
    if checks.adds_unreported_third_party_fact:
        return "unreported_third_party_fact"
    if checks.promotes_prior_ai_hypothesis:
        return "prior_ai_hypothesis_promotion"
    if checks.named_guess_count > 2:
        return "guess_limit"
    if checks.diagnostic_self_screening_present:
        return "diagnostic_self_screening"
    if checks.health_boundary == "violated":
        return "health_boundary"
    if checks.cross_chat_boundary == "violated":
        return "cross_chat_boundary"
    if not checks.other_pas_requirements_ok:
        return "pas_principle_violation"
    return None


class ReviewDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    contract_version: Literal["2"]
    draft_disposition: DraftDisposition = Field(
        description=(
            "Use accepted only when final_response is the Reflection draft "
            "unchanged apart from formatting and draft_findings is empty. Use "
            "rewritten only when at least one draft finding exists and "
            "final_response is meaningfully different from the draft."
        )
    )
    draft_findings: list[ReviewIssue] = Field(
        max_length=17,
        description=(
            "Issues found in the Reflection draft only. This list must be empty "
            "for accepted and non-empty for rewritten; auditing a safe draft is "
            "not itself a finding."
        ),
    )
    final_response: str = Field(
        min_length=1,
        max_length=12000,
        description=(
            "Copy the Reflection draft unchanged when draft_disposition is "
            "accepted. When rewritten, materially change the draft and resolve "
            "every listed draft finding."
        ),
    )
    final_checks: FinalResponseChecks
    risk_level: RiskLevel
    rationale: str = Field(
        min_length=1,
        max_length=1200,
        description="Short internal explanation. Never show this field to the user.",
    )

    @field_validator("draft_findings")
    @classmethod
    def require_unique_draft_findings(
        cls,
        values: list[ReviewIssue],
    ) -> list[ReviewIssue]:
        if len(values) != len(set(values)):
            raise ValueError("Review draft findings must be unique.")
        return values

    @model_validator(mode="after")
    def validate_draft_disposition(self) -> "ReviewDecision":
        if self.draft_disposition == "accepted" and self.draft_findings:
            raise ValueError("An accepted draft cannot contain findings.")
        if self.draft_disposition == "rewritten" and not self.draft_findings:
            raise ValueError("A rewritten draft requires at least one finding.")
        return self

    @property
    def approved(self) -> bool:
        """Compatibility view for internal consumers; not part of input JSON."""

        return self.draft_disposition == "accepted"

    @property
    def issues(self) -> list[ReviewIssue]:
        """Compatibility view for internal consumers; not part of input JSON."""

        return list(self.draft_findings)


class FinalVerificationDecision(BaseModel):
    """A non-rewriting release decision for one exact Review candidate."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    contract_version: Literal["2"]
    target_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_action: FinalVerificationAction
    primary_finding: FinalVerificationFinding
    named_guess_count: int = Field(
        ge=0,
        le=12,
        description=(
            "Independent count of every assistant-proposed, named or exemplified "
            "explanation, cause, mechanism, or alternative domain in the exact "
            "candidate. Do not count states faithfully repeated from the user, "
            "the smallest obvious character or Chinese/pinyin lexical repair, "
            "or a statement that their relationship and cause remain unknown. "
            "Several reported states with no proposed explanation count as zero."
        ),
    )
    rationale: str = Field(
        min_length=1,
        max_length=600,
        description="Short internal explanation. Never show this field to the user.",
    )

    @field_validator("rationale")
    @classmethod
    def require_meaningful_rationale(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Final Verification rationale must be meaningful.")
        return stripped

    @model_validator(mode="after")
    def validate_gate_finding_pair(self) -> "FinalVerificationDecision":
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
        return self


_ZH_NAMED_CAUSAL_LIST_PATTERN = re.compile(
    r"(?:还|尚)?看不出(?:来)?(?:是)?因为\s*"
    r"(?P<items>[^。！？?\n]{1,120})|"
    r"(?:可能|也许|或许)(?:还|也)?(?:是|来自|与)\s*"
    r"(?P<possibilities>[^。！？?\n]{1,120})|"
    r"(?:原因|解释|机制|方向|因素|影响因素)(?:可能)?(?:包括|有|是)\s*"
    r"(?P<directions>[^。！？?\n]{1,120})|"
    r"(?:^|[。！？?；;\n])\s*"
    r"(?!你(?:说|提到|问|想知道)|用户|当前消息|你的问题)"
    r"(?P<postposed_items>[^。！？?；;\n]{1,120}?)\s*"
    r"(?:(?:都|也)\s*)?(?<!不)(?:可能|也许|或许)\s*"
    r"(?:(?:都|也)\s*)?(?:会|有)?\s*"
    r"(?:影响|相关|有关|起作用|导致|参与其中|"
    r"(?:是|算是|构成)(?:一个|一些)?(?:因素|原因|解释|方向))",
    re.IGNORECASE,
)
_EN_NAMED_CAUSAL_LIST_PATTERN = re.compile(
    r"(?:could|might|may)(?:\s+also)?\s+"
    r"(?:be|involve|come\s+from|relate\s+to)\s+"
    r"(?P<items>[^.!?\n]{1,160})|"
    r"(?:cannot|can't|can not|unclear|unknown)[^.!?\n]{0,28}"
    r"(?:whether|if)\s+(?:the\s+)?(?:cause|reason|explanation)\s+"
    r"(?:is|involves?)\s+(?P<uncertain_items>[^.!?\n]{1,160})|"
    r"(?:causes?|explanations?|mechanisms?|directions?|contributors?|factors?)\s+"
    r"(?:could\s+include|may\s+include|include|are)\s+"
    r"(?P<directions>[^.!?\n]{1,160})|"
    r"(?:^|[.!?;\n])\s*"
    r"(?!the\s+(?:user|response|message)\b|"
    r"you\s+(?:said|mentioned|asked)\b|your\s+(?:question|wording)\b)"
    r"(?P<postposed_items>[^.!?;\n]{1,160}?)\s+"
    r"(?:(?:can|could|might|may)\s+(?:(?:all|each|possibly|also)\s+)*"
    r"(?:contribute|matter|affect|be\s+contributing|"
    r"play\s+(?:a\s+)?role|have\s+(?:an?\s+)?effect|be\s+involved|"
    r"be\s+(?:contributing\s+)?"
    r"(?:causes?|factors?|explanations?|directions?))|"
    r"(?:are|seem)\s+(?:all\s+)?(?:possible\s+)?"
    r"(?:contributors?|factors?|causes?|explanations?|directions?))",
    re.IGNORECASE,
)
_ZH_NAMED_LIST_SEPARATOR = re.compile(r"\s*(?:、|以及|或者|或|和)\s*")
_EN_NAMED_LIST_SEPARATOR = re.compile(r"\s*(?:,|\band\b|\bor\b)\s*", re.IGNORECASE)
_ZH_UNNAMED_LIST_TAIL = re.compile(
    r"(?:，|,)?\s*(?:还是)?(?:别的|其他|其它|未命名|未知)[^，,。！？?\n]*|"
    r"(?:，|,)?\s*(?:具体|实际)?原因(?:还|仍|尚|并)?[^，,。！？?\n]*",
    re.IGNORECASE,
)
_EN_UNNAMED_LIST_TAIL = re.compile(
    r",?\s*(?:or\s+)?(?:something\s+else|other|another|unknown|unnamed)\b.*|"
    r",?\s*(?:the\s+)?(?:actual|specific)?\s*(?:cause|reason)\b.*",
    re.IGNORECASE,
)


def _explicit_list_size(
    fragment: str,
    *,
    separator: re.Pattern[str],
    unnamed_tail: re.Pattern[str],
    require_english_list_evidence: bool = False,
) -> int:
    """Return only a high-confidence three-or-more explicit list size."""

    bounded_fragment = unnamed_tail.sub("", fragment).strip(" ，,、;；:\t")
    if not bounded_fragment:
        return 0
    if require_english_list_evidence and re.match(
        r"^(?:neither\b|no\b|not\b(?!\s+only\b))",
        bounded_fragment,
        re.IGNORECASE,
    ):
        return 0
    if require_english_list_evidence and re.search(
        r"\b(?:and|or)\b",
        bounded_fragment,
        re.IGNORECASE,
    ) is None and bounded_fragment.count(",") < 2:
        return 0
    items = [
        item.strip(" ，,、;；:\t")
        for item in separator.split(bounded_fragment)
        if item.strip(" ，,、;；:\t")
    ]
    # This is a fail-closed lower bound, not a general semantic guess counter.
    # Restrict it to unmistakable enumerations so two-item prose and ordinary
    # conjunctions remain the responsibility of the two model gates.
    return len(items) if len(items) >= 3 else 0


def explicit_named_guess_lower_bound(candidate: str) -> int:
    """Find unmistakable three-plus causal lists the model gates undercounted.

    Review and Final Verifier remain the semantic counters. This deterministic
    lower bound covers only explicit coordinated lists under a causal or
    explanatory cue; it can increase their conservative count, never lower it.
    """

    lower_bound = 0
    for match in _ZH_NAMED_CAUSAL_LIST_PATTERN.finditer(candidate):
        fragment = next(value for value in match.groupdict().values() if value)
        lower_bound = max(
            lower_bound,
            _explicit_list_size(
                fragment,
                separator=_ZH_NAMED_LIST_SEPARATOR,
                unnamed_tail=_ZH_UNNAMED_LIST_TAIL,
            ),
        )
    for match in _EN_NAMED_CAUSAL_LIST_PATTERN.finditer(candidate):
        fragment = next(value for value in match.groupdict().values() if value)
        lower_bound = max(
            lower_bound,
            _explicit_list_size(
                fragment,
                separator=_EN_NAMED_LIST_SEPARATOR,
                unnamed_tail=_EN_UNNAMED_LIST_TAIL,
                require_english_list_evidence=True,
            ),
        )
    return lower_bound


def conservative_named_guess_count(
    review_count: int,
    verifier_count: int,
    candidate: str | None = None,
) -> int:
    """Never let either model gate erase another gate or server lower bound."""

    server_lower_bound = (
        explicit_named_guess_lower_bound(candidate) if candidate is not None else 0
    )
    return max(review_count, verifier_count, server_lower_bound)


def final_response_digest(candidate: str) -> str:
    """Return the audit identity of the exact UTF-8 candidate text."""

    return hashlib.sha256(candidate.encode("utf-8")).hexdigest()


def response_has_at_most_one_question(candidate: str) -> bool:
    """Enforce PAS-003's deterministic one-question surface boundary."""

    return candidate.count("?") + candidate.count("？") <= 1


def normalize_review_text(value: str) -> str:
    """Normalize only formatting differences when comparing draft disposition."""

    normalized = "".join(
        character
        for character in unicodedata.normalize("NFC", value)
        if unicodedata.category(character) != "Cf"
    )
    return re.sub(r"\s+", " ", normalized).strip()


def review_disposition_matches_draft(
    decision: ReviewDecision,
    reflection_draft: str,
) -> bool:
    unchanged = normalize_review_text(decision.final_response) == normalize_review_text(
        reflection_draft
    )
    if decision.draft_disposition == "accepted":
        return unchanged
    return not unchanged


class MemoryCandidate(BaseModel):
    kind: MemoryKind
    content: str = Field(min_length=1, max_length=1000)
    confidence: MemoryConfidence
    confirmation_prompt: str = Field(min_length=1, max_length=500)


class MemoryDecision(BaseModel):
    should_propose: bool
    kind: MemoryKind | None = None
    content: str | None = Field(default=None, max_length=1000)
    confidence: MemoryConfidence | None = None
    confirmation_prompt: str | None = Field(default=None, max_length=500)
    rationale: str = Field(
        max_length=1200,
        description="Short internal explanation. Never show this field to the user.",
    )

    @model_validator(mode="after")
    def validate_candidate_shape(self) -> "MemoryDecision":
        candidate_fields = (
            self.kind,
            self.content,
            self.confidence,
            self.confirmation_prompt,
        )
        if self.should_propose and any(value is None for value in candidate_fields):
            raise ValueError("A proposed memory requires every candidate field.")
        if not self.should_propose and any(value is not None for value in candidate_fields):
            raise ValueError("A declined memory must not contain candidate fields.")
        return self

    def public_candidate(self) -> MemoryCandidate | None:
        if not self.should_propose:
            return None
        return MemoryCandidate(
            kind=self.kind,
            content=self.content,
            confidence=self.confidence,
            confirmation_prompt=self.confirmation_prompt,
        )

    def sourced_public_candidate(self, user_message: str) -> MemoryCandidate | None:
        """Expose only verbatim user-authored content with fixed neutral framing."""

        if not self.should_propose or self.content is None:
            return None
        candidate_content = self.content.strip()
        if not candidate_content or candidate_content != user_message.strip():
            return None
        return MemoryCandidate(
            kind="reflection",
            content=candidate_content,
            confidence="low",
            confirmation_prompt=(
                "这段内容直接来自你刚才的原话。它准确吗，而且你希望 PAS 记住它吗？"
            ),
        )


class AgentResult(BaseModel):
    response: str = Field(min_length=1, max_length=12000)
    mode: AgentMode = "dual-agent"
    support_mode: SupportMode
    memory_candidate: MemoryCandidate | None = None
    response_source: ResponseSource = "review"
    risk_level: RiskLevel | None = None
    reflection_draft: str | None = Field(default=None, exclude=True)
    review: ReviewDecision | None = Field(default=None, exclude=True)
    verification: FinalVerificationDecision | None = Field(
        default=None,
        exclude=True,
    )
    bounded_response_kind: BoundedResponseKind | None = Field(
        default=None,
        exclude=True,
    )

    @model_validator(mode="after")
    def validate_response_provenance(self) -> "AgentResult":
        has_review_artifacts = self.reflection_draft is not None and self.review is not None
        has_partial_review_artifacts = (self.reflection_draft is None) != (self.review is None)
        if has_partial_review_artifacts:
            raise ValueError("Review provenance requires both draft and decision.")

        if self.response_source == "review":
            if not has_review_artifacts or self.review is None:
                raise ValueError("A reviewed response requires Review artifacts.")
            if self.review.risk_level != "none":
                raise ValueError("Risk responses must use the deterministic safety envelope.")
            if not review_disposition_matches_draft(
                self.review,
                self.reflection_draft,
            ):
                raise ValueError("Review draft disposition is inconsistent.")
            if not self.review.final_checks.release_ready:
                raise ValueError("A normal reviewed response must pass final checks.")
            if self.response != self.review.final_response:
                raise ValueError("A reviewed response must match Review final_response.")
            if not response_has_at_most_one_question(self.response):
                raise ValueError("A reviewed response cannot contain multiple questions.")
            if self.verification is None:
                raise ValueError("A normal reviewed response requires Final Verification.")
            if self.verification.gate_action != "release_candidate":
                raise ValueError("A normal response requires verifier release.")
            if self.verification.target_digest != final_response_digest(self.response):
                raise ValueError("Final Verification must target the exact response.")
            if (
                conservative_named_guess_count(
                    self.review.final_checks.named_guess_count,
                    self.verification.named_guess_count,
                    self.response,
                )
                > 2
            ):
                raise ValueError(
                    "A normal response cannot exceed the conservative guess limit."
                )
            if self.mode == "safety-guard":
                raise ValueError("A normal reviewed response cannot use safety-guard mode.")
            if self.risk_level is None:
                self.risk_level = self.review.risk_level
            elif self.risk_level != self.review.risk_level:
                raise ValueError("Agent and Review risk levels must match.")

            if self.bounded_response_kind is not None:
                if self.review.draft_disposition != "accepted":
                    raise ValueError(
                        "A bounded response requires exact primary Review acceptance."
                    )
                if self.reflection_draft != self.response:
                    raise ValueError(
                        "A bounded response must preserve the deterministic candidate."
                    )
                if self.memory_candidate is not None:
                    raise ValueError("A bounded response cannot propose memory.")
                if not bounded_response_health_boundary_is_satisfied(
                    self.bounded_response_kind,
                    self.review.final_checks.health_boundary,
                ):
                    raise ValueError(
                        "Health bounded candidates require a satisfied Review "
                        "health boundary."
                    )
                if self.bounded_response_kind == "unavailable_cross_chat_context":
                    if not unavailable_cross_chat_checks_are_exact(
                        source_bases=list(self.review.final_checks.source_bases),
                        named_guess_count=self.review.final_checks.named_guess_count,
                        diagnostic_self_screening_present=(
                            self.review.final_checks.diagnostic_self_screening_present
                        ),
                        health_boundary=self.review.final_checks.health_boundary,
                        cross_chat_boundary=(
                            self.review.final_checks.cross_chat_boundary
                        ),
                    ):
                        raise ValueError(
                            "The unavailable cross-chat candidate requires its exact "
                            "structured Review boundary."
                        )
                    if self.verification.named_guess_count != 0:
                        raise ValueError(
                            "The unavailable cross-chat candidate has zero guesses."
                        )
                if self.bounded_response_kind == "personal_lifespan_conversion":
                    if not personal_lifespan_checks_are_exact(
                        source_bases=list(self.review.final_checks.source_bases),
                        named_guess_count=self.review.final_checks.named_guess_count,
                        diagnostic_self_screening_present=(
                            self.review.final_checks.diagnostic_self_screening_present
                        ),
                        health_boundary=self.review.final_checks.health_boundary,
                        cross_chat_boundary=(
                            self.review.final_checks.cross_chat_boundary
                        ),
                    ):
                        raise ValueError(
                            "The lifespan candidate requires its exact structured "
                            "Review boundary."
                        )
                    if self.verification.named_guess_count != 0:
                        raise ValueError(
                            "The lifespan candidate has zero explanatory guesses."
                        )

        elif self.response_source == "review_safety_envelope":
            if self.bounded_response_kind is not None:
                raise ValueError("A bounded response cannot use a safety envelope.")
            if not has_review_artifacts or self.review is None:
                raise ValueError("A Review safety envelope requires Review artifacts.")
            if self.review.risk_level not in {"concerning", "urgent"}:
                raise ValueError("A Review safety envelope requires elevated risk.")
            if self.mode != "safety-guard":
                raise ValueError("A Review safety envelope requires safety-guard mode.")
            if self.verification is not None:
                raise ValueError("Elevated Review risk must skip Final Verification.")
            if self.risk_level is None:
                self.risk_level = self.review.risk_level
            elif self.risk_level != self.review.risk_level:
                raise ValueError("Agent and Review risk levels must match.")

        elif self.response_source == "safety_guard":
            if self.bounded_response_kind is not None:
                raise ValueError("A preflight safety response cannot be bounded.")
            if has_review_artifacts:
                raise ValueError("A preflight safety response cannot claim Review artifacts.")
            if self.risk_level not in {"concerning", "urgent"}:
                raise ValueError("A preflight safety response requires elevated risk.")
            if self.mode != "safety-guard":
                raise ValueError("A preflight safety response requires safety-guard mode.")
            if self.verification is not None:
                raise ValueError("A preflight safety response cannot claim verification.")

        else:
            if self.bounded_response_kind is not None:
                raise ValueError("A safe fallback cannot be bounded.")
            if has_review_artifacts:
                raise ValueError("A safe fallback cannot claim Review artifacts.")
            if self.risk_level is not None:
                raise ValueError("A safe fallback must not infer a user risk level.")
            if self.mode != "safety-guard":
                raise ValueError("A safe fallback requires safety-guard mode.")
            if self.verification is not None:
                raise ValueError("A safe fallback cannot claim verification.")

        expected_support_mode = (
            "reflection" if self.risk_level == "none" else "support"
        )
        if self.response_source == "safe_fallback":
            expected_support_mode = "support"
        if self.support_mode != expected_support_mode:
            raise ValueError("Risk and support mode must remain consistent.")
        if self.support_mode == "support" and self.memory_candidate is not None:
            raise ValueError("Support responses cannot include a memory candidate.")
        return self
