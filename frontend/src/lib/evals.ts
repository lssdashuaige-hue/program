import "client-only";

const evalErrorCodes = [
  "pipeline_failed_closed",
  "timeout",
  "internal_error",
] as const;

const pipelineStages = ["reflection", "review"] as const;

const gatewayErrorCodes = [
  "provider_authentication",
  "provider_permission",
  "provider_rate_limited",
  "provider_timeout",
  "provider_connection",
  "provider_unavailable",
  "provider_http_error",
  "empty_content",
  "invalid_schema",
  "unexpected_error",
] as const;

const safeFinishReasons = [
  "stop",
  "length",
  "content_filter",
  "tool_calls",
  "insufficient_system_resource",
  "other",
] as const;

const responseSources = [
  "review",
  "safety_guard",
  "review_safety_envelope",
  "safe_fallback",
] as const;

const riskLevels = ["none", "concerning", "urgent"] as const;

const runScopes = ["full_suite", "suite_subset", "explicit_cases"] as const;

const contextRoles = ["user", "assistant"] as const;

export const evalSuiteCatalog = {
  "pas-core-v0.1": [
    "normal_reflection",
    "diagnosis_temptation",
    "overcertainty_temptation",
    "autonomy_temptation",
    "dependency_temptation",
    "reality_detachment_temptation",
    "passive_self_harm",
    "urgent_self_harm",
    "fiction_quote_negative",
    "privacy_memory_boundary",
    "cross_context_pattern",
    "one_time_emotion",
  ],
  "pas-dialogue-v0.1": [
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
  ],
} as const;

export type EvalSuiteName = keyof typeof evalSuiteCatalog;
export const evalSuiteNames = Object.keys(evalSuiteCatalog) as EvalSuiteName[];

const pipelineFailureKeys = new Set([
  "stage",
  "code",
  "retryable",
  "content_present",
  "request_id_present",
  "http_status",
  "finish_reason",
]);

export type EvalErrorCode = (typeof evalErrorCodes)[number];
export type EvalPipelineStage = (typeof pipelineStages)[number];
export type EvalGatewayErrorCode = (typeof gatewayErrorCodes)[number];
export type EvalFinishReason = (typeof safeFinishReasons)[number];
export type EvalResponseSource = (typeof responseSources)[number];
export type EvalRiskLevel = (typeof riskLevels)[number];
export type EvalRunScope = (typeof runScopes)[number];
export type EvalContextRole = (typeof contextRoles)[number];

export class EvalClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EvalClientError";
  }
}

export type EvalSuite = {
  name: EvalSuiteName;
  description: string;
  case_count: number;
  case_ids: string[];
  categories: string[];
};

export type EvalAssertion = {
  rule: string;
  applicable: boolean;
  passed: boolean;
  detail: string;
};

export type EvalReview = {
  approved: boolean;
  issues: string[];
  risk_level: EvalRiskLevel;
  rationale: string;
};

export type EvalPipelineFailure = {
  stage: EvalPipelineStage;
  code: EvalGatewayErrorCode;
  retryable: boolean;
  content_present: boolean;
  request_id_present: boolean;
  http_status?: number;
  finish_reason?: EvalFinishReason;
};

export type EvalContextMessage = {
  role: EvalContextRole;
  content: string;
};

export type EvalCaseResult = {
  case_id: string;
  category: string;
  input: string;
  conversation_history: EvalContextMessage[];
  reflection_draft?: string;
  final_response?: string;
  mode?: string;
  support_mode?: "reflection" | "support";
  response_source?: EvalResponseSource;
  risk_level?: EvalRiskLevel;
  safety_guard_applied: boolean;
  memory_candidate_present: boolean;
  memory_candidate_confidence?: "low" | "medium";
  review_completed: boolean;
  review?: EvalReview;
  hard_assertions: EvalAssertion[];
  passed: boolean;
  latency_ms: number;
  error?: EvalErrorCode;
  pipeline_failure?: EvalPipelineFailure;
};

