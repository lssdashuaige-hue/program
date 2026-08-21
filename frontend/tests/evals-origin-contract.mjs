import assert from "node:assert/strict";
import { createHash } from "node:crypto";

import {
  EvalClientError,
  normalizeEvalRunResponse,
  normalizeHistoricalEvalRunResponse,
} from "../src/lib/evals.ts";

const candidate = "候选回答。";
const digest = createHash("sha256").update(candidate, "utf8").digest("hex");

function reportWithVerification(verification) {
  return {
    run_scope: "explicit_cases",
    data_classification: "synthetic",
    case_count: 1,
    passed: true,
    pass_count: 1,
    fail_count: 0,
    duration_ms: 10,
    cases: [
      {
        case_id: "origin_contract",
        category: "pipeline",
        input: "合成测试",
        conversation_history: [],
        reflection_draft: candidate,
        final_response: candidate,
        mode: "multi-agent",
        support_mode: "reflection",
        response_source: "review",
        risk_level: "none",
        safety_guard_applied: false,
        memory_candidate_present: false,
        review_completed: true,
        review: {
          contract_version: "2",
          draft_disposition: "accepted",
          draft_findings: [],
          final_checks: {
            source_bases: ["current_user_message"],
            source_attribution_ok: true,
            adds_unreported_user_fact: false,
            adds_unreported_third_party_fact: false,
            promotes_prior_ai_hypothesis: false,
            named_guess_count: 0,
            diagnostic_self_screening_present: false,
            health_boundary: "not_applicable",
            cross_chat_boundary: "not_applicable",
            other_pas_requirements_ok: true,
            release_ready: true,
          },
          risk_level: "none",
          rationale: "Synthetic origin-contract probe.",
        },
        review_verification: verification,
        hard_assertions: [
          {
            rule: "synthetic_contract_probe",
            applicable: true,
            passed: true,
            detail: "Synthetic assertion.",
          },
        ],
        passed: true,
        latency_ms: 10,
      },
    ],
  };
}

const dialogueCaseIds = [
  "short_followup_uses_history",
  "colloquial_typo_grounding",
  "generic_assent_does_not_confirm_hypothesis",
  "ambiguous_codes_need_context",
  "explicit_guess_is_transparent",
  "diagnosis_guess_keeps_boundary",
  "observer_keeps_imported_provenance",
  "unavailable_other_chat_is_not_claimed",
  "family_cause_stays_hypothetical",
  "neuro_metaphor_is_not_literalized",
  "persistent_change_names_real_world_evaluation",
  "lifespan_request_keeps_evidence_boundary",
];

function fullDialogueReportWithVerification(
  verification,
  { currentCrossRoute = false } = {},
) {
  const template = reportWithVerification(verification).cases[0];
  const existingKinds = {
    diagnosis_guess_keeps_boundary: "single_chat_diagnostic_request",
    family_cause_stays_hypothetical: "third_party_private_state",
    lifespan_request_keeps_evidence_boundary: "personal_lifespan_conversion",
  };
  const cases = dialogueCaseIds.map((caseId, index) => {
    const item = structuredClone(template);
    item.case_id = caseId;
    item.category = "dialogue_contract";
    item.input = `synthetic dialogue case ${index + 1}`;
    const existingKind = existingKinds[caseId];
    if (existingKind) item.bounded_response_kind = existingKind;
    if (
      caseId === "unavailable_other_chat_is_not_claimed" &&
      currentCrossRoute
    ) {
      item.bounded_response_kind = "unavailable_cross_chat_context";
      item.review.final_checks.source_bases = [
        "current_user_message",
        "general_knowledge",
      ];
      item.review.final_checks.cross_chat_boundary = "satisfied";
    }
    return item;
  });
  return {
    suite: "pas-dialogue-v0.1",
    run_scope: "full_suite",
    total_suite_case_count: dialogueCaseIds.length,
    data_classification: "synthetic",
    case_count: cases.length,
    passed: true,
    pass_count: cases.length,
    fail_count: 0,
    duration_ms: 120,
    cases,
  };
}

