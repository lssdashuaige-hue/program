import type { Metadata } from "next";
import { InternalEvalsDashboard } from "@/components/internal-evals-dashboard";

export const metadata: Metadata = {
  title: "内部评测",
  description: "PAS 开发与安全边界评测工具，不提供心理服务。",
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: {
      index: false,
      follow: false,
      noimageindex: true,
    },
  },
};

export default function InternalEvalsPage() {
  return (
    <main className="min-h-screen px-5 py-10 sm:px-8 sm:py-14" id="main-content">
      <div className="mx-auto w-full max-w-6xl">
        <header className="border-b border-[var(--line)] pb-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="status-chip">内部工具</span>
            <span className="text-xs font-semibold tracking-[0.12em] text-[var(--muted)] uppercase">
              Development &amp; admin only
            </span>
          </div>
          <p className="eyebrow mt-7">PAS quality evaluation</p>
          <h1 className="mt-3 max-w-4xl text-4xl font-semibold tracking-[-0.045em] sm:text-5xl">
            PAS 内部评测
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-8 text-[var(--muted)]">
            此页面用于开发人员检查 PAS 的输出边界、支持模式与记忆提议规则。它不是心理服务，不提供诊断、治疗或危机支持，也不应作为普通用户的对话入口。
          </p>
        </header>

        <InternalEvalsDashboard />

        <footer className="mt-12 border-t border-[var(--line)] pt-6 text-xs leading-6 text-[var(--muted)]">
          内部评测结果只说明当前测试套件的运行情况，不代表对任何真实用户或心理状态的判断。
        </footer>
      </div>
    </main>
  );
}
