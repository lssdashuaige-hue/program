from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
]

RiskLevel = Literal["none", "concerning", "urgent"]
AgentMode = Literal["dual-agent", "multi-agent", "safety-guard"]
ResponseSource = Literal[
    "review",
    "safety_guard",
    "review_safety_envelope",
    "safe_fallback",
]
SupportMode = Literal["reflection", "support"]
MemoryKind = Literal["experience", "reflection", "pattern", "need"]
MemoryConfidence = Literal["low", "medium"]


class ReviewDecision(BaseModel):
    approved: bool
    final_response: str = Field(min_length=1, max_length=12000)
    issues: list[ReviewIssue] = Field(default_factory=list)
    risk_level: RiskLevel = "none"
    rationale: str = Field(
        max_length=1200,
        description="Short internal explanation. Never show this field to the user.",
    )


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


class AgentResult(BaseModel):
    response: str = Field(min_length=1, max_length=12000)
    mode: AgentMode = "dual-agent"
    support_mode: SupportMode
    memory_candidate: MemoryCandidate | None = None
    response_source: ResponseSource = "review"
    risk_level: RiskLevel | None = None
    reflection_draft: str | None = Field(default=None, exclude=True)
    review: ReviewDecision | None = Field(default=None, exclude=True)

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
            if self.response.strip() != self.review.final_response.strip():
                raise ValueError("A reviewed response must match Review final_response.")
            if self.mode == "safety-guard":
                raise ValueError("A normal reviewed response cannot use safety-guard mode.")
            if self.risk_level is None:
                self.risk_level = self.review.risk_level
            elif self.risk_level != self.review.risk_level:
                raise ValueError("Agent and Review risk levels must match.")

        elif self.response_source == "review_safety_envelope":
            if not has_review_artifacts or self.review is None:
                raise ValueError("A Review safety envelope requires Review artifacts.")
            if self.review.risk_level not in {"concerning", "urgent"}:
                raise ValueError("A Review safety envelope requires elevated risk.")
            if self.mode != "safety-guard":
                raise ValueError("A Review safety envelope requires safety-guard mode.")
            if self.risk_level is None:
                self.risk_level = self.review.risk_level
            elif self.risk_level != self.review.risk_level:
                raise ValueError("Agent and Review risk levels must match.")

        elif self.response_source == "safety_guard":
            if has_review_artifacts:
                raise ValueError("A preflight safety response cannot claim Review artifacts.")
            if self.risk_level not in {"concerning", "urgent"}:
                raise ValueError("A preflight safety response requires elevated risk.")
            if self.mode != "safety-guard":
                raise ValueError("A preflight safety response requires safety-guard mode.")

        else:
            if has_review_artifacts:
                raise ValueError("A safe fallback cannot claim Review artifacts.")
            if self.risk_level is not None:
                raise ValueError("A safe fallback must not infer a user risk level.")
            if self.mode != "safety-guard":
                raise ValueError("A safe fallback requires safety-guard mode.")

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
