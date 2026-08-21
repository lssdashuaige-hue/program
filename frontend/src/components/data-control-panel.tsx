"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  DataControlApiError,
  type DataControlState,
  type SavedMemory,
  deleteMemoryLineage,
  downloadDataExport,
  loadDataControlState,
  permanentlyDeleteAccount,
  reviseMemory,
  updateMemoryEnabled,
  updateMemoryStatus,
} from "@/lib/data-control";
import { createClient } from "@/lib/supabase/client";

const accountConfirmation = "删除我的 PAS 账户";
const kindLabels: Record<SavedMemory["kind"], string> = {
  experience: "经历",
  reflection: "理解",
  pattern: "观察中的模式",
  need: "重要需要",
};

function messageForError(error: unknown): string {
  return error instanceof DataControlApiError
    ? error.message
    : "这项操作没有完成，请稍后重试。";
}

function groupedMemories(memories: SavedMemory[]): Array<{
  current: SavedMemory;
  versions: SavedMemory[];
}> {
  const groups = new Map<string, SavedMemory[]>();
  for (const memory of memories) {
    const versions = groups.get(memory.lineage_id) ?? [];
    versions.push(memory);
    groups.set(memory.lineage_id, versions);
  }
  return Array.from(groups.values()).map((versions) => {
    const sorted = versions.toSorted((left, right) => right.version - left.version);
    return { current: sorted[0], versions: sorted };
  });
}

