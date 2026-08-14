"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  type EvalCaseResult,
  type EvalRunResponse,
  type EvalSuite,
  fetchEvalSuites,
  runEvalSuite,
} from "@/lib/evals";

const coreSuiteName = "pas-core-v0.1";

type CategorySummary = {
  name: string;
  total: number;
  passed: number;
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

function CaseResult({ result }: { result: EvalCaseResult }) {
  const memoryConfidence =
    result.memory_candidate_confidence === "medium"
      ? "中置信度"
      : result.memory_candidate_confidence === "low"
        ? "低置信度"
        : "未返回置信度";

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
              {result.review_completed ? "已完成" : "未完成"}
            </dd>
          </div>
        </dl>

        {result.error && (
          <div className="mt-5 rounded-2xl border border-[#c7aaa4] bg-[#f8efec] px-4 py-3 text-sm leading-6 text-[#7a463d]">
            <p className="font-semibold">案例运行错误</p>
            <p className="mt-1 break-words">{result.error}</p>
          </div>
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
              未返回 Review metadata；本案例的 Review 未完成。
            </p>
          )}
        </section>

        <section className="mt-6">
          <h3 className="text-sm font-semibold">最终回答（Review 后）</h3>
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
  const [run, setRun] = useState<EvalRunResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const tokenInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  const categorySummaries = useMemo(
    () => summarizeCategories(run?.cases ?? []),
    [run],
  );

  const loadedSuite = suites.find((suite) => suite.name === coreSuiteName);
  const resultCount = run?.cases.length ?? 0;
  const total = run?.case_count ?? 0;
  const passed = run?.pass_count ?? 0;
  const failed = run?.fail_count ?? 0;
  const passRate = run && total ? (passed / total) * 100 : 0;
  const totalLatency = run?.duration_ms ?? 0;

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
    setRunning(true);
    setError(null);
    setSuites([]);
    setRun(null);

    try {
      const availableSuites = await fetchEvalSuites(
        evalToken,
        controller.signal,
      );
      setSuites(availableSuites);

      if (!availableSuites.some((suite) => suite.name === coreSuiteName)) {
        throw new Error("后端没有返回 pas-core-v0.1 内建评测套件。");
      }

      const result = await runEvalSuite(
        evalToken,
        coreSuiteName,
        controller.signal,
      );
      setRun(result);
    } catch (caught) {
      if (caught instanceof Error && caught.name === "AbortError") return;
      setError(
        caught instanceof Error ? caught.message : "内部评测出现未知错误。",
      );
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
      setRunning(false);
    }
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
          <div className="mt-2 flex flex-col gap-3 sm:flex-row">
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
            <button
              className="button-primary shrink-0 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={running || !token.trim()}
              type="submit"
            >
              {running ? "正在运行…" : "运行 pas-core-v0.1"}
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
            正在读取套件并逐项运行评测，请保持此页面打开。
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
                本次评测结果
              </h2>
              <p className="mt-2 text-xs text-[var(--muted)]">
                {run.suite ?? coreSuiteName} · {run.data_classification}
              </p>
            </div>
            <div className="flex flex-col items-start gap-2 sm:items-end">
              <span
                className={
                  run.passed
                    ? "rounded-full border border-[#9eb5a6] bg-[#eef2ec] px-3 py-1 text-xs font-semibold text-[#48675b]"
                    : "rounded-full border border-[#c7aaa4] bg-[#f8efec] px-3 py-1 text-xs font-semibold text-[#7a463d]"
                }
              >
                {run.passed ? "套件整体通过" : "套件存在未通过案例"}
              </span>
              <p className="text-sm text-[var(--muted)]" role="status">
                评测完成，共返回 {resultCount} 条案例结果。
              </p>
            </div>
          </div>

          <dl className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
            {[
              ["总通过率", formatRate(passRate)],
              ["案例总数", String(total)],
              ["通过", String(passed)],
              ["未通过", String(failed)],
              ["总耗时", formatLatency(totalLatency)],
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
            {run.cases.length ? (
              <div className="mt-4 space-y-3">
                {run.cases.map((result, index) => (
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
