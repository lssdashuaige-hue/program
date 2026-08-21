import type { Metadata } from "next";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { DataControlPanel } from "@/components/data-control-panel";
import { PageIntro } from "@/components/page-intro";

export const metadata: Metadata = {
  title: "记忆与隐私",
  description: "管理 PAS 的长期记忆、临时会话、数据导出和账户删除。",
};

const controls = [
  ["临时会话", "新探索可选择不进入历史；当前页面关闭后无法恢复。"],
  ["记忆默认关闭", "只有你明确开启后，已保存的普通探索才可能提出候选。"],
  ["版本化修改", "首次原话不会被覆盖；修改会成为新的用户确认版本。"],
  ["导出与删除", "可即时导出活跃记录，或永久删除账户与活跃数据库数据。"],
];

export default function PrivacyPage() {
  return (
    <AppShell active="privacy">
      <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
        <PageIntro
          description="这里的按钮都连接真实服务端操作。未覆盖的 Provider 日志、备份残留和处理者删除责任仍会明确写出，不用一个开关冒充完整隐私承诺。"
          eyebrow="Memory & privacy"
          note="登录用户的数据控制"
          title="你的内容，应由你决定"
        />

        <section aria-labelledby="available-controls" className="mt-10">
          <h2 className="sr-only" id="available-controls">当前可用控制</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {controls.map(([title, description]) => (
              <article className="quiet-card p-6" key={title}>
                <p className="status-chip">本地闭环</p>
                <h3 className="mt-5 text-lg font-medium">{title}</h3>
                <p className="mt-3 text-sm leading-7 text-[var(--muted)]">{description}</p>
              </article>
            ))}
          </div>
        </section>

        <DataControlPanel />

        <aside className="mt-10 rounded-[1.75rem] border border-[#b9c8bd] bg-[var(--surface-quiet)] p-6 sm:p-8">
          <h2 className="text-xl font-medium">想先进行一次不留历史的整理？</h2>
          <p className="mt-3 max-w-3xl leading-7 text-[var(--muted)]">
            在新的反思空间选择“临时会话”。本页近期原话只用于当前页面的后续请求，不写入数据库，也不生成候选记忆。
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link className="button-primary" href="/explore">开始临时探索</Link>
            <Link className="button-secondary" href="/help/safety">查看安全边界</Link>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}
