import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { PageIntro } from "@/components/page-intro";

export const metadata: Metadata = {
  title: "心理地图",
  description: "一张由你确认、可以持续修正的当前理解地图。",
};

const mapSections = [
  { title: "容易触发我的情境", description: "暂无已确认内容" },
  { title: "常见的情绪与反应", description: "暂无已确认内容" },
  { title: "可能的保护方式", description: "暂无已确认内容" },
  { title: "我重视或需要什么", description: "暂无已确认内容" },
  { title: "正在尝试的新方向", description: "暂无已确认内容" },
];

export default function MapPage() {
  return (
    <AppShell active="map">
      <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
        <PageIntro
          description="这不是人格分类，也不是关于你的最终结论。地图只应呈现你确认过、并且随时可以修正的当前理解。"
          eyebrow="Current understanding"
          note="尚未读取任何个人地图数据"
          title="一张仍然开放的心理地图"
        />

        <div className="mt-10">
          <EmptyState
            actionHref="/explore"
            actionLabel="从一次探索开始"
            description="心理地图页面目前还没有接入已保存的候选记忆。为了避免替你编造模式，这里只显示明确的空状态。"
            title="还没有可呈现的已确认观察"
          />
        </div>

        <section aria-labelledby="map-sections" className="mt-14">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="max-w-2xl">
              <p className="eyebrow">地图结构</p>
              <h2
                className="mt-4 text-2xl font-medium tracking-[-0.035em] sm:text-3xl"
                id="map-sections"
              >
                接通数据后，会从这些角度整理
              </h2>
            </div>
            <p className="text-sm text-[var(--muted)]">
              不使用诊断分数或人格类型
            </p>
          </div>
          <ul className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {mapSections.map((section) => (
              <li className="quiet-card min-h-40 p-6" key={section.title}>
                <span className="status-chip">未连接</span>
                <h3 className="mt-6 text-lg font-medium">{section.title}</h3>
                <p className="mt-2 text-sm text-[var(--muted)]">
                  {section.description}
                </p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </AppShell>
  );
}