export function DataControlPanel() {
  const [state, setState] = useState<DataControlState | null>(null);
  const [loading, setLoading] = useState(true);
  const [signedOut, setSignedOut] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [deleteConfirmation, setDeleteConfirmation] = useState("");

  useEffect(() => {
    let active = true;
    void loadDataControlState()
      .then((loaded) => {
        if (active) setState(loaded);
      })
      .catch((caught) => {
        if (!active) return;
        if (caught instanceof DataControlApiError && caught.status === 401) {
          setSignedOut(true);
        } else {
          setError(messageForError(caught));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const memoryGroups = useMemo(
    () => groupedMemories(state?.memories ?? []),
    [state?.memories],
  );

  function begin(action: string) {
    setBusy(action);
    setNotice(null);
    setError(null);
  }

  function finish() {
    setBusy(null);
  }

  async function handleMemoryToggle() {
    if (!state || busy) return;
    const enabled = !state.memory_enabled;
    begin("memory-setting");
    try {
      const updated = await updateMemoryEnabled(enabled);
      setState((current) =>
        current
          ? {
              ...current,
              memory_enabled: updated.memory_enabled,
              memory_enabled_at: updated.memory_enabled_at,
            }
          : current,
      );
      setNotice(
        enabled
          ? "你已明确开启长期记忆。首次保存仍需要逐条确认。"
          : "长期记忆已暂停；不会生成新候选，已有版本仍可查看、导出或删除。",
      );
    } catch (caught) {
      setError(messageForError(caught));
    } finally {
      finish();
    }
  }

  async function handleRevision(memory: SavedMemory) {
    if (!state || busy) return;
    const content = drafts[memory.id] ?? memory.content;
    if (!content.trim() || content === memory.content) {
      setError("请先写下需要保存的新版本内容。");
      return;
    }
    begin(`revise-${memory.id}`);
    try {
      const revised = await reviseMemory(memory.id, memory.version, content);
      setState((current) =>
        current
          ? {
              ...current,
              memories: [
                revised,
                ...current.memories.map((item) =>
                  item.id === memory.id
                    ? {
                        ...item,
                        status: "superseded" as const,
                        superseded_at: revised.confirmed_at,
                        paused_at: null,
                      }
                    : item,
                ),
              ],
            }
          : current,
      );
      setDrafts((current) => {
        const next = { ...current };
        delete next[memory.id];
        return next;
      });
      setNotice(`已保存为第 ${revised.version} 版；原文和上一版仍保留在版本记录中。`);
    } catch (caught) {
      setError(messageForError(caught));
    } finally {
      finish();
    }
  }

  async function handleStatus(memory: SavedMemory) {
    if (!state || busy) return;
    const nextStatus = memory.status === "paused" ? "active" : "paused";
    begin(`status-${memory.id}`);
    try {
      const updated = await updateMemoryStatus(memory.id, nextStatus);
      setState((current) =>
        current
          ? {
              ...current,
              memories: current.memories.map((item) =>
                item.id === updated.id ? updated : item,
              ),
            }
          : current,
      );
      setNotice(nextStatus === "paused" ? "这条记忆已暂停。" : "这条记忆已恢复。" );
    } catch (caught) {
      setError(messageForError(caught));
    } finally {
      finish();
    }
  }

  async function handleDelete(memory: SavedMemory) {
    if (!state || busy) return;
    if (!window.confirm("删除后，这条记忆的全部版本都无法在 PAS 中恢复。确认删除吗？")) {
      return;
    }
    begin(`delete-${memory.lineage_id}`);
    try {
      await deleteMemoryLineage(memory.lineage_id);
      setState((current) =>
        current
          ? {
              ...current,
              memories: current.memories.filter(
                (item) => item.lineage_id !== memory.lineage_id,
              ),
            }
          : current,
      );
      setNotice("这条记忆及其版本记录已从活跃数据库删除。" );
    } catch (caught) {
      setError(messageForError(caught));
    } finally {
      finish();
    }
  }

  async function handleExport() {
    if (busy) return;
    begin("export");
    try {
      await downloadDataExport();
      setNotice("导出已下载到你的设备；PAS 没有在服务器创建导出文件。");
    } catch (caught) {
      setError(messageForError(caught));
    } finally {
      finish();
    }
  }

  async function handleAccountDelete() {
    if (busy || deleteConfirmation !== accountConfirmation) return;
    if (!window.confirm("这是永久操作。确认删除 PAS 账户及活跃数据库中的个人数据吗？")) {
      return;
    }
    begin("account-delete");
    try {
      await permanentlyDeleteAccount();
      try {
        await createClient().auth.signOut({ scope: "local" });
      } finally {
        window.location.replace("/?account=deleted");
      }
    } catch (caught) {
      setError(messageForError(caught));
      finish();
    }
  }

  if (loading) {
    return <p className="mt-10 text-sm text-[var(--muted)]" role="status">正在读取你的数据控制状态…</p>;
  }

  if (signedOut) {
    return (
      <section className="quiet-card mt-10 p-6 sm:p-8">
        <h2 className="text-xl font-medium">登录后管理你的数据</h2>
        <p className="mt-3 max-w-2xl leading-7 text-[var(--muted)]">
          临时会话无需登录；记忆设置、已保存版本、导出和账户删除只对已验证的账户开放。
        </p>
        <Link className="button-primary mt-5" href="/auth?next=/settings/privacy">前往登录</Link>
      </section>
    );
  }

  if (!state) {
    return (
      <section className="quiet-card mt-10 p-6 sm:p-8">
        <h2 className="text-xl font-medium">暂时无法读取控制状态</h2>
        <p className="mt-3 text-[var(--muted)]">{error ?? "请稍后重新打开此页面。"}</p>
      </section>
    );
  }

  return (
    <div className="mt-10 space-y-10">
      {(notice || error) && (
        <p
          className={error ? "text-sm text-[#9f3a38]" : "text-sm text-[var(--muted)]"}
          role={error ? "alert" : "status"}
        >
          {error ?? notice}
        </p>
      )}

      <section aria-labelledby="memory-control" className="quiet-card p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-2xl">
            <p className="eyebrow">Explicit opt-in</p>
            <h2 className="mt-3 text-2xl font-medium" id="memory-control">长期记忆默认关闭</h2>
            <p className="mt-3 leading-7 text-[var(--muted)]">
              开启只允许 PAS 在已保存、低风险的普通探索后提出候选；每条仍需你确认。关闭后不会产生新候选，已有记忆也不会发送给模型。
            </p>
          </div>
          <button
            aria-pressed={state.memory_enabled}
            className={state.memory_enabled ? "button-secondary" : "button-primary"}
            disabled={busy !== null}
            onClick={() => void handleMemoryToggle()}
            type="button"
          >
            {busy === "memory-setting"
              ? "正在更新…"
              : state.memory_enabled
                ? "暂停长期记忆"
                : "明确开启长期记忆"}
          </button>
        </div>
        {!state.memory_feature_available && (
          <p className="mt-5 rounded-2xl border border-[var(--line)] bg-[var(--surface-quiet)] px-4 py-3 text-sm leading-6 text-[var(--muted)]">
            当前部署尚未启用记忆候选模型。你的选择可以被记录，但在服务端功能开启前不会生成候选。
          </p>
        )}
        <p className="mt-4 text-xs leading-5 text-[var(--muted)]">
          已保存记忆当前不参与模型上下文；接入前还需独立来源与隐私验收。
        </p>
      </section>

      <section aria-labelledby="saved-memories">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Versioned memories</p>
            <h2 className="mt-3 text-2xl font-medium" id="saved-memories">你确认过的记忆</h2>
          </div>
          <span className="status-chip">{memoryGroups.length} 条</span>
        </div>
        {memoryGroups.length === 0 ? (
          <p className="quiet-card mt-5 p-6 leading-7 text-[var(--muted)]">
            这里还没有经你确认的长期记忆。PAS 不会用空白页面替你编造内容。
          </p>
        ) : (
          <ul className="mt-5 space-y-5">
            {memoryGroups.map(({ current, versions }) => (
              <li className="quiet-card p-6 sm:p-8" key={current.lineage_id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="status-chip">{kindLabels[current.kind]} · 第 {current.version} 版</span>
                  <span className="text-xs text-[var(--muted)]">
                    {current.status === "paused" ? "已暂停" : "当前版本"}
                  </span>
                </div>
                <div className="mt-5 grid gap-5 lg:grid-cols-2">
                  <div>
                    <h3 className="text-sm font-medium">首次确认的完整原话</h3>
                    <blockquote className="mt-2 whitespace-pre-wrap rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 leading-7">
                      {current.original_content}
                    </blockquote>
                  </div>
                  <div>
                    <label className="text-sm font-medium" htmlFor={`memory-${current.id}`}>当前确认版本</label>
                    <textarea
                      className="mt-2 min-h-28 w-full rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 leading-7 outline-none"
                      id={`memory-${current.id}`}
                      maxLength={8000}
                      onChange={(event) =>
                        setDrafts((items) => ({ ...items, [current.id]: event.target.value }))
                      }
                      value={drafts[current.id] ?? current.content}
                    />
                    <p className="mt-2 text-xs leading-5 text-[var(--muted)]">
                      修改会生成一个由你主动编写的新版本，旧版本不会被倒写。
                    </p>
                  </div>
                </div>
                <div className="mt-5 flex flex-wrap gap-3">
                  <button
                    className="button-primary"
                    disabled={busy !== null || (drafts[current.id] ?? current.content) === current.content}
                    onClick={() => void handleRevision(current)}
                    type="button"
                  >
                    {busy === `revise-${current.id}` ? "正在保存…" : "保存为新版本"}
                  </button>
                  <button
                    className="button-secondary"
                    disabled={busy !== null}
                    onClick={() => void handleStatus(current)}
                    type="button"
                  >
                    {current.status === "paused" ? "恢复这条记忆" : "暂停这条记忆"}
                  </button>
                  <button
                    className="button-quiet text-[#8a3f3a]"
                    disabled={busy !== null}
                    onClick={() => void handleDelete(current)}
                    type="button"
                  >
                    删除全部版本
                  </button>
                </div>
                {versions.length > 1 && (
                  <details className="mt-5 border-t border-[var(--line)] pt-4">
                    <summary className="text-sm font-medium">查看 {versions.length} 个版本</summary>
                    <ol className="mt-3 space-y-3">
                      {versions.map((version) => (
                        <li className="rounded-2xl bg-[var(--surface-quiet)] px-4 py-3 text-sm" key={version.id}>
                          <p className="font-medium">第 {version.version} 版 · {version.version_origin === "source_quote" ? "首次原话" : "用户修改"}</p>
                          <p className="mt-1 whitespace-pre-wrap text-[var(--muted)]">{version.content}</p>
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="export-data" className="quiet-card p-6 sm:p-8">
        <h2 className="text-2xl font-medium" id="export-data">导出你的数据</h2>
        <p className="mt-3 max-w-3xl leading-7 text-[var(--muted)]">
          导出包含活跃数据库中的账户资料、探索历史、主题、记忆版本与同意状态。文件直接下载到你的设备，服务器不创建临时导出副本。
        </p>
        <button className="button-secondary mt-5" disabled={busy !== null} onClick={() => void handleExport()} type="button">
          {busy === "export" ? "正在准备…" : "下载 JSON 导出"}
        </button>
      </section>

      <section aria-labelledby="delete-account" className="rounded-[1.75rem] border border-[#c8a7a2] bg-[#fbf2f0] p-6 sm:p-8">
        <h2 className="text-2xl font-medium" id="delete-account">永久删除账户</h2>
        <p className="mt-3 max-w-3xl leading-7 text-[var(--muted)]">
          此操作删除 Auth 账户并通过级联清除活跃数据库中的个人资料、探索、消息、记忆与主题。Provider 日志、备份残留周期和你已下载的文件不在这一步的可控范围内，产品上线前仍需完成处理者清单与删除 SLA。
        </p>
        <label className="mt-5 block text-sm font-medium" htmlFor="account-delete-confirmation">
          输入“{accountConfirmation}”确认
        </label>
        <input
          autoComplete="off"
          className="mt-2 w-full max-w-lg rounded-2xl border border-[#c8a7a2] bg-white px-4 py-3 outline-none"
          id="account-delete-confirmation"
          onChange={(event) => setDeleteConfirmation(event.target.value)}
          value={deleteConfirmation}
        />
        <button
          className="mt-4 rounded-full bg-[#7d3935] px-5 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
          disabled={busy !== null || deleteConfirmation !== accountConfirmation}
          onClick={() => void handleAccountDelete()}
          type="button"
        >
          {busy === "account-delete" ? "正在删除…" : "永久删除我的账户"}
        </button>
      </section>
    </div>
  );
}
