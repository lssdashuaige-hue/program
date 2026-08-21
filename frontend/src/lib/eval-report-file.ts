import "client-only";

import {
  EvalClientError,
  type EvalCaseResult,
  type EvalRunResponse,
  isRetryableEvalFailure,
  normalizeHistoricalEvalRunResponse,
} from "@/lib/evals";

const REPORT_SCHEMA_VERSION = 2;
const reportKeys = new Set([
  "schema_version",
  "saved_at",
  "full_attempt",
  "retry_attempts",
]);
export const MAX_EVAL_RETRY_ATTEMPTS = 12;

export type SavedEvalReport = {
  schema_version: typeof REPORT_SCHEMA_VERSION;
  saved_at: string;
  full_attempt: EvalRunResponse;
  retry_attempts: EvalRunResponse[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function validateReportRelationship(
  fullAttempt: EvalRunResponse,
  retryAttempts: EvalRunResponse[],
): void {
  if (fullAttempt.run_scope !== "full_suite" || !fullAttempt.suite) {
    throw new EvalClientError("保存的报告缺少一次可验证的完整套件运行。");
  }

  const fullCaseIds = new Set(fullAttempt.cases.map((item) => item.case_id));
  if (fullCaseIds.size !== fullAttempt.cases.length) {
    throw new EvalClientError("保存的完整运行包含重复案例 ID。");
  }

  const latestById = new Map<string, EvalCaseResult>(
    fullAttempt.cases.map((item) => [item.case_id, item]),
  );
  for (const attempt of retryAttempts) {
    const attemptCaseIds = new Set(
      attempt.cases.map((item) => item.case_id),
    );
    const expectedCaseIds = fullAttempt.cases.flatMap((item) => {
      const latest = latestById.get(item.case_id) ?? item;
      return isRetryableEvalFailure(latest) ? [item.case_id] : [];
    });
    const actualCaseIds = attempt.cases.map((item) => item.case_id);
    if (
      attempt.run_scope !== "suite_subset" ||
      attempt.suite !== fullAttempt.suite ||
      attempt.total_suite_case_count !== fullAttempt.total_suite_case_count ||
      attemptCaseIds.size !== attempt.cases.length ||
      attempt.cases.some((item) => !fullCaseIds.has(item.case_id)) ||
      actualCaseIds.length !== expectedCaseIds.length ||
      actualCaseIds.some((caseId, index) => caseId !== expectedCaseIds[index])
    ) {
      throw new EvalClientError("保存的失败项重跑与完整套件不匹配。");
    }
    for (const item of attempt.cases) {
      latestById.set(item.case_id, item);
    }
  }
}

export function createSavedEvalReport(
  fullAttempt: EvalRunResponse,
  retryAttempts: EvalRunResponse[],
): SavedEvalReport {
  if (retryAttempts.length > MAX_EVAL_RETRY_ATTEMPTS) {
    throw new EvalClientError("失败项重跑记录超过当前报告版本的安全上限。");
  }
  validateReportRelationship(fullAttempt, retryAttempts);
  return {
    schema_version: REPORT_SCHEMA_VERSION,
    saved_at: new Date().toISOString(),
    full_attempt: fullAttempt,
    retry_attempts: retryAttempts,
  };
}

export function parseSavedEvalReport(value: unknown): SavedEvalReport {
  if (
    !isRecord(value) ||
    Object.keys(value).length !== reportKeys.size ||
    !Object.keys(value).every((key) => reportKeys.has(key)) ||
    value.schema_version !== REPORT_SCHEMA_VERSION ||
    typeof value.saved_at !== "string" ||
    !Number.isFinite(Date.parse(value.saved_at)) ||
    !Array.isArray(value.retry_attempts) ||
    value.retry_attempts.length > MAX_EVAL_RETRY_ATTEMPTS
  ) {
    throw new EvalClientError(
      "保存的评测报告版本或结构无法识别；旧单遍 Review 报告不能作为当前双门验收。",
    );
  }

  const fullAttempt = normalizeHistoricalEvalRunResponse(value.full_attempt);
  const retryAttempts = value.retry_attempts.map(
    normalizeHistoricalEvalRunResponse,
  );
  validateReportRelationship(fullAttempt, retryAttempts);

  return {
    schema_version: REPORT_SCHEMA_VERSION,
    saved_at: value.saved_at,
    full_attempt: fullAttempt,
    retry_attempts: retryAttempts,
  };
}
