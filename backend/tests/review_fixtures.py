from collections.abc import Sequence

from app.ai.models import (
    BoundaryStatus,
    DraftDisposition,
    FinalResponseChecks,
    FinalVerificationDecision,
    FinalVerificationFinding,
    ReviewDecision,
    ReviewIssue,
    RiskLevel,
    SourceBasis,
    final_response_digest,
)


def safe_final_checks(
    *,
    source_bases: Sequence[SourceBasis] = ("current_user_message",),
    named_guess_count: int = 0,
    health_boundary: BoundaryStatus = "not_applicable",
    cross_chat_boundary: BoundaryStatus = "not_applicable",
) -> FinalResponseChecks:
    return FinalResponseChecks(
        source_bases=list(source_bases),
        source_attribution_ok=True,
        adds_unreported_user_fact=False,
        adds_unreported_third_party_fact=False,
        promotes_prior_ai_hypothesis=False,
        named_guess_count=named_guess_count,
        diagnostic_self_screening_present=False,
        health_boundary=health_boundary,
        cross_chat_boundary=cross_chat_boundary,
        other_pas_requirements_ok=True,
    )


def review_decision(
    *,
    final_response: str,
    draft_disposition: DraftDisposition = "accepted",
    draft_findings: Sequence[ReviewIssue] = (),
    final_checks: FinalResponseChecks | None = None,
    risk_level: RiskLevel = "none",
    rationale: str = "Synthetic structured Review fixture.",
) -> ReviewDecision:
    return ReviewDecision(
        contract_version="2",
        draft_disposition=draft_disposition,
        draft_findings=list(draft_findings),
        final_response=final_response,
        final_checks=final_checks or safe_final_checks(),
        risk_level=risk_level,
        rationale=rationale,
    )


def verification_decision(
    candidate: str,
    *,
    release: bool = True,
    primary_finding: FinalVerificationFinding | None = None,
    named_guess_count: int = 0,
    target_digest: str | None = None,
    rationale: str = "Synthetic Final Verification fixture.",
) -> FinalVerificationDecision:
    if primary_finding is None:
        primary_finding = "none" if release else "pas_principle_violation"
    return FinalVerificationDecision(
        contract_version="2",
        target_digest=target_digest or final_response_digest(candidate),
        gate_action="release_candidate" if release else "reject_candidate",
        primary_finding=primary_finding,
        named_guess_count=named_guess_count,
        rationale=rationale,
    )