export type EvalRunResponse = {
  suite?: EvalSuiteName;
  run_scope: EvalRunScope;
  total_suite_case_count?: number;
  data_classification: "synthetic";
  case_count: number;
  passed: boolean;
  pass_count: number;
  fail_count: number;
  duration_ms: number;
  cases: EvalCaseResult[];
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const normalized = asString(item);
        return normalized ? [normalized] : [];
      })
    : [];
}

function isAllowedValue<const Values extends readonly string[]>(
  value: unknown,
  allowed: Values,
): value is Values[number] {
  return (
    typeof value === "string" &&
    (allowed as readonly string[]).includes(value)
  );
}

export function isEvalSuiteName(value: unknown): value is EvalSuiteName {
  return (
    typeof value === "string" &&
    Object.prototype.hasOwnProperty.call(evalSuiteCatalog, value)
  );
}

function arraysEqual(left: readonly string[], right: readonly string[]): boolean {
  return (
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  );
}

function normalizePipelineFailure(
  value: unknown,
  caseIndex: number,
): EvalPipelineFailure | undefined {
  if (value === null || value === undefined) return undefined;

  const invalidMessage = `评测服务返回的第 ${caseIndex + 1} 条案例包含无法识别的安全诊断数据。`;
  if (!isRecord(value)) throw new EvalClientError(invalidMessage);

  if (Object.keys(value).some((key) => !pipelineFailureKeys.has(key))) {
    throw new EvalClientError(invalidMessage);
  }

  if (
    !isAllowedValue(value.stage, pipelineStages) ||
    !isAllowedValue(value.code, gatewayErrorCodes) ||
    typeof value.retryable !== "boolean" ||
    typeof value.content_present !== "boolean" ||
    typeof value.request_id_present !== "boolean"
  ) {
    throw new EvalClientError(invalidMessage);
  }

  let httpStatus: number | undefined;
  if (value.http_status !== null && value.http_status !== undefined) {
    if (
      typeof value.http_status !== "number" ||
      !Number.isInteger(value.http_status) ||
      value.http_status < 400 ||
      value.http_status > 599
    ) {
      throw new EvalClientError(invalidMessage);
    }
    httpStatus = value.http_status;
  }

  let finishReason: EvalFinishReason | undefined;
  if (value.finish_reason !== null && value.finish_reason !== undefined) {
    if (!isAllowedValue(value.finish_reason, safeFinishReasons)) {
      throw new EvalClientError(invalidMessage);
    }
    finishReason = value.finish_reason;
  }

  return {
    stage: value.stage,
    code: value.code,
    retryable: value.retryable,
    content_present: value.content_present,
    request_id_present: value.request_id_present,
    http_status: httpStatus,
    finish_reason: finishReason,
  };
}

function normalizeSuite(value: unknown): EvalSuite | null {
  if (!isRecord(value)) return null;

  const name = value.name;
  const description = asString(value.description);
  const caseCount = asNumber(value.case_count);
  const caseIds = asStringArray(value.case_ids);
  if (
    !isEvalSuiteName(name) ||
    !description ||
    caseCount === undefined ||
    !Number.isInteger(caseCount) ||
    caseCount !== evalSuiteCatalog[name].length ||
    !arraysEqual(caseIds, evalSuiteCatalog[name])
  ) {
    return null;
  }

  return {
    name,
    description,
    case_count: caseCount,
    case_ids: caseIds,
    categories: asStringArray(value.categories),
  };
}

function normalizeAssertion(value: unknown, index: number): EvalAssertion {
  if (
    !isRecord(value) ||
    !asString(value.rule) ||
    typeof value.applicable !== "boolean" ||
    typeof value.passed !== "boolean" ||
    !asString(value.detail)
  ) {
    throw new EvalClientError(
      `评测运行报告包含无法识别的第 ${index + 1} 条断言。`,
    );
  }

  return {
    rule: value.rule as string,
    applicable: value.applicable,
    passed: value.passed,
    detail: value.detail as string,
  };
}

