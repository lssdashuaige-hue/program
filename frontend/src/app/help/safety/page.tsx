import type { Metadata } from "next";
import Link from "next/link";
import { PageIntro } from "@/components/page-intro";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "安全与能力边界",
  description: "了解 PAS 的能力边界与紧急危险时应优先采取的现实行动。",
};

export default function SafetyPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader active="safety" variant="public" />
      <main className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14" id="main-content">
        <PageIntro
          description="PAS 是 AI 辅助自我理解工具，不是心理医生、治疗服务或危机干预渠道。"
          eyebrow="Safety & boundaries"
          title="什么时候可以使用 PAS，什么时候不应该等待它"
        />

        <section className="mt-10 rounded-[2rem] border-2 border-[var(--ink)] bg-[var(--surface)] p-6 sm:p-9" aria-labelledby="urgent-title">
          <p className="eyebrow">需要立即行动的情况</p>
          <h2 className="mt-4 text-2xl font-medium tracking-[-0.035em]" id="urgent-title">
            如果你或他人可能正处于即时危险
          </h2>
          <p className="mt-4 max-w-3xl leading-8 text-[var(--muted)]">
            请立即联系所在地的急救或报警服务，或联系能够马上到场的可信任的人。不要等待 PAS 回复，也不要把它作为紧急情况下的唯一支持。
          </p>
        </section>

        <section className="mt-12 grid gap-4 md:grid-cols-2" aria-label="使用边界">
          <article className="quiet-card p-6 sm:p-8">
            <p className="status-chip">适合作为辅助</p>
            <h2 className="mt-5 text-xl font-medium">日常的自我观察与整理</h2>
            <p className="mt-3 leading-7 text-[var(--muted)]">
              梳理困惑、关系事件或选择，观察可能的模式，并形成由你确认、可以修正的理解。
            </p>
          </article>
          <article className="quiet-card p-6 sm:p-8">
            <p className="status-chip">不适合作为替代</p>
            <h2 className="mt-5 text-xl font-medium">诊断、治疗与紧急支持</h2>
            <p className="mt-3 leading-7 text-[var(--muted)]">
              PAS 不判断疾病或人格类型，不替代心理治疗、精神医疗、专业评估与危机干预。
            </p>
          </article>
        </section>

        <section className="quiet-card mt-12 p-6 sm:p-9">
          <h2 className="text-2xl font-medium tracking-[-0.035em]">技术故障不应被伪装成理解</h2>
          <p className="mt-4 max-w-3xl leading-8 text-[var(--muted)]">
            网络、AI 或安全服务不可用时，PAS 应明确说明状态，而不是生成看似合理的替代回应。重要决定请回到现实信息、可信任的人与专业支持中核实。
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link className="button-primary" href="/explore">开始探索</Link>
            <Link className="button-secondary" href="/settings/privacy">查看数据边界</Link>
          </div>
        </section>
      </main>
    </div>
  );
}
