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
    response: str
    mode: Literal["dual-agent", "multi-agent"] = "dual-agent"
    memory_candidate: MemoryCandidate | None = None
