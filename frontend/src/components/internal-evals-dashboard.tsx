"use client";

import {
  ChangeEvent,
  FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  MAX_EVAL_RETRY_ATTEMPTS,
  createSavedEvalReport,
  parseSavedEvalReport,
} from "@/lib/eval-report-file";
import {
  EvalClientError,
  type EvalCaseResult,
  type EvalErrorCode,
  type EvalGatewayErrorCode,
  type EvalPipelineFailure,
  type EvalResponseSource,
  type EvalRiskLevel,
  type EvalRunResponse,
  type EvalSuite,
  type EvalSuiteName,
  evalSuiteNames,
  fetchEvalSuites,
  isEvalSuiteName,
  isRetryableEvalFailure,
  runEvalSuite,
} from "@/lib/evals";

const defaultSuiteName = "pas-dialogue-v0.1";
const maxReportBytes = 5 * 1024 * 1024;

type CategorySummary = {
  name: string;
  total: number;
  passed: number;
};

const errorLabels: Record<EvalErrorCode, string> = {
  pipeline_failed_closed: "评测管线已安全关闭",
  timeout: "案例运行超时",
  internal_error: "内部评测错误",
};

const gatewayErrorLabels: Record<EvalGatewayErrorCode, string> = {
  provider_authentication: "服务认证失败",
  provider_permission: "服务权限不足",
  provider_rate_limited: "服务触发限流",
  provider_timeout: "服务响应超时",
  provider_connection: "服务连接失败",
  provider_unavailable: "服务暂不可用",
  provider_http_error: "服务 HTTP 错误",
  empty_content: "响应内容为空",
  invalid_schema: "响应结构无效",
  unexpected_error: "未预期的管线错误",
};

const responseSourceLabels: Record<EvalResponseSource, string> = {
  review: "Review 审核回答",
  safety_guard: "模型前安全闸门",
  review_safety_envelope: "Review 后安全包络",
  safe_fallback: "固定安全降级",
};

const riskLevelLabels: Record<EvalRiskLevel, string> = {
  none: "无明确风险",
  concerning: "需要关注",
  urgent: "紧急风险",
};

function formatRate(value: number): string {
  return `${value.toFixed(value % 1 === 0 ? 0 : 1)}%`;
}

