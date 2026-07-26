"use client";

import { FormEvent, useState } from "react";
import { sendReflection } from "@/lib/api";

type Message = { role: "user" | "assistant"; content: string };

const opening: Message = {
  role: "assistant",
  content: "这里不是测试，也不会急着定义你。你可以从最近反复想到的一件事开始。",
};

export function ReflectionRoom() {
  const [messages, setMessages] = useState<Message[]>([opening]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
    if (!message || pending) return;
    setInput("");
    setError(null);
    setPending(true);
    setMessages((current) => [...current, { role: "user", content: message }]);
    try {
      const result = await sendReflection(message);
      setMessages((current) => [...current, { role: "assistant", content: result.response }]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "出现了未知错误。");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mx-auto flex min-h-[calc(100vh-7rem)] w-full max-w-4xl flex-col px-5 py-8 sm:px-8">
      <header className="mb-7 flex items-start justify-between gap-5 border-b border-[var(--line)] pb-6">
        <div>
          <p className="mb-2 text-xs font-medium tracking-[0.22em] text-[var(--muted)] uppercase">Reflection room</p>
          <h1 className="text-2xl font-medium tracking-[-0.03em] sm:text-3xl">今天，你想从哪里开始？</h1>
        </div>
        <span className="rounded-full border border-[var(--line)] px-3 py-1.5 text-xs text-[var(--muted)]">当前不保存记忆</span>
      </header>
      <div className="flex flex-1 flex-col gap-4" aria-live="polite">
        {messages.map((message, index) => (
          <article
            className={message.role === "assistant"
              ? "max-w-2xl rounded-3xl rounded-tl-md bg-[var(--surface)] px-5 py-4 leading-7 shadow-[0_12px_40px_rgba(36,54,52,0.06)]"
              : "ml-auto max-w-2xl rounded-3xl rounded-tr-md bg-[var(--ink)] px-5 py-4 leading-7 text-white"}
            key={`${message.role}-${index}`}
          >
            {message.content}
          </article>
        ))}
        {pending && <p className="text-sm text-[var(--muted)]">PAS 正在整理你的表达…</p>}
        {error && <p className="text-sm text-[#9f3a38]">{error}</p>}
      </div>
      <form className="sticky bottom-4 mt-8 rounded-[1.75rem] border border-[var(--line)] bg-[rgba(250,248,243,0.94)] p-3 shadow-[0_20px_60px_rgba(36,54,52,0.12)] backdrop-blur" onSubmit={handleSubmit}>
        <label className="sr-only" htmlFor="reflection">写下此刻的想法</label>
        <textarea
          className="min-h-24 w-full resize-none bg-transparent px-3 py-2 leading-7 outline-none placeholder:text-[var(--muted)]"
          id="reflection"
          maxLength={8000}
          onChange={(event) => setInput(event.target.value)}
          placeholder="写下此刻最想整理的事情…"
          value={input}
        />
        <div className="flex items-center justify-between gap-3 px-2 pb-1">
          <p className="text-xs text-[var(--muted)]">PAS 不提供诊断，也不替你做决定</p>
          <button className="rounded-full bg-[var(--ink)] px-5 py-2.5 text-sm font-medium text-white transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40" disabled={!input.trim() || pending} type="submit">
            继续探索
          </button>
        </div>
      </form>
    </section>
  );
}
