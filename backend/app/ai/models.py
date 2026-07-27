from typing import Literal

from pydantic import BaseModel, Field


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


class ReviewDecision(BaseModel):
    approved: bool
    final_response: str = Field(min_length=1, max_length=12000)
    issues: list[ReviewIssue] = Field(default_factory=list)
    risk_level: RiskLevel = "none"
    rationale: str = Field(
        max_length=1200,
        description="Short internal explanation. Never show this field to the user.",
    )


class AgentResult(BaseModel):
    response: str
    mode: Literal["dual-agent"] = "dual-agent"