function normalizeReview(
  value: unknown,
  caseIndex: number,
): EvalReview | undefined {
  if (value === null || value === undefined) return undefined;
  if (
    !isRecord(value) ||
    typeof value.approved !== "boolean" ||
    !Array.isArray(value.issues) ||
    value.issues.some((item) => !asString(item)) ||
    !asString(value.rationale)
  ) {
    throw new EvalClientError(
      `评测服务返回的第 ${caseIndex + 1} 条案例包含无法识别的 Review 数据。`,
    );
  }

  if (!isAllowedValue(value.risk_level, riskLevels)) {
    throw new EvalClientError(
      `评测服务返回的第 ${caseIndex + 1} 条案例包含无法识别的 Review 风险等级。`,
    );
  }

  return {
    approved: value.approved,
    issues: value.issues as string[],
    risk_level: value.risk_level,
    rationale: value.rationale as string,
  };
}

function normalizeConversationHistory(
  value: unknown,
  caseIndex: number,
): EvalContextMessage[] {
  if (value === null || value === undefined) return [];
  if (!Array.isArray(value)) {
    throw new EvalClientError(
      `评测服务返回的第 ${caseIndex + 1} 条案例包含无法识别的合成会话历史。`,
    );
  }

  return value.map((item) => {
    if (
      !isRecord(item) ||
      !isAllowedValue(item.role, contextRoles) ||
      typeof item.content !== "string"
    ) {
      throw new EvalClientError(
        `评测服务返回的第 ${caseIndex + 1} 条案例包含无法识别的合成会话历史。`,
      );
    }
    return { role: item.role, content: item.content };
  });
}

function normalizeCaseResult(value: unknown, index: number): EvalCaseResult {
  if (!isRecord(value)) {
    throw new EvalClientError(
      `评测服务返回的第 ${index + 1} 条案例结果无法识别。`,
    );
  }

  const caseId = asString(value.case_id);
  const category = asString(value.category);
  const input = asString(value.input);
  const latencyMs = asNumber(value.latency_ms);
  if (
    !caseId ||
    !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(caseId) ||
    !category ||
    !input ||
    typeof value.memory_candidate_present !== "boolean" ||
    typeof value.review_completed !== "boolean" ||
    typeof value.passed !== "boolean" ||
    latencyMs === undefined ||
    !Number.isInteger(latencyMs) ||
    latencyMs < 0 ||
    !Array.isArray(value.hard_assertions) ||
    value.hard_assertions.length === 0
  ) {
    throw new EvalClientError(
      `评测服务返回的第 ${index + 1} 条案例结果字段不完整。`,
    );
  }

  const supportMode = asString(value.support_mode);
  const memoryConfidence = asString(value.memory_candidate_confidence);
  if (typeof value.safety_guard_applied !== "boolean") {
    throw new EvalClientError(
      `评测服务返回的第 ${index + 1} 条案例包含无法识别的安全闸门状态。`,
    );
  }

  let riskLevel: EvalRiskLevel | undefined;
  if (value.risk_level !== null && value.risk_level !== undefined) {
    if (!isAllowedValue(value.risk_level, riskLevels)) {
      throw new EvalClientError(
        `评测服务返回的第 ${index + 1} 条案例包含无法识别的规范风险等级。`,
      );
    }
    riskLevel = value.risk_level;
  }

  let error: EvalErrorCode | undefined;
  if (value.error !== null && value.error !== undefined) {
    if (!isAllowedValue(value.error, evalErrorCodes)) {
      throw new EvalClientError(
        `评测服务返回的第 ${index + 1} 条案例包含无法识别的错误类别。`,
      );
    }
    error = value.error;
  }

  let responseSource: EvalResponseSource | undefined;
  if (value.response_source !== null && value.response_source !== undefined) {
    if (!isAllowedValue(value.response_source, responseSources)) {
      throw new EvalClientError(
        `评测服务返回的第 ${index + 1} 条案例包含无法识别的回答路径。`,
      );
    }
    responseSource = value.response_source;
  } else if (error === undefined) {
    throw new EvalClientError(
      `评测服务返回的第 ${index + 1} 条成功案例缺少回答路径。`,
    );
  }

  const review = normalizeReview(value.review, index);
  const hardAssertions = value.hard_assertions.map(normalizeAssertion);
  const applicableAssertions = hardAssertions.filter(
    (assertion) => assertion.applicable,
  );
  const computedPassed =
    error === undefined &&
    applicableAssertions.length > 0 &&
    applicableAssertions.every((assertion) => assertion.passed);

  if (value.passed !== computedPassed || (error !== undefined && value.passed)) {
    throw new EvalClientError(
      `评测服务返回的第 ${index + 1} 条案例通过状态与断言不一致。`,
    );
  }

  if (error === undefined) {
    if (
      !responseSource ||
      !asString(value.final_response) ||
      !asString(value.mode) ||
      (supportMode !== "reflection" && supportMode !== "support") ||
      (responseSource !== "safe_fallback" && !riskLevel)
    ) {
      throw new EvalClientError(
        `评测服务返回的第 ${index + 1} 条已完成案例缺少回答来源。`,
      );
    }
    if (responseSource === "review" && (
      !value.review_completed ||
      !review ||
      value.safety_guard_applied
    )) {
      throw new EvalClientError(
        `评测服务返回的第 ${index + 1} 条案例缺少已声明的 Review。`,
      );
    }
    if (
      responseSource === "review_safety_envelope" &&
      (!value.review_completed || !review || !value.safety_guard_applied)
    ) {
      throw new EvalClientError(
        `评测服务返回的第 ${index + 1} 条 Review 安全包络来源不一致。`,
      );
    }
    if (
      responseSource === "safety_guard" &&
      (!value.safety_guard_applied || value.review_completed || review)
    ) {
      throw new EvalClientError(
        `评测服务返回的第 ${index + 1} 条安全闸门来源不一致。`,
      );
    }
    if (
      responseSource === "safe_fallback" &&
      (value.review_completed || review || !value.safety_guard_applied || value.passed)
    ) {
      throw new EvalClientError(
        `评测服务返回的第 ${index + 1} 条安全降级来源不一致。`,
      );
    }
  } else if (value.review_completed || review || responseSource) {
    throw new EvalClientError(
      `评测服务返回的第 ${index + 1} 条失败案例包含不一致的回答来源。`,
    );
  }

  return {
    case_id: caseId,
    category,
    input,
    conversation_history: normalizeConversationHistory(
      value.conversation_history,
      index,
    ),
    reflection_draft: asString(value.reflection_draft),
    final_response: asString(value.final_response),
    mode: asString(value.mode),
    support_mode:
      supportMode === "reflection" || supportMode === "support"
        ? supportMode
        : undefined,
    response_source: responseSource,
    risk_level: riskLevel,
    safety_guard_applied: value.safety_guard_applied,
    memory_candidate_present: value.memory_candidate_present === true,
    memory_candidate_confidence:
      memoryConfidence === "low" || memoryConfidence === "medium"
        ? memoryConfidence
        : undefined,
    review_completed: value.review_completed,
    review,
    hard_assertions: hardAssertions,
    passed: value.passed,
    latency_ms: latencyMs,
    error,
    pipeline_failure: normalizePipelineFailure(value.pipeline_failure, index),
  };
}

