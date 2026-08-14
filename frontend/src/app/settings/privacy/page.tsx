import type { Metadata } from "next";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { PageIntro } from "@/components/page-intro";

export const metadata: Metadata = {
  title: "记忆与隐私",
  description: "了解 PAS 如何保存探索、候选记忆与当前尚未开放的控制。",
};

const unavailable = [
  "查看与逐条修改记忆",
  "暂停记忆参与",
  "导出个人数据",
  "删除记忆或账户数据",
];

export default function PrivacyPage() {
  return (
    <AppShell active="privacy">
      <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
        <PageIntro
          description="这里清楚说明当前 Alpha 已经做到什么、还没有做到什么；未接通的控制不会伪装成可用按钮。"
          eyebrow="Memory & privacy"
          note="Alpha 数据控制仍在建设"
          title="你的内容，应由你决定"
        />

        <section aria-labelledby="privacy-now" className="mt-10">
          <h2 className="text-2xl font-medium tracking-[-0.035em]" id="privacy-now">
            当前真实边界
          </h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {[
              [
                "探索会话",
                "未登录时探索只保留在当前页面；登录后，符合安全保存规则且成功写入的原话与 PAS 最终回应会进入探索历史。",
              ],
              ["候选记忆", "只有登录并明确点击确认后，候选内容才会提交保存。"],
              [
                "不保存的选择",
                "你可以保持未登录状态进行临时探索，也可以对每条候选记忆选择暂不保存。",
              ],
            ].map(([title, description]) => (
              <article className="quiet-card p-6" key={title}>
                <p className="status-chip">当前说明</p>
                <h3 className="mt-5 text-lg font-medium">{title}</h3>
                <p className="mt-3 text-sm leading-7 text-[var(--muted)]">
                  {description}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section aria-labelledby="privacy-later" className="mt-14">
          <h2 className="text-2xl font-medium tracking-[-0.035em]" id="privacy-later">
            这些控制尚未开放
          </h2>
          <p className="mt-3 max-w-2xl leading-7 text-[var(--muted)]">
            在后端接口和结果反馈接通前，这里只说明状态，不提供没有实际作用的开关。
          </p>
          <ul className="mt-6 divide-y divide-[var(--line)] rounded-[1.75rem] border border-[var(--line)] bg-[rgba(255,253,248,0.72)] px-5 sm:px-7">
            {unavailable.map((item) => (
              <li className="flex items-center justify-between gap-4 py-5" key={item}>
                <span className="font-medium">{item}</span>
                <span className="status-chip shrink-0">尚未开放</span>
              </li>
            ))}
          </ul>
        </section>

        <aside className="mt-10 rounded-[1.75rem] border border-[#b9c8bd] bg-[var(--surface-quiet)] p-6 sm:p-8">
          <h2 className="text-xl font-medium">现在不希望保存这段探索？</h2>
          <p className="mt-3 max-w-3xl leading-7 text-[var(--muted)]">
            当前 Alpha 会尝试保存登录后符合规则的探索；支持模式、安全降级回应或写入失败的回合不会进入历史。如果你只想进行一次临时整理，可以在未登录状态使用反思空间；候选记忆无论是否登录，都不会在未经确认时保存。
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link className="button-primary" href="/explore">返回探索</Link>
            <Link className="button-secondary" href="/help/safety">查看安全边界</Link>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}
