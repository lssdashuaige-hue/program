import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { PageIntro } from "@/components/page-intro";

export const metadata: Metadata = {
  title: "探索历史",
  description: "按主题与变化回看自己的探索，而不是一串聊天记录。",
};

const historyLayers = [
  {
    title: "你的原话",
    description: "保留当时的表达，不把系统转述伪装成你的结论。",
  },
  {
    title: "你确认的理解",
    description: "只呈现你明确认可过、并愿意保留的观察。",
  },
  {
    title: "仍待验证的方向",
    description: "可能的联系会保留不确定性，不会被写成既定事实。",
  },
];

export default function HistoryPage() {
  return (
    <AppShell active="history">
      <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
        <PageIntro
          description="历史应该帮助你看见一个主题如何变化，而不是用日期和消息数量制造进度感。"
          eyebrow="Exploration history"
          note="此页面尚未接入真实历史数据"
          title="把变化放回主题里看"
        />

        <div className="mt-10">
          <EmptyState
            actionHref="/explore"
            actionLabel="开始一次探索"
            description="这个页面目前还不能读取你的真实探索历史。我们不会用示例对话填充它；在数据接口接通后，这里才会显示属于你的内容。"
            title="这里还没有可显示的探索历史"
          />
        </div>

        <section aria-labelledby="history-structure" className="mt-14">
          <div className="max-w-2xl">
            <p className="eyebrow">接通后如何整理</p>
            <h2
              className="mt-4 text-2xl font-medium tracking-[-0.035em] sm:text-3xl"
              id="history-structure"
            >
              三种内容会保持清楚区分
            </h2>
          </div>
          <ul className="mt-7 grid gap-4 md:grid-cols-3">
            {historyLayers.map((layer) => (
              <li className="quiet-card p-6" key={layer.title}>
                <h3 className="text-lg font-medium">{layer.title}</h3>
                <p className="mt-3 text-sm leading-7 text-[var(--muted)]">
                  {layer.description}
                </p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </AppShell>
  );
}
