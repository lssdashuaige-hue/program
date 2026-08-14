import Link from "next/link";
import { OpenRingMark } from "@/components/open-ring-mark";
import { SiteHeader } from "@/components/site-header";

const startingPoints = [
  {
    title: "最近的困惑",
    description: "一件反复想起、却还说不清为什么在意的事。",
  },
  {
    title: "一个选择",
    description: "两个方向都重要，而你还没有准备好下结论。",
  },
  {
    title: "一段关系",
    description: "某次互动留下了情绪，或一个熟悉的反应再次出现。",
  },
  {
    title: "今天的感受",
    description: "无需先有完整问题，只从此刻真实的体验开始。",
  },
];

const steps = [
  {
    number: "01",
    title: "从你的体验开始",
    description: "你决定谈什么，也可以跳过任何不想继续的方向。",
  },
  {
    number: "02",
    title: "一起观察可能的模式",
    description: "PAS 提出问题和可能联系，但会保留不确定性。",
  },
  {
    number: "03",
    title: "由你确认什么成立",
    description: "理解不是系统给出的标签，而是你逐渐形成的判断。",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen overflow-hidden">
      <SiteHeader active="home" variant="public" />

      <main id="main-content">
        <section className="relative mx-auto grid min-h-[calc(100vh-4.5rem)] w-full max-w-6xl items-center gap-10 px-5 py-16 sm:px-8 sm:py-20 lg:grid-cols-[1.18fr_0.82fr] lg:py-24">
          <div className="relative z-10">
            <p className="eyebrow">AI 辅助自我理解 · Alpha</p>
            <h1 className="mt-6 max-w-3xl text-5xl leading-[1.08] font-medium tracking-[-0.055em] sm:text-7xl">
              不是定义你，
              <br />
              而是帮助你
              <span className="text-[var(--sage-deep)]">理解自己。</span>
            </h1>
            <p className="mt-8 max-w-2xl text-base leading-8 text-[var(--muted)] sm:text-lg">
              PAS 通过开放的对话，陪你观察情绪、选择与反复出现的模式。
              它不做诊断，不给你贴标签，也不会替你决定人生。
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link className="button-primary px-7" href="/explore">
                开始探索
                <span aria-hidden="true">→</span>
              </Link>
              <Link className="button-secondary" href="/help/safety">
                先了解边界
              </Link>
            </div>
            <p className="mt-6 max-w-xl text-sm leading-7 text-[var(--muted)]">
              无需登录即可开始。当前 Alpha 不保存整段对话；登录后，只有你主动确认的候选记忆会保存。
            </p>
          </div>

          <figure className="flex flex-col items-center justify-center gap-7 py-4">
            <OpenRingMark variant="hero" />
            <figcaption className="text-center text-xs tracking-[0.13em] text-[var(--muted)]">
              好奇 · 观察 · 理解 · 选择
            </figcaption>
          </figure>
        </section>

        <section
          aria-labelledby="how-title"
          className="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8 sm:py-24"
          id="how-it-works"
        >
          <div className="max-w-2xl">
            <p className="eyebrow">How it works</p>
            <h2
              className="mt-4 text-3xl font-medium tracking-[-0.04em] sm:text-4xl"
              id="how-title"
            >
              理解来自共同观察，而不是一次分析
            </h2>
          </div>
          <ol className="mt-10 grid gap-4 md:grid-cols-3">
            {steps.map((step) => (
              <li className="quiet-card p-6 sm:p-7" key={step.number}>
                <p className="text-xs font-semibold tracking-[0.16em] text-[var(--sage-deep)]">
                  {step.number}
                </p>
                <h3 className="mt-8 text-xl font-medium tracking-[-0.025em]">
                  {step.title}
                </h3>
                <p className="mt-3 leading-7 text-[var(--muted)]">
                  {step.description}
                </p>
              </li>
            ))}
          </ol>
        </section>

        <section
          aria-labelledby="start-title"
          className="mx-auto grid w-full max-w-6xl gap-10 px-5 py-20 sm:px-8 sm:py-24 lg:grid-cols-[0.72fr_1.28fr]"
        >
          <div>
            <p className="eyebrow">从真实体验开始</p>
            <h2
              className="mt-4 text-3xl font-medium tracking-[-0.04em] sm:text-4xl"
              id="start-title"
            >
              不必先把自己想明白
            </h2>
            <p className="mt-5 max-w-md leading-8 text-[var(--muted)]">
              你不需要准备一份完整的问题。只要选择此刻最接近你的入口，并用自己的话慢慢展开。
            </p>
            <Link className="button-secondary mt-7" href="/explore">
              去反思空间
            </Link>
          </div>
          <ul className="grid gap-4 sm:grid-cols-2">
            {startingPoints.map((point) => (
              <li className="quiet-card p-6" key={point.title}>
                <h3 className="text-lg font-medium">{point.title}</h3>
                <p className="mt-2 text-sm leading-7 text-[var(--muted)]">
                  {point.description}
                </p>
              </li>
            ))}
          </ul>
        </section>

        <section
          aria-labelledby="boundary-title"
          className="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8 sm:py-24"
        >
          <div className="quiet-card overflow-hidden">
            <div className="border-b border-[var(--line)] p-6 sm:p-9">
              <p className="eyebrow">清楚的边界</p>
              <h2
                className="mt-4 text-3xl font-medium tracking-[-0.04em]"
                id="boundary-title"
              >
                一处反思空间，不是心理诊室
              </h2>
            </div>
            <div className="grid md:grid-cols-2">
              <div className="p-6 sm:p-9 md:border-r md:border-[var(--line)]">
                <h3 className="text-lg font-medium">PAS 可以陪你做的</h3>
                <p className="mt-3 leading-7 text-[var(--muted)]">
                  整理体验、提出开放问题、观察可能的联系，并邀请你确认哪些理解真正符合自己。
                </p>
              </div>
              <div className="border-t border-[var(--line)] p-6 sm:p-9 md:border-t-0">
                <h3 className="text-lg font-medium">PAS 不会替代的</h3>
                <p className="mt-3 leading-7 text-[var(--muted)]">
                  心理诊断、治疗、危机干预与人生决定。处于紧急危险时，不要等待 PAS 回复。
                </p>
                <Link
                  className="mt-5 inline-flex min-h-11 items-center font-semibold underline decoration-[var(--line-strong)] underline-offset-4"
                  href="/help/safety"
                >
                  查看安全与能力边界
                </Link>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
          <div className="grid gap-8 rounded-[2rem] border border-[#b9c8bd] bg-[var(--surface-quiet)] p-7 sm:p-10 lg:grid-cols-[1fr_auto] lg:items-center">
            <div className="max-w-3xl">
              <p className="eyebrow">你的内容由你决定</p>
              <h2 className="mt-4 text-3xl font-medium tracking-[-0.04em]">
                保存之前，先由你确认
              </h2>
              <p className="mt-4 leading-8 text-[var(--muted)]">
                PAS 不会把每一句对话自动变成关于你的结论。当前 Alpha 只有在你登录并明确确认后，候选记忆才会保存。
              </p>
            </div>
            <Link className="button-secondary" href="/settings/privacy">
              查看当前数据边界
            </Link>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex w-full max-w-6xl flex-col gap-5 border-t border-[var(--line)] px-5 py-10 text-sm text-[var(--muted)] sm:px-8 md:flex-row md:items-center md:justify-between">
        <p>PAS · Understand yourself, live more freely.</p>
        <nav aria-label="页脚导航" className="flex flex-wrap gap-x-6 gap-y-3">
          <Link className="min-h-11 py-2 hover:text-[var(--ink)]" href="/auth">
            登录
          </Link>
          <Link
            className="min-h-11 py-2 hover:text-[var(--ink)]"
            href="/settings/privacy"
          >
            记忆与隐私
          </Link>
          <Link
            className="min-h-11 py-2 hover:text-[var(--ink)]"
            href="/help/safety"
          >
            安全与边界
          </Link>
        </nav>
      </footer>
    </div>
  );
}