function reportWithPipelineFailure(pipelineFailure) {
  return {
    run_scope: "explicit_cases",
    data_classification: "synthetic",
    case_count: 1,
    passed: false,
    pass_count: 0,
    fail_count: 1,
    duration_ms: 10,
    cases: [
      {
        case_id: "failure_origin_contract",
        category: "pipeline",
        input: "合成测试",
        conversation_history: [],
        safety_guard_applied: false,
        memory_candidate_present: false,
        review_completed: false,
        hard_assertions: [
          {
            rule: "synthetic_contract_probe",
            applicable: true,
            passed: false,
            detail: "Synthetic assertion.",
          },
        ],
        passed: false,
        latency_ms: 10,
        error: "pipeline_failed_closed",
        pipeline_failure: pipelineFailure,
      },
    ],
  };
}

const reviewFailure = {
  stage: "review",
  reason: "review_contract_violation",
  contract_failure_code: "final_checks_not_release_ready",
  review_final_finding: "health_boundary",
  code: "invalid_schema",
  retryable: false,
  content_present: true,
  request_id_present: false,
};
const verifierFailure = {
  stage: "review_verifier",
  reason: "review_contract_violation",
  contract_failure_code: "verifier_rejected",
  verifier_finding: "health_boundary",
  code: "invalid_schema",
  retryable: false,
  content_present: true,
  request_id_present: false,
};

for (const currentFailure of [reviewFailure, verifierFailure]) {
  const normalized = normalizeEvalRunResponse(
    reportWithPipelineFailure(currentFailure),
  );
  assert.equal(
    normalized.cases[0].pipeline_failure?.legacy_missing_finding,
    undefined,
  );

  const missingFinding = { ...currentFailure };
  delete missingFinding.review_final_finding;
  delete missingFinding.verifier_finding;
  assert.throws(
    () => normalizeEvalRunResponse(reportWithPipelineFailure(missingFinding)),
    EvalClientError,
  );

  const historical = normalizeHistoricalEvalRunResponse(
    reportWithPipelineFailure(missingFinding),
  );
  assert.equal(
    historical.cases[0].pipeline_failure?.legacy_missing_finding,
    true,
  );
  assert.equal(
    normalizeHistoricalEvalRunResponse(historical).cases[0].pipeline_failure
      ?.legacy_missing_finding,
    true,
    "normalized legacy markers remain importable",
  );
}

const forgedFailures = [
  { ...reviewFailure, verifier_finding: "health_boundary" },
  { ...verifierFailure, review_final_finding: "health_boundary" },
  { ...reviewFailure, stage: "review_verifier" },
  { ...verifierFailure, code: "provider_timeout" },
  { ...reviewFailure, candidate: "private candidate" },
  { ...reviewFailure, legacy_missing_finding: true },
];
for (const forgedFailure of forgedFailures) {
  assert.throws(
    () => normalizeEvalRunResponse(reportWithPipelineFailure(forgedFailure)),
    EvalClientError,
  );
  assert.throws(
    () =>
      normalizeHistoricalEvalRunResponse(
        reportWithPipelineFailure(forgedFailure),
      ),
    EvalClientError,
  );
}

const legacyReport = reportWithVerification({
  contract_version: "1",
  target_digest: digest,
  gate_action: "release_candidate",
  primary_finding: "none",
});

assert.throws(
  () => normalizeEvalRunResponse(legacyReport),
  (error) =>
    error instanceof EvalClientError &&
    error.message.includes("实时验收只接受 v2"),
);

const historical = normalizeHistoricalEvalRunResponse(legacyReport);
assert.equal(historical.passed, true, "historical result remains auditable");
assert.equal(historical.contains_legacy_verifier_v1, true);
assert.equal(historical.contains_legacy_route, false);
assert.equal(historical.current_contract_passed, false);
assert.equal(historical.cases[0].passed, true);
assert.equal(historical.cases[0].legacy_verifier_v1, true);
assert.equal(historical.cases[0].current_contract_passed, false);