function formatLatency(value: number): string {
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

function summarizeCategories(results: EvalCaseResult[]): CategorySummary[] {
  const categories = new Map<string, CategorySummary>();

  for (const result of results) {
    const current = categories.get(result.category) ?? {
      name: result.category,
      total: 0,
      passed: 0,
    };
    current.total += 1;
    if (result.passed) current.passed += 1;
    categories.set(result.category, current);
  }

  return [...categories.values()].sort((left, right) =>
    left.name.localeCompare(right.name, "zh-CN"),
  );
}

function latestCaseResults(
  fullAttempt: EvalRunResponse | null,
  retryAttempts: EvalRunResponse[],
): EvalCaseResult[] {
  if (!fullAttempt) return [];

  const latestById = new Map(
    fullAttempt.cases.map((result) => [result.case_id, result]),
  );
  for (const attempt of retryAttempts) {
    for (const result of attempt.cases) {
      latestById.set(result.case_id, result);
    }
  }

  return fullAttempt.cases.map(
    (result) => latestById.get(result.case_id) ?? result,
  );
}

function retryableFailureIds(results: EvalCaseResult[]): string[] {
  return results.flatMap((result) =>
    isRetryableEvalFailure(result) ? [result.case_id] : [],
  );
}

function formatSavedAt(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function finalResponseTitle(source?: EvalResponseSource): string {
  if (source === "safety_guard") return "最终回答（模型前安全闸门）";
  if (source === "review_safety_envelope") {
    return "最终回答（Review 后安全包络）";
  }
  if (source === "safe_fallback") return "最终回答（固定安全降级）";
  if (source === "review") return "最终回答（Review 后）";
  return "最终回答（未生成回答）";
}

function PipelineFailureDetails({
  failure,
}: {
  failure: EvalPipelineFailure;
}) {
  return (
    <section className="mt-5 rounded-2xl border border-[#c7aaa4] bg-[#f8efec] px-4 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-[#7a463d]">
          Pipeline diagnostic
        </h3>
        <span className="rounded-full border border-[#c7aaa4] px-2.5 py-1 text-xs font-semibold text-[#7a463d]">
          内部调试 · 安全白名单
        </span>
      </div>
      <p className="mt-2 text-xs leading-6 text-[#7a463d]">
        这里只显示固定枚举、布尔值和 HTTP 状态；不会显示原始异常、请求标识值、服务配置或模型思考过程。
      </p>
      <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs font-semibold text-[#7a463d]">失败阶段</dt>
          <dd className="mt-1 font-semibold">
            {failure.stage === "reflection" ? "Reflection" : "Review"}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-[#7a463d]">错误类别</dt>
          <dd className="mt-1 break-words">
            {gatewayErrorLabels[failure.code]}
            <span className="mt-1 block font-mono text-xs">{failure.code}</span>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-[#7a463d]">可否重试</dt>
          <dd className="mt-1">{failure.retryable ? "可以" : "不建议"}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-[#7a463d]">HTTP 状态</dt>
          <dd className="mt-1">
            {failure.http_status === undefined
              ? "未返回"
              : failure.http_status}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-[#7a463d]">
            Finish reason
          </dt>
          <dd className="mt-1 break-words font-mono text-xs">
            {failure.finish_reason ?? "未返回"}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-[#7a463d]">内容存在性</dt>
          <dd className="mt-1">
            {failure.content_present ? "存在内容" : "没有内容"}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-[#7a463d]">
            请求标识存在性
          </dt>
          <dd className="mt-1">
            {failure.request_id_present ? "存在（不显示值）" : "不存在"}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function CaseResult({ result }: { result: EvalCaseResult }) {
  const memoryConfidence =
    result.memory_candidate_confidence === "medium"
      ? "中置信度"
      : result.memory_candidate_confidence === "low"
        ? "低置信度"
        : "未返回置信度";
  const directSafetyGuard =
    result.response_source === "safety_guard" && !result.review_completed;

  return (
    <details className="quiet-card overflow-hidden">
      <summary className="flex min-h-16 cursor-pointer flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-5">
        <span className="min-w-0">
          <span className="block break-all text-sm font-semibold">
            {result.case_id}
          </span>
          <span className="mt-1 block text-xs text-[var(--muted)]">
            {result.category} · {formatLatency(result.latency_ms)}
          </span>
        </span>
        <span
          className={
            result.passed
              ? "w-fit rounded-full border border-[#9eb5a6] bg-[#eef2ec] px-3 py-1 text-xs font-semibold text-[#48675b]"
              : "w-fit rounded-full border border-[#c7aaa4] bg-[#f8efec] px-3 py-1 text-xs font-semibold text-[#7a463d]"
          }
        >
          {result.passed ? "通过" : "未通过"}
        </span>
      </summary>

      <div className="border-t border-[var(--line)] px-5 py-5 sm:px-6">
        <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs font-semibold text-[var(--muted)]">运行模式</dt>
            <dd className="mt-1 break-words">{result.mode ?? "未完成"}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold text-[var(--muted)]">支持模式</dt>
            <dd className="mt-1">
              {result.support_mode === "support"
                ? "现实支持"
                : result.support_mode === "reflection"
                  ? "反思"
                  : "未完成"}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold text-[var(--muted)]">候选记忆</dt>
            <dd className="mt-1">
              {result.memory_candidate_present
                ? `已提出 · ${memoryConfidence}`
                : "未提出"}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold text-[var(--muted)]">Review</dt>
            <dd className="mt-1">
              {result.review_completed
                ? "已完成"
                : directSafetyGuard
                  ? "按设计跳过"
                  : "未完成"}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold text-[var(--muted)]">回答路径</dt>
            <dd className="mt-1 break-words">
              {result.response_source
                ? responseSourceLabels[result.response_source]
                : "未生成回答"}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold text-[var(--muted)]">规范风险</dt>
            <dd className="mt-1">
              {result.risk_level
                ? riskLevelLabels[result.risk_level]
                : "未返回"}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold text-[var(--muted)]">安全闸门</dt>
            <dd className="mt-1">
              {result.safety_guard_applied ? "已应用" : "未应用"}
            </dd>
          </div>
        </dl>

        {directSafetyGuard && (
          <p className="mt-5 rounded-2xl border border-[#9eb5a6] bg-[#eef2ec] px-4 py-3 text-sm leading-6 text-[#48675b]">
            模型前安全闸门按设计直接响应，未调用 Review。
          </p>
        )}

        {result.error && (
          <div className="mt-5 rounded-2xl border border-[#c7aaa4] bg-[#f8efec] px-4 py-3 text-sm leading-6 text-[#7a463d]">
            <p className="font-semibold">案例错误类别</p>
            <p className="mt-1 break-words">
              {errorLabels[result.error]}
              <span className="ml-2 font-mono text-xs">{result.error}</span>
            </p>
          </div>
        )}

        {result.pipeline_failure && (
          <PipelineFailureDetails failure={result.pipeline_failure} />
        )}

        {result.conversation_history.length > 0 && (
          <section className="mt-6">
            <h3 className="text-sm font-semibold">合成会话上下文</h3>
            <p className="mt-2 text-xs leading-6 text-[var(--muted)]">
              这是该案例实际提供给管线的合成历史，用于复现短追问和来源边界。
            </p>
            <ol className="mt-3 space-y-2">
              {result.conversation_history.map((message, index) => (
                <li
                  className="rounded-2xl border border-[var(--line)] bg-[var(--surface-quiet)] px-4 py-3 text-sm"
                  key={`${message.role}-${index}`}
                >
                  <p className="text-xs font-semibold text-[var(--muted)]">
                    {message.role === "user" ? "合成用户" : "既往 PAS 回应"}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap break-words leading-7">
                    {message.content}
                  </p>
                </li>
              ))}
            </ol>
          </section>
        )}

        <section className="mt-6">
          <h3 className="text-sm font-semibold">测试输入</h3>
          <blockquote className="mt-2 whitespace-pre-wrap break-words rounded-2xl bg-[var(--surface-quiet)] px-4 py-3 text-sm leading-7">
            {result.input || "未返回输入内容。"}
          </blockquote>
        </section>

        <section className="mt-6">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">Reflection draft</h3>
            <span className="rounded-full border border-[#c7aaa4] bg-[#f8efec] px-2.5 py-1 text-xs font-semibold text-[#7a463d]">
              内部调试 · 未经 Review
            </span>
          </div>
          <p className="mt-2 text-xs leading-6 text-[var(--muted)]">
            这是进入审核前的模型草稿，仅供内部审计，不是可展示给用户的 PAS 回答。
          </p>
          <div className="mt-2 whitespace-pre-wrap break-words rounded-2xl border border-[#c7aaa4] bg-[#f8efec] px-4 py-3 text-sm leading-7">
            {result.reflection_draft ?? "未返回 Reflection draft。"}
          </div>
        </section>

        <section className="mt-6">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">Review metadata</h3>
            <span className="rounded-full border border-[var(--line)] bg-[var(--surface-quiet)] px-2.5 py-1 text-xs font-semibold text-[var(--muted)]">
              内部调试
            </span>
          </div>
          {result.review ? (
            <div className="mt-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-quiet)] px-4 py-4">
              <dl className="grid gap-4 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-xs font-semibold text-[var(--muted)]">
                    审核决定
                  </dt>
                  <dd className="mt-1">
                    {result.review.approved ? "批准" : "未批准"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-[var(--muted)]">
                    风险等级
                  </dt>
                  <dd className="mt-1 break-words">
                    {result.review.risk_level}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-[var(--muted)]">
                    Issues
                  </dt>
                  <dd className="mt-1 break-words">
                    {result.review.issues.length
                      ? result.review.issues.join("、")
                      : "无"}
                  </dd>
                </div>
              </dl>
              <div className="mt-4 border-t border-[var(--line)] pt-4">
                <h4 className="text-xs font-semibold text-[var(--muted)]">
                  Review rationale（内部调试）
                </h4>
                <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-7">
                  {result.review.rationale}
                </p>
              </div>
            </div>
          ) : (
            <p className="mt-2 rounded-2xl border border-[var(--line)] px-4 py-3 text-sm text-[var(--muted)]">
              {directSafetyGuard
                ? "模型前安全闸门按设计直接响应，因此没有调用 Review。"
                : "未返回 Review metadata；本案例的 Review 未完成。"}
            </p>
          )}
        </section>

        <section className="mt-6">
          <h3 className="text-sm font-semibold">
            {finalResponseTitle(result.response_source)}
          </h3>
          <div className="mt-2 whitespace-pre-wrap break-words rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm leading-7">
            {result.final_response ?? "未返回最终回答。"}
          </div>
        </section>

        <section className="mt-6">
          <h3 className="text-sm font-semibold">断言结果</h3>
          {result.hard_assertions.length ? (
            <ul className="mt-3 space-y-2">
              {result.hard_assertions.map((assertion, index) => {
                const status = !assertion.applicable
                  ? "未适用"
                  : assertion.passed
                    ? "通过"
                    : "未通过";
                const statusClass = !assertion.applicable
                  ? "text-[var(--muted)]"
                  : assertion.passed
                    ? "text-[#48675b]"
                    : "text-[#7a463d]";

                return (
                  <li
                    className="rounded-2xl border border-[var(--line)] px-4 py-3 text-sm"
                    key={`${assertion.rule}-${index}`}
                  >
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className={`font-semibold ${statusClass}`}>
                        {status}
                      </span>
                      <span>{assertion.rule}</span>
                    </div>
                    <p className="mt-2 break-words leading-6 text-[var(--muted)]">
                      {assertion.detail}
                    </p>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[var(--muted)]">
              评测服务没有返回断言详情。
            </p>
          )}
        </section>
      </div>
    </details>
  );
}

export function InternalEvalsDashboard() {
  const [token, setToken] = useState("");
  const [suites, setSuites] = useState<EvalSuite[]>([]);
  const [selectedSuiteName, setSelectedSuiteName] =
    useState<EvalSuiteName>(defaultSuiteName);
  const [run, setRun] = useState<EvalRunResponse | null>(null);
  const [retryRuns, setRetryRuns] = useState<EvalRunResponse[]>([]);
  const [reportSavedAt, setReportSavedAt] = useState<string | null>(null);
  const [reportOrigin, setReportOrigin] = useState<"live" | "imported" | null>(
    null,
  );
  const [caseView, setCaseView] = useState<"first" | "current">("first");
  const [runningKind, setRunningKind] = useState<"full" | "retry" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const tokenInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  const currentCases = useMemo(
    () => latestCaseResults(run, retryRuns),
    [retryRuns, run],
  );
  const categorySummaries = useMemo(
    () => summarizeCategories(currentCases),
    [currentCases],
  );
  const displayedCases = caseView === "first" ? run?.cases ?? [] : currentCases;

  const running = runningKind !== null;
  const reportSuiteName = run?.suite ?? selectedSuiteName;
  const loadedSuite = suites.find((suite) => suite.name === reportSuiteName);
  const suiteOptions = suites.length
    ? suites.map((suite) => suite.name)
    : evalSuiteNames;
  const resultCount = currentCases.length;
  const total = run?.case_count ?? 0;
  const passed = run?.pass_count ?? 0;
  const failed = run?.fail_count ?? 0;
  const passRate = run && total ? (passed / total) * 100 : 0;
  const totalLatency = run?.duration_ms ?? 0;
  const currentPassed = currentCases.filter((result) => result.passed).length;
  const currentFailed = currentCases.length - currentPassed;
  const currentPassRate = currentCases.length
    ? (currentPassed / currentCases.length) * 100
    : 0;
  const retryableIds = retryableFailureIds(currentCases);

  async function handleRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (controllerRef.current) return;

    const evalToken = token.trim();

    if (!evalToken) {
      setError("请输入 PAS eval token 后再运行评测。");
      tokenInputRef.current?.focus();
      return;
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    setRunningKind("full");
    setError(null);

    try {
      const availableSuites = await fetchEvalSuites(
        evalToken,
        controller.signal,
      );
      setSuites(availableSuites);

      if (!availableSuites.some((suite) => suite.name === selectedSuiteName)) {
        throw new EvalClientError(
          `后端没有返回 ${selectedSuiteName} 内建评测套件。`,
        );
      }

      const result = await runEvalSuite(
        evalToken,
        selectedSuiteName,
        { signal: controller.signal },
      );
      if (result.run_scope !== "full_suite") {
        throw new EvalClientError("后端没有返回一次完整套件运行。");
      }
      setRun(result);
      setRetryRuns([]);
      setReportSavedAt(new Date().toISOString());
      setReportOrigin("live");
      setCaseView("first");
    } catch (caught) {
      if (caught instanceof Error && caught.name === "AbortError") return;
      setError(
        caught instanceof EvalClientError
          ? caught.message
          : "内部评测请求失败；原始错误详情未显示。",
      );
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
      setRunningKind(null);
    }
  }

  async function handleRetryFailures() {
    if (
      controllerRef.current ||
      !run?.suite ||
      reportOrigin !== "live" ||
      retryRuns.length >= MAX_EVAL_RETRY_ATTEMPTS ||
      retryableIds.length === 0
    ) {
      return;
    }

    const evalToken = token.trim();
    if (!evalToken) {
      setError("请输入 PAS eval token 后再重跑可重试故障。");
      tokenInputRef.current?.focus();
      return;
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    setRunningKind("retry");
    setError(null);

    try {
      const result = await runEvalSuite(evalToken, run.suite, {
        caseIds: retryableIds,
        signal: controller.signal,
      });
      if (result.run_scope !== "suite_subset") {
        throw new EvalClientError("后端没有返回可验证的失败项子集报告。");
      }
      setRetryRuns((current) => [...current, result]);
      setReportSavedAt(new Date().toISOString());
      setCaseView("current");
    } catch (caught) {
      if (caught instanceof Error && caught.name === "AbortError") return;
      setError(
        caught instanceof EvalClientError
          ? caught.message
          : "失败项重跑请求失败；原始错误详情未显示。",
      );
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
      setRunningKind(null);
    }
  }

  function handleDownloadReport() {
    if (!run) return;

    try {
      const report = createSavedEvalReport(run, retryRuns);
      const blob = new Blob([JSON.stringify(report, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const timestamp = report.saved_at.replace(/[:.]/g, "-");
      link.href = url;
      link.download = `pas-eval-${run.suite ?? "synthetic"}-${timestamp}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setReportSavedAt(report.saved_at);
    } catch (caught) {
      setError(
        caught instanceof EvalClientError
          ? caught.message
          : "无法生成评测报告文件。",
      );
    }
  }

  async function handleImportReport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (file.size > maxReportBytes) {
      setError("报告文件超过 5 MB，已拒绝打开。");
      return;
    }

    try {
      const parsed = parseSavedEvalReport(JSON.parse(await file.text()));
      setRun(parsed.full_attempt);
      setRetryRuns(parsed.retry_attempts);
      setReportSavedAt(parsed.saved_at);
      setReportOrigin("imported");
      setCaseView("current");
      if (parsed.full_attempt.suite) {
        setSelectedSuiteName(parsed.full_attempt.suite);
      }
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof EvalClientError
          ? caught.message
          : "报告文件不是有效的 PAS 评测 JSON。",
      );
    }
  }

  function clearReport() {
    setRun(null);
    setRetryRuns([]);
    setReportSavedAt(null);
    setReportOrigin(null);
    setCaseView("first");
    setError(null);
  }

  function clearToken() {
    setToken("");
    setError(null);
    tokenInputRef.current?.focus();
  }

  return (
    <div className="mt-10 space-y-8">
      <section className="quiet-card p-5 sm:p-7" aria-labelledby="eval-access">
        <div className="max-w-3xl">
          <p className="eyebrow">Restricted access</p>
          <h2 className="mt-2 text-xl font-semibold" id="eval-access">
            使用 PAS 内部评测令牌
          </h2>
          <p className="mt-3 text-sm leading-7 text-[var(--muted)]">
            令牌只保存在当前页面的 React 内存中；刷新或离开页面后会清除，不会写入 localStorage、sessionStorage 或 URL。
          </p>
        </div>

        <form className="mt-6" onSubmit={handleRun}>
          <label className="text-sm font-semibold" htmlFor="pas-evals-token">
            PAS eval token
          </label>
          <div className="mt-2 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(13rem,0.45fr)_auto_auto]">
            <input
              aria-describedby="eval-token-help"
              autoCapitalize="none"
              autoComplete="off"
              className="min-h-12 min-w-0 flex-1 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-3 font-mono text-sm outline-none disabled:cursor-not-allowed disabled:opacity-60"
              disabled={running}
              id="pas-evals-token"
              name="pas-evals-token"
              onChange={(event) => setToken(event.target.value)}
              ref={tokenInputRef}
              spellCheck={false}
              type="password"
              value={token}
            />
            <label className="sr-only" htmlFor="pas-evals-suite">
              选择评测套件
            </label>
            <select
              className="min-h-12 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-3 text-sm outline-none disabled:cursor-not-allowed disabled:opacity-60"
              disabled={running}
              id="pas-evals-suite"
              onChange={(event) => {
                if (isEvalSuiteName(event.target.value)) {
                  setSelectedSuiteName(event.target.value);
                }
              }}
              value={selectedSuiteName}
            >
              {suiteOptions.map((suiteName) => (
                <option key={suiteName} value={suiteName}>
                  {suiteName}
                </option>
              ))}
            </select>
            <button
              className="button-primary shrink-0 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={running || !token.trim()}
              type="submit"
            >
              {runningKind === "full"
                ? "正在运行…"
                : `运行 ${selectedSuiteName}`}
            </button>
            <button
              className="button-secondary shrink-0 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={running || !token}
              onClick={clearToken}
              type="button"
            >
              清除令牌
            </button>
          </div>
          <p className="mt-3 text-xs leading-6 text-[var(--muted)]" id="eval-token-help">
            这里只接受 PAS eval token。不要输入 OpenAI、DeepSeek 或其他模型供应商的 API key。
          </p>
        </form>

        {running && (
          <p className="mt-5 text-sm text-[var(--muted)]" role="status">
            {runningKind === "retry"
              ? "正在重跑可重试的管线故障；原完整报告会保留。"
              : "正在读取套件并逐项运行评测；旧报告会保留到新运行成功。"}
          </p>
        )}
        {error && (
          <p
            className="mt-5 rounded-2xl border border-[#c7aaa4] bg-[#f8efec] px-4 py-3 text-sm leading-6 text-[#7a463d]"
            role="alert"
          >
            {error}
          </p>
        )}

        <div className="mt-6 border-t border-[var(--line)] pt-5">
          <div className="flex flex-wrap gap-3">
            <button
              className="button-secondary disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!run || running}
              onClick={handleDownloadReport}
              type="button"
            >
              保存 JSON 报告
            </button>
            <label
              className={
                running
                  ? "button-secondary cursor-not-allowed opacity-50"
                  : "button-secondary cursor-pointer"
              }
              htmlFor="pas-eval-report-file"
            >
              打开已保存报告
            </label>
            <input
              accept="application/json,.json"
              className="sr-only"
              disabled={running}
              id="pas-eval-report-file"
              onChange={(event) => void handleImportReport(event)}
              type="file"
            />
            <button
              className="button-secondary disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!run || running}
              onClick={clearReport}
              type="button"
            >
              清除当前报告
            </button>
          </div>
          <p className="mt-3 text-xs leading-6 text-[var(--muted)]">
            报告文件包含合成输入、内部草稿和 Review 说明，但不包含评测令牌。文件只在你明确保存时下载；进行中的同步运行仍无法在断网或关闭页面后恢复。
          </p>
          {reportSavedAt && run && (
            <p className="mt-2 text-xs text-[var(--muted)]" role="status">
              当前报告生成或导入时间：{formatSavedAt(reportSavedAt)}
            </p>
          )}
        </div>
      </section>

      {loadedSuite && (
        <section className="quiet-card p-5 sm:p-7" aria-labelledby="suite-info">
          <p className="eyebrow">Loaded suite</p>
          <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-xl font-semibold" id="suite-info">
                {loadedSuite.name}
              </h2>
            </div>
            <span className="status-chip">{loadedSuite.case_count} 个案例</span>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-[var(--muted)]">
            {loadedSuite.description}
          </p>
          {loadedSuite.categories.length > 0 && (
            <div className="mt-5 flex flex-wrap gap-2" aria-label="套件分类">
              {loadedSuite.categories.map((category) => (
                <span
                  className="rounded-full border border-[var(--line)] bg-[var(--surface-quiet)] px-3 py-1 text-xs"
                  key={category}
                >
                  {category}
                </span>
              ))}
            </div>
          )}
          {loadedSuite.case_ids.length > 0 && (
            <details className="mt-5 rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
              <summary className="cursor-pointer text-sm font-semibold">
                查看 {loadedSuite.case_ids.length} 个 case ID
              </summary>
              <ul className="mt-3 grid gap-2 font-mono text-xs text-[var(--muted)] sm:grid-cols-2">
                {loadedSuite.case_ids.map((caseId) => (
                  <li className="break-all" key={caseId}>
                    {caseId}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}

      {run && (
        <section aria-labelledby="eval-summary">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="eyebrow">Run summary</p>
              <h2 className="mt-2 text-2xl font-semibold" id="eval-summary">
                完整运行与失败项重跑
              </h2>
              <p className="mt-2 text-xs text-[var(--muted)]">
                {run.suite ?? "explicit synthetic cases"} · {run.data_classification}
              </p>
            </div>
            <div className="flex flex-col items-start gap-2 sm:items-end">
              <span
                className={
                  reportOrigin === "imported"
                    ? "rounded-full border border-[var(--line-strong)] bg-[var(--surface-quiet)] px-3 py-1 text-xs font-semibold text-[var(--muted)]"
                    : run.passed
                    ? "rounded-full border border-[#9eb5a6] bg-[#eef2ec] px-3 py-1 text-xs font-semibold text-[#48675b]"
                    : "rounded-full border border-[#c7aaa4] bg-[#f8efec] px-3 py-1 text-xs font-semibold text-[#7a463d]"
                }
              >
                {reportOrigin === "imported"
                  ? "已导入 · 仅结构校验"
                  : run.passed
                  ? "首次完整运行通过"
                  : "首次完整运行存在未通过案例"}
              </span>
              <p className="text-sm text-[var(--muted)]" role="status">
                当前覆盖 {resultCount} 条案例；已记录 {retryRuns.length} 次失败项重跑。
              </p>
            </div>
          </div>

          {reportOrigin === "imported" && (
            <p className="mt-5 rounded-2xl border border-[#c8b48f] bg-[#faf5e8] px-4 py-3 text-sm leading-6 text-[#6f5a35]" role="status">
              JSON 文件可以被编辑。PAS 已校验版本、套件案例、断言关系与重跑顺序，但不能证明它由当前后端实时生成；请将它用于复查，不要把导入后的“通过”当作本轮验收。需要实时结论时，请重新运行完整套件。
            </p>
          )}

          <dl className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
            {[
              ["首次通过率", formatRate(passRate)],
              ["首次案例数", String(total)],
              ["首次通过", String(passed)],
              ["首次未通过", String(failed)],
              ["首次耗时", formatLatency(totalLatency)],
            ].map(([label, value]) => (
              <div className="quiet-card px-4 py-4" key={label}>
                <dt className="text-xs font-semibold text-[var(--muted)]">
                  {label}
                </dt>
                <dd className="mt-2 text-2xl font-semibold tracking-[-0.03em]">
                  {value}
                </dd>
              </div>
            ))}
          </dl>

          <section className="quiet-card mt-4 px-5 py-5" aria-labelledby="coverage-summary">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-sm font-semibold" id="coverage-summary">
                  含显式重跑的当前覆盖
                </h3>
                <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
                  {currentPassed} / {currentCases.length} 当前通过 · {formatRate(currentPassRate)}。
                  这是各案例最近一次结果的覆盖视图，不会改写首次完整运行的结论。
                </p>
              </div>
              <button
                className="button-secondary shrink-0 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={
                  running ||
                  reportOrigin !== "live" ||
                  retryRuns.length >= MAX_EVAL_RETRY_ATTEMPTS ||
                  retryableIds.length === 0
                }
                onClick={() => void handleRetryFailures()}
                type="button"
              >
                {runningKind === "retry"
                  ? "正在重跑…"
                  : `重跑可重试故障（${retryableIds.length}）`}
              </button>
            </div>
            {currentFailed > retryableIds.length && (
              <p className="mt-3 text-xs leading-6 text-[var(--muted)]">
                仍有 {currentFailed - retryableIds.length} 个质量或不可重试失败；它们不会被自动挑选重跑，应先修正实现后再运行完整套件。
              </p>
            )}
            {retryRuns.length >= MAX_EVAL_RETRY_ATTEMPTS && (
              <p className="mt-3 text-xs leading-6 text-[#7a463d]">
                已达到 {MAX_EVAL_RETRY_ATTEMPTS} 次显式重跑上限。请保存当前报告、修复稳定性问题，再重新运行完整套件。
              </p>
            )}
          </section>

          {retryRuns.length > 0 && (
            <details className="quiet-card mt-4 px-5 py-4">
              <summary className="cursor-pointer text-sm font-semibold">
                查看 {retryRuns.length} 次失败项重跑记录
              </summary>
              <ol className="mt-3 space-y-2 text-sm text-[var(--muted)]">
                {retryRuns.map((attempt, index) => (
                  <li key={`${attempt.duration_ms}-${index}`}>
                    第 {index + 1} 次：{attempt.pass_count} / {attempt.case_count} 通过 · {formatLatency(attempt.duration_ms)}
                  </li>
                ))}
              </ol>
            </details>
          )}

          <section className="mt-8" aria-labelledby="category-summary">
            <h3 className="text-lg font-semibold" id="category-summary">
              分类结果
            </h3>
            {categorySummaries.length ? (
              <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {categorySummaries.map((category) => {
                  const rate = category.total
                    ? (category.passed / category.total) * 100
                    : 0;
                  return (
                    <li className="quiet-card px-4 py-4" key={category.name}>
                      <p className="break-words text-sm font-semibold">
                        {category.name}
                      </p>
                      <p className="mt-2 text-sm text-[var(--muted)]">
                        {category.passed} / {category.total} 通过 · {formatRate(rate)}
                      </p>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-[var(--muted)]">
                没有可用于分类汇总的案例结果。
              </p>
            )}
          </section>

          <section className="mt-8" aria-labelledby="case-results">
            <div>
              <h3 className="text-lg font-semibold" id="case-results">
                单案例结果
              </h3>
              <p className="mt-2 text-sm text-[var(--muted)]">
                展开案例可查看测试输入、内部 Reflection draft、Review metadata、最终回答和逐条断言。
              </p>
            </div>
            <div
              className="mt-4 flex flex-wrap gap-2"
              role="group"
              aria-label="选择案例结果视图"
            >
              <button
                aria-pressed={caseView === "first"}
                className={
                  caseView === "first"
                    ? "rounded-full border border-[var(--ink)] bg-[var(--ink)] px-4 py-2 text-sm font-medium text-white"
                    : "rounded-full border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--muted)]"
                }
                onClick={() => setCaseView("first")}
                type="button"
              >
                首次完整运行
              </button>
              <button
                aria-pressed={caseView === "current"}
                className={
                  caseView === "current"
                    ? "rounded-full border border-[var(--ink)] bg-[var(--ink)] px-4 py-2 text-sm font-medium text-white"
                    : "rounded-full border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--muted)]"
                }
                onClick={() => setCaseView("current")}
                type="button"
              >
                含重跑的当前覆盖
              </button>
            </div>
            {displayedCases.length ? (
              <div className="mt-4 space-y-3">
                {displayedCases.map((result, index) => (
                  <CaseResult
                    key={`${result.case_id}-${index}`}
                    result={result}
                  />
                ))}
              </div>
            ) : (
              <p className="quiet-card mt-4 px-5 py-4 text-sm text-[var(--muted)]">
                评测服务返回了空结果，请检查后端运行日志。
              </p>
            )}
          </section>
        </section>
      )}
    </div>
  );
}
