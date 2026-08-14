import "client-only";

export type EvalSuite = {
  name: string;
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
  risk_level: string;
  rationale: string;
};

export type EvalCaseResult = {
  case_id: string;
  category: string;
  input: string;
  reflection_draft?: string;
  final_response?: string;
  mode?: string;
  support_mode?: "reflection" | "support";
  memory_candidate_present: boolean;
  memory_candidate_confidence?: "low" | "medium";
  review_completed: boolean;
  review?: EvalReview;
  hard_assertions: EvalAssertion[];
  passed: boolean;
  latency_ms: number;
  error?: string;
};

export type EvalRunResponse = {
  suite?: string;
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

function normalizeSuite(value: unknown): EvalSuite | null {
  if (!isRecord(value)) return null;

  const name = asString(value.name);
  const description = asString(value.description);
  const caseCount = asNumber(value.case_count);
  if (!name || !description || caseCount === undefined) return null;

  return {
    name,
    description,
    case_count: caseCount,
    case_ids: asStringArray(value.case_ids),
    categories: asStringArray(value.categories),
  };
}

function normalizeAssertion(value: unknown, index: number): EvalAssertion {
  if (!isRecord(value)) {
    return {
      rule: `assertion-${index + 1}`,
      applicable: true,
      passed: false,
      detail: "评测服务返回了无法识别的断言数据。",
    };
  }

  return {
    rule: asString(value.rule) ?? `assertion-${index + 1}`,
    applicable:
      typeof value.applicable === "boolean" ? value.applicable : true,
    passed: value.passed === true,
    detail: asString(value.detail) ?? "未返回断言说明。",
  };
}

function normalizeReview(value: unknown): EvalReview | undefined {
  if (!isRecord(value)) return undefined;

  return {
    approved: value.approved === true,
    issues: asStringArray(value.issues),
    risk_level: asString(value.risk_level) ?? "unknown",
    rationale: asString(value.rationale) ?? "未返回 Review rationale。",
  };
}

function normalizeCaseResult(value: unknown, index: number): EvalCaseResult {
  if (!isRecord(value)) {
    throw new Error(`评测服务返回的第 ${index + 1} 条案例结果无法识别。`);
  }

  const supportMode = asString(value.support_mode);
  const memoryConfidence = asString(value.memory_candidate_confidence);

  return {
    case_id: asString(value.case_id) ?? `case-${index + 1}`,
    category: asString(value.category) ?? "未分类",
    input: asString(value.input) ?? "",
    reflection_draft: asString(value.reflection_draft),
    final_response: asString(value.final_response),
    mode: asString(value.mode),
    support_mode:
      supportMode === "reflection" || supportMode === "support"
        ? supportMode
        : undefined,
    memory_candidate_present: value.memory_candidate_present === true,
    memory_candidate_confidence:
      memoryConfidence === "low" || memoryConfidence === "medium"
        ? memoryConfidence
        : undefined,
    review_completed: value.review_completed === true,
    review: normalizeReview(value.review),
    hard_assertions: Array.isArray(value.hard_assertions)
      ? value.hard_assertions.map(normalizeAssertion)
      : [],
    passed: value.passed === true,
    latency_ms: asNumber(value.latency_ms) ?? 0,
    error: asString(value.error),
  };
}

async function errorForResponse(response: Response): Promise<Error> {
  if (response.status === 401 || response.status === 403) {
    return new Error("评测令牌无效，或当前环境不允许访问内部评测。");
  }

  if (response.status === 404) {
    return new Error("当前后端尚未启用内部评测接口。");
  }

  let detail: string | undefined;
  try {
    const payload = (await response.json()) as unknown;
    if (isRecord(payload)) detail = asString(payload.detail);
  } catch {
    // A non-JSON error response is reported using its HTTP status below.
  }

  return new Error(
    detail
      ? `评测请求失败：${detail.slice(0, 300)}`
      : `评测请求失败（HTTP ${response.status}）。`,
  );
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
    throw new Error("评测服务返回了无法识别的套件列表。");
  }

  return payload.flatMap((item) => {
    const suite = normalizeSuite(item);
    return suite ? [suite] : [];
  });
}

export async function runEvalSuite(
  token: string,
  suiteName: string,
  signal?: AbortSignal,
): Promise<EvalRunResponse> {
  const response = await fetch(`${apiUrl}/internal/evals/run`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ suite: suiteName }),
    cache: "no-store",
    signal,
  });

  if (!response.ok) throw await errorForResponse(response);

  const payload = (await response.json()) as unknown;
  if (!isRecord(payload) || !Array.isArray(payload.cases)) {
    throw new Error("评测服务返回了无法识别的运行结果。");
  }

  const dataClassification = asString(payload.data_classification);
  const caseCount = asNumber(payload.case_count);
  const passCount = asNumber(payload.pass_count);
  const failCount = asNumber(payload.fail_count);
  const durationMs = asNumber(payload.duration_ms);
  if (
    dataClassification !== "synthetic" ||
    caseCount === undefined ||
    passCount === undefined ||
    failCount === undefined ||
    durationMs === undefined
  ) {
    throw new Error("评测服务返回的运行汇总字段不完整。");
  }

  return {
    suite: asString(payload.suite),
    data_classification: dataClassification,
    case_count: caseCount,
    passed: payload.passed === true,
    pass_count: passCount,
    fail_count: failCount,
    duration_ms: durationMs,
    cases: payload.cases.map(normalizeCaseResult),
  };
}