const currentReport = reportWithVerification({
  contract_version: "2",
  target_digest: digest,
  gate_action: "release_candidate",
  primary_finding: "none",
  named_guess_count: 0,
});
const current = normalizeEvalRunResponse(currentReport);
assert.equal(current.contains_legacy_verifier_v1, false);
assert.equal(current.contains_legacy_route, false);
assert.equal(current.current_contract_passed, true);
assert.equal(current.cases[0].current_contract_passed, true);

const legacyFullDialogueReport = fullDialogueReportWithVerification({
  contract_version: "1",
  target_digest: digest,
  gate_action: "release_candidate",
  primary_finding: "none",
});
assert.throws(
  () => normalizeEvalRunResponse(legacyFullDialogueReport),
  EvalClientError,
  "live reports never accept verifier v1 or a pre-route cross-chat case",
);
const historicalFullDialogue = normalizeHistoricalEvalRunResponse(
  legacyFullDialogueReport,
);
const historicalCrossCase = historicalFullDialogue.cases.find(
  (item) => item.case_id === "unavailable_other_chat_is_not_claimed",
);
assert.equal(historicalCrossCase?.bounded_response_kind, undefined);
assert.equal(historicalCrossCase?.legacy_route, true);
assert.equal(historicalCrossCase?.current_contract_passed, false);
assert.equal(historicalFullDialogue.contains_legacy_route, true);
assert.equal(historicalFullDialogue.current_contract_passed, false);

const impossibleLegacyNewRoute = fullDialogueReportWithVerification(
  {
    contract_version: "1",
    target_digest: digest,
    gate_action: "release_candidate",
    primary_finding: "none",
  },
  { currentCrossRoute: true },
);
assert.throws(
  () => normalizeHistoricalEvalRunResponse(impossibleLegacyNewRoute),
  EvalClientError,
  "historical v1 cannot claim a cross-chat route introduced with v2",
);

const forgedLegacyKind = structuredClone(legacyFullDialogueReport);
forgedLegacyKind.cases.find(
  (item) => item.case_id === "unavailable_other_chat_is_not_claimed",
).bounded_response_kind = "third_party_private_state";
assert.throws(
  () => normalizeHistoricalEvalRunResponse(forgedLegacyKind),
  EvalClientError,
  "historical compatibility does not allow a forged wrong kind",
);

const currentFullWithoutCrossKind = fullDialogueReportWithVerification({
  contract_version: "2",
  target_digest: digest,
  gate_action: "release_candidate",
  primary_finding: "none",
  named_guess_count: 0,
});
assert.throws(
  () => normalizeEvalRunResponse(currentFullWithoutCrossKind),
  EvalClientError,
  "current full reports require the new cross-chat route",
);
assert.throws(
  () => normalizeHistoricalEvalRunResponse(currentFullWithoutCrossKind),
  EvalClientError,
  "historical import only relaxes the pre-route verifier-v1 shape",
);

const currentFullDialogue = normalizeEvalRunResponse(
  fullDialogueReportWithVerification(
    {
      contract_version: "2",
      target_digest: digest,
      gate_action: "release_candidate",
      primary_finding: "none",
      named_guess_count: 0,
    },
    { currentCrossRoute: true },
  ),
);
const currentCrossCase = currentFullDialogue.cases.find(
  (item) => item.case_id === "unavailable_other_chat_is_not_claimed",
);
assert.equal(
  currentCrossCase?.bounded_response_kind,
  "unavailable_cross_chat_context",
);
assert.equal(currentCrossCase?.legacy_route, false);
assert.equal(currentCrossCase?.current_contract_passed, true);
assert.equal(currentFullDialogue.contains_legacy_route, false);

process.stdout.write("eval live/import origin contract: ok\n");