async function errorForResponse(response: Response): Promise<EvalClientError> {
  if (response.status === 401 || response.status === 403) {
    return new EvalClientError(
      "评测令牌无效，或当前环境不允许访问内部评测。",
    );
  }

  if (response.status === 404) {
    return new EvalClientError("当前后端尚未启用内部评测接口。");
  }

  if (response.status === 409) {
    return new EvalClientError(
      "已有一轮评测正在运行。为避免叠加模型调用，请等待它结束后再试。",
    );
  }

  return new EvalClientError(`评测请求失败（HTTP ${response.status}）。`);
}

export async function fetchEvalSuites(
  token: string,
  signal?: AbortSignal,
): Promise<EvalSuite[]> {
  const response = await fetch(`${apiUrl}/internal/evals/suites`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
    signal,
  });

  if (!response.ok) throw await errorForResponse(response);

  const payload = (await response.json()) as unknown;
  if (!Array.isArray(payload)) {
    throw new EvalClientError("评测服务返回了无法识别的套件列表。");
  }

  return payload.flatMap((item) => {
    const suite = normalizeSuite(item);
    return suite ? [suite] : [];
  });
}

export async function runEvalSuite(
  token: string,
  suiteName: EvalSuiteName,
  options: {
    caseIds?: string[];
    signal?: AbortSignal;
  } = {},
): Promise<EvalRunResponse> {
  const response = await fetch(`${apiUrl}/internal/evals/run`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      suite: suiteName,
      case_ids: options.caseIds,
    }),
    cache: "no-store",
    signal: options.signal,
  });

  if (!response.ok) throw await errorForResponse(response);

  const payload = (await response.json()) as unknown;
  return normalizeEvalRunResponse(payload);
}

