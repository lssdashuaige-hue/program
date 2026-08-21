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
  const [status, setStatus] = useState<
    "idle" | "saving" | "signed_out" | "error"
  >("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!candidate.content.trim() || status === "saving") return;

    setStatus("saving");
    setError(null);

    let result;
    try {
      result = await saveConfirmedMemory({
        ...candidate,
        content: candidate.content,
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
        <h3 className="text-sm font-medium">等待你确认的原话</h3>
        <blockquote className="mt-2 whitespace-pre-wrap rounded-2xl border border-[#c7d3ca] bg-[var(--surface)] px-4 py-3 leading-7">
          {candidate.content}
        </blockquote>
        <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
          为了保留否定、引用和来源语境，当前版本只允许按原话确认。
          如果这段表述不适合长期保存，请选择暂不保存；带版本记录的编辑功能尚未开放。
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
          disabled={status === "saving" || !candidate.content.trim()}
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
