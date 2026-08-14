"use client";

import Link from "next/link";
import { useState } from "react";
import type { MemoryCandidate } from "@/lib/api";
import { saveConfirmedMemory } from "@/lib/memory";

type Props = {
  candidate: MemoryCandidate;
  onDismiss: () => void;
  onSaved: () => void;
};

const kindLabels: Record<MemoryCandidate["kind"], string> = {
  experience: "一段经历",
  reflection: "你的理解",
  pattern: "正在观察的模式",
  need: "可能的重要需要",
};

export function MemoryCandidateCard({
  candidate,
  onDismiss,
  onSaved,
}: Props) {
  const [content, setContent] = useState(candidate.content);
  const [status, setStatus] = useState<
    "idle" | "saving" | "signed_out" | "error"
  >("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    const confirmedContent = content.trim();
    if (!confirmedContent || status === "saving") return;

    setStatus("saving");
    setError(null);

    let result;
    try {
      result = await saveConfirmedMemory({
        ...candidate,
        content: confirmedContent,
      });
    } catch {
      setStatus("error");
      setError("暂时无法连接到你的私密空间，请稍后重试。");
      return;
    }

    if (result.status === "saved") {
      onSaved();
      return;
    }

    if (result.status === "signed_out") {
      setStatus("signed_out");
      return;
    }

    setStatus("error");
    setError(result.message);
  }

  return (
    <aside className="max-w-2xl rounded-3xl border border-[#b9c8bd] bg-[#f3f5ef] px-5 py-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-medium">需要你确认的理解</h2>
          <p className="mt-1 text-xs font-medium tracking-[0.12em] text-[var(--muted)]">
            {kindLabels[candidate.kind]}
          </p>
        </div>
        <span className="rounded-full border border-[#c7d3ca] px-2.5 py-1 text-xs text-[var(--muted)]">
          尚未保存
        </span>
      </div>
      <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
        {candidate.confirmation_prompt}
      </p>
      <div className="mt-4">
        <label className="text-sm font-medium" htmlFor="memory-candidate-content">
          你希望保存的表述
        </label>
        <textarea
          className="mt-2 min-h-28 w-full resize-y rounded-2xl border border-[#c7d3ca] bg-[var(--surface)] px-4 py-3 leading-7 outline-none focus:border-[#7f9a89]"
          disabled={status === "saving"}
          id="memory-candidate-content"
          maxLength={1000}
          onChange={(event) => setContent(event.target.value)}
          value={content}
        />
        <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
          这只是等待你确认的理解，不是对你的定义。你可以先修改，再决定是否保存。
        </p>
      </div>

      {status === "signed_out" && (
        <p className="mt-4 text-sm leading-6 text-[var(--muted)]" role="status">
          需要先登录，才能把它保存到只属于你的心理地图。
          <Link className="ml-2 underline underline-offset-4" href="/auth?next=/explore">
            前往登录
          </Link>
        </p>
      )}
      {status === "saving" && (
        <p className="mt-4 text-sm text-[var(--muted)]" role="status">
          正在保存经你确认的表述…
        </p>
      )}
      {error && (
        <p className="mt-4 text-sm text-[#9f3a38]" role="alert">
          {error}
        </p>
      )}

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          className="rounded-full bg-[var(--ink)] px-5 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
          disabled={status === "saving" || !content.trim()}
          onClick={handleSave}
          type="button"
        >
          {status === "saving" ? "正在保存…" : "确认并保存"}
        </button>
        <button
          className="rounded-full border border-[var(--line)] px-5 py-2.5 text-sm text-[var(--muted)]"
          disabled={status === "saving"}
          onClick={onDismiss}
          type="button"
        >
          暂不保存
        </button>
      </div>
    </aside>
  );
}