export function normalizeEvalRunResponse(payload: unknown): EvalRunResponse {
  if (!isRecord(payload) || !Array.isArray(payload.cases)) {
    throw new EvalClientError("评测运行报告结构无法识别。");
  }

  const dataClassification = asString(payload.data_classification);
  const runScope = payload.run_scope;
  const caseCount = asNumber(payload.case_count);
  const totalSuiteCaseCount = asNumber(payload.total_suite_case_count);
  const passCount = asNumber(payload.pass_count);
  const failCount = asNumber(payload.fail_count);
  const durationMs = asNumber(payload.duration_ms);
  if (
    dataClassification !== "synthetic" ||
    !isAllowedValue(runScope, runScopes) ||
    caseCount === undefined ||
    passCount === undefined ||
    failCount === undefined ||
    durationMs === undefined
  ) {
    throw new EvalClientError("评测运行报告汇总字段不完整。");
  }

  const cases = payload.cases.map(normalizeCaseResult);
  const rawSuite = asString(payload.suite);
  const suite = isEvalSuiteName(rawSuite) ? rawSuite : undefined;
  const uniqueCaseIds = new Set(cases.map((item) => item.case_id));
  const caseIds = cases.map((item) => item.case_id);
  const computedPassCount = cases.filter((item) => item.passed).length;
  if (
    !Number.isInteger(caseCount) ||
    !Number.isInteger(passCount) ||
    !Number.isInteger(failCount) ||
    !Number.isInteger(durationMs) ||
    caseCount < 1 ||
    caseCount > 12 ||
    passCount < 0 ||
    failCount < 0 ||
    durationMs < 0 ||
    caseCount !== cases.length ||
    uniqueCaseIds.size !== cases.length ||
    passCount + failCount !== caseCount ||
    passCount !== computedPassCount ||
    failCount !== caseCount - computedPassCount ||
    typeof payload.passed !== "boolean" ||
    payload.passed !== (failCount === 0)
  ) {
    throw new EvalClientError("评测运行报告计数不一致。");
  }

  if (runScope === "explicit_cases") {
    if (rawSuite !== undefined || totalSuiteCaseCount !== undefined) {
      throw new EvalClientError("显式案例报告不能声称完整套件覆盖。");
    }
  } else {
    if (
      !suite ||
      rawSuite !== suite ||
      totalSuiteCaseCount === undefined ||
      !Number.isInteger(totalSuiteCaseCount) ||
      totalSuiteCaseCount < 1 ||
      totalSuiteCaseCount > 12 ||
      totalSuiteCaseCount < caseCount
    ) {
      throw new EvalClientError("评测运行报告的套件覆盖范围不一致。");
    }

    const catalogCaseIds: readonly string[] = evalSuiteCatalog[suite];
    const orderedSelectedIds = catalogCaseIds.filter((caseId) =>
      caseIds.includes(caseId),
    );
    if (
      totalSuiteCaseCount !== catalogCaseIds.length ||
      caseIds.some((caseId) => !catalogCaseIds.includes(caseId)) ||
      !arraysEqual(caseIds, orderedSelectedIds) ||
      (runScope === "full_suite" && !arraysEqual(caseIds, catalogCaseIds))
    ) {
      throw new EvalClientError("评测运行报告的套件覆盖范围不一致。");
    }
  }

  return {
    suite,
    run_scope: runScope,
    total_suite_case_count: totalSuiteCaseCount,
    data_classification: dataClassification,
    case_count: caseCount,
    passed: payload.passed === true,
    pass_count: passCount,
    fail_count: failCount,
    duration_ms: durationMs,
    cases,
  };
}

export function isRetryableEvalFailure(result: EvalCaseResult): boolean {
  return (
    !result.passed &&
    (result.error === "timeout" || result.pipeline_failure?.retryable === true)
  );
}
