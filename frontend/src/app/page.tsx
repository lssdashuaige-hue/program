import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen overflow-hidden">
      <nav className="mx-auto flex h-24 w-full max-w-6xl items-center justify-between px-5 sm:px-8">
        <span className="text-sm font-semibold tracking-[0.22em]">PAS</span>
        <span className="text-xs tracking-[0.16em] text-[var(--muted)] uppercase">
          Psychological AI System
        </span>
      </nav>

      <section className="relative mx-auto grid min-h-[calc(100vh-6rem)] w-full max-w-6xl items-center gap-14 px-5 pb-24 sm:px-8 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="relative z-10">
          <p className="mb-7 text-sm tracking-[0.18em] text-[var(--muted)]">
            一处属于你的反思空间
          </p>
          <h1 className="max-w-3xl text-5xl leading-[1.08] font-medium tracking-[-0.055em] sm:text-7xl">
            不是定义你，
            <br />
            而是帮助你
            <span className="text-[#6f8d7d]">理解自己。</span>
          </h1>
          <p className="mt-8 max-w-xl text-base leading-8 text-[var(--muted)] sm:text-lg">
            PAS 通过持续、开放的对话，陪你观察情绪、选择与反复出现的模式。
            它不做诊断，不给你贴标签，也不会替你决定人生。
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-5">
            <Link
              className="rounded-full bg-[var(--ink)] px-7 py-3.5 text-sm font-medium text-white transition hover:-translate-y-0.5 hover:shadow-lg"
              href="/explore"
            >
              开始探索自己
            </Link>
            <p className="text-xs leading-5 text-[var(--muted)]">
              Alpha 预览
              <br />
              当前对话不会保存
            </p>
          </div>
        </div>

        <aside className="relative min-h-96" aria-hidden="true">
          <div className="absolute top-1/2 left-1/2 h-80 w-80 -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#aebeb3] opacity-70" />
          <div className="absolute top-1/2 left-1/2 h-60 w-60 -translate-x-[42%] -translate-y-[56%] rounded-full border border-[#8da596] opacity-55" />
          <div className="absolute top-1/2 left-1/2 h-40 w-40 -translate-x-[58%] -translate-y-[42%] rounded-full bg-[rgba(158,181,166,0.35)] blur-sm" />
          <div className="absolute top-1/2 left-1/2 flex h-44 w-44 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-[var(--surface)] text-center shadow-[0_35px_90px_rgba(36,54,52,0.14)]">
            <p className="text-sm leading-7 text-[var(--muted)]">
              看见
              <br />
              理解
              <br />
              选择
            </p>
          </div>
        </aside>
      </section>
    </main>
  );
}
