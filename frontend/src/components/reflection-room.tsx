"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import { MemoryCandidateCard } from "@/components/memory-candidate-card";
import {
  type MemoryCandidate,
  type PersistenceResult,
  type ResponsePreference,
  type SupportMode,
  sendReflection,
} from "@/lib/api";
import type { ConversationMessage } from "@/lib/conversation-types";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type FailedRequest = {
  messageId: string;
  content: string;
  clientTurnId: string;
  responsePreference: ResponsePreference | null;
};

type RequestStatus = "idle" | "sending" | "stopping";

type ComposerSnapshot = {
  input: string;
  responsePreference: ResponsePreference | null;
};

const opening: Message = {
  id: "opening",
  role: "assistant",
  content: "这里不是测试，也不会急着定义你。你可以从最近反复想到的一件事开始。",
};

const startingPrompts = [
  "最近有件事一直在我脑海里打转",
  "我正在一个选择之间犹豫",
  "一段关系让我反复有同样的感受",
];

const responsePreferences: Array<{
  value: ResponsePreference;
  label: string;
}> = [
  { value: "listen", label: "先听我说" },
  { value: "organize", label: "帮我理清" },
  { value: "explore_causes", label: "分析可能原因" },
  { value: "next_step", label: "想一个下一步" },
];

type Props = {
  initialConversation?: {
    id: string;
    title: string | null;
  };
  initialMessages?: ConversationMessage[];
};

function titleFromMessage(message: string): string {
  const normalized = message.replace(/\s+/g, " ").trim();
  return normalized.length > 36 ? `${normalized.slice(0, 36)}…` : normalized;
}

function persistenceMessage(persistence: PersistenceResult): string | null {
  switch (persistence.status) {
    case "already_saved":
      return "这次重试已与原来保存的内容对齐，没有重复写入历史。";
    case "not_saved_support":
      return "这轮已切换到支持模式，没有写入探索历史，也不会形成候选记忆。";
    case "not_saved_fallback":
      return "本次使用了安全降级回应，因此这轮没有写入探索历史。";
    case "failed":
      return "PAS 已回应，但这轮没有成功写入历史。当前页面仍保留内容，刷新后可能无法恢复。";
    default:
      return null;
  }
}

function requestErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return "这次没有连接成功。你的表达已经保留，可以稍后重试。";
  }

  if (
    error instanceof TypeError ||
    /failed to fetch|networkerror|load failed/i.test(error.message)
  ) {
    return "这次没有连接成功。你的表达已经保留，可以稍后重试。";
  }

  return error.message || "这次没有完成。你的表达已经保留，可以稍后重试。";
}

export function ReflectionRoom({
  initialConversation,
  initialMessages = [],
}: Props) {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>(() =>
    initialMessages.length
      ? initialMessages.map(({ id, role, content }) => ({ id, role, content }))
      : [opening],
  );
  const [input, setInput] = useState("");
  const [responsePreference, setResponsePreference] =
    useState<ResponsePreference | null>(null);
  const [requestStatus, setRequestStatus] = useState<RequestStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [requestNotice, setRequestNotice] = useState<string | null>(null);
  const [failedRequest, setFailedRequest] = useState<FailedRequest | null>(null);
  const [supportMode, setSupportMode] = useState<SupportMode>("reflection");
  const [memoryCandidate, setMemoryCandidate] =
    useState<MemoryCandidate | null>(null);
  const [memoryNotice, setMemoryNotice] = useState<string | null>(null);
  const [persistenceNotice, setPersistenceNotice] = useState<string | null>(
    null,
  );
  const [conversationId, setConversationId] = useState<string | null>(
    initialConversation?.id ?? null,
  );
  const [conversationTitle, setConversationTitle] = useState(
    initialConversation?.title?.trim() || null,
  );
  const abortControllerRef = useRef<AbortController | null>(null);
  const messageIdRef = useRef(1);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const pending = requestStatus !== "idle";

  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  async function requestReflection(
    message: string,
    messageId: string,
    clientTurnId: string,
    preference: ResponsePreference | null,
    composerSnapshot: ComposerSnapshot,
  ) {
    if (abortControllerRef.current) return;

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setError(null);
    setRequestNotice(null);
    setFailedRequest(null);
    setMemoryCandidate(null);
    setMemoryNotice(null);
    setPersistenceNotice(null);
    setRequestStatus("sending");

    try {
      const result = await sendReflection(message, {
        clientTurnId,
        conversationId,
        responsePreference: preference,
        signal: controller.signal,
      });
      const savedPersistence =
        result.persistence.status === "saved" ||
        result.persistence.status === "already_saved"
          ? result.persistence
          : null;
      const responseId = savedPersistence
        ? savedPersistence.assistant_message_id
        : `assistant-${messageIdRef.current++}`;
      setMessages((current) => [
        ...current,
        { id: responseId, role: "assistant", content: result.response },
      ]);
      setSupportMode(result.support_mode);
      setPersistenceNotice(persistenceMessage(result.persistence));

      if (savedPersistence) {
        const firstSavedTurn = !conversationId;
        setConversationId(savedPersistence.conversation_id);
        if (firstSavedTurn) {
          setConversationTitle(titleFromMessage(message));
          if (savedPersistence.status === "saved") {
            setPersistenceNotice(
              "这段探索已保存。你可以从探索历史回到这里继续。",
            );
          }
          router.replace(`/explore/${savedPersistence.conversation_id}`, {
            scroll: false,
          });
        }
      }

      setMemoryCandidate(
        result.support_mode === "support"
          ? null
          : result.memory_candidate
            ? {
                ...result.memory_candidate,
                source_message_id:
                  savedPersistence?.assistant_message_id,
              }
            : null,
      );
    } catch (caught) {
      setInput(composerSnapshot.input);
      setResponsePreference(composerSnapshot.responsePreference);
      setFailedRequest({
        messageId,
        content: message,
        clientTurnId,
        responsePreference: preference,
      });

      if (caught instanceof Error && caught.name === "AbortError") {
        setRequestNotice(
          "已停止等待，你的文字已经放回输入框。若服务端此前已完成，使用同一内容重试会恢复已保存的结果。",
        );
      } else {
        setError(requestErrorMessage(caught));
      }
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      setRequestStatus("idle");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input.trim() || abortControllerRef.current) return;

    const message = input;
    const preference = responsePreference;

    const previousRequest = failedRequest;
    const retryingSameExpression =
      previousRequest !== null &&
      previousRequest.content === message &&
      previousRequest.responsePreference === preference;
    const messageId = retryingSameExpression
      ? previousRequest.messageId
      : `user-${messageIdRef.current++}`;
    const clientTurnId = retryingSameExpression
      ? previousRequest.clientTurnId
      : crypto.randomUUID();
    setInput("");
    setResponsePreference(null);
    setMessages((current) =>
      retryingSameExpression
        ? current.map((item) =>
              item.id === messageId ? { ...item, content: message } : item,
            )
        : [...current, { id: messageId, role: "user", content: message }],
    );
    await requestReflection(message, messageId, clientTurnId, preference, {
      input: message,
      responsePreference: preference,
    });
  }

  async function handleRetry() {
    if (!failedRequest || abortControllerRef.current) return;

    const request = failedRequest;
    const composerSnapshot = { input, responsePreference };
    const composerIsRecoveredRequest =
      input === request.content &&
      responsePreference === request.responsePreference;
    if (composerIsRecoveredRequest) {
      setInput("");
      setResponsePreference(null);
    }
    await requestReflection(
      request.content,
      request.messageId,
      request.clientTurnId,
      request.responsePreference,
      composerSnapshot,
    );
  }

  function handleStop() {
    if (!abortControllerRef.current) return;
    setRequestStatus("stopping");
    abortControllerRef.current.abort();
  }

  function handleStartingPrompt(prompt: string) {
    setInput(prompt);
    inputRef.current?.focus();
  }

  return (
    <section className="mx-auto flex min-h-[calc(100vh-7rem)] w-full max-w-4xl flex-col px-5 py-8 sm:px-8">
      <header className="mb-7 border-b border-[var(--line)] pb-6">
        <div>
          <p className="mb-2 text-xs font-medium tracking-[0.22em] text-[var(--muted)] uppercase">Reflection room</p>
          <h1 className="text-2xl font-medium tracking-[-0.03em] sm:text-3xl">
            {conversationId
              ? conversationTitle || "继续这段探索"
              : "今天，你想从哪里开始？"}
          </h1>
        </div>
      </header>
      {!conversationId && messages.length === 1 && input.length === 0 && (
        <section className="mb-7" aria-labelledby="starting-prompts-title">
          <p
            className="text-sm leading-6 text-[var(--muted)]"
            id="starting-prompts-title"
          >
            如果一时不知道怎么开始，可以选一个起点，也可以直接跳过。
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {startingPrompts.map((prompt) => (
              <button
                className="rounded-full border border-[var(--line)] bg-[var(--surface)] px-4 py-2 text-left text-sm text-[var(--muted)] hover:text-[var(--ink)]"
                key={prompt}
                onClick={() => handleStartingPrompt(prompt)}
                type="button"
              >
                {prompt}
              </button>
            ))}
          </div>
        </section>
      )}
      <div className="flex flex-1 flex-col gap-4" aria-live="polite">
        {messages.map((message) => (
          <article
            className={message.role === "assistant"
              ? "max-w-2xl rounded-3xl rounded-tl-md bg-[var(--surface)] px-5 py-4 leading-7 shadow-[0_12px_40px_rgba(36,54,52,0.06)]"
              : "ml-auto max-w-2xl rounded-3xl rounded-tr-md bg-[var(--ink)] px-5 py-4 leading-7 text-white"}
            key={message.id}
          >
            <p
              className={message.role === "assistant"
                ? "mb-1 text-xs font-medium tracking-[0.08em] text-[var(--muted)]"
                : "mb-1 text-xs font-medium tracking-[0.08em] text-white/70"}
            >
              {message.role === "assistant" ? "PAS 的回应" : "你"}
            </p>
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          </article>
        ))}
        {pending && (
          <p className="text-sm text-[var(--muted)]" role="status">
            {requestStatus === "stopping"
              ? "正在停止这次回应…"
              : "PAS 正在整理你的表达…"}
          </p>
        )}
        {requestNotice && (
          <p className="text-sm leading-6 text-[var(--muted)]" role="status">
            {requestNotice}
          </p>
        )}
        {persistenceNotice && (
          <p className="text-sm leading-6 text-[var(--muted)]" role="status">
            {persistenceNotice}
          </p>
        )}
        {error && (
          <p className="text-sm leading-6 text-[#9f3a38]" role="alert">
            {error}
          </p>
        )}
        {failedRequest && !pending && (
          <button
            className="w-fit rounded-full border border-[var(--line)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--ink)]"
            onClick={() => void handleRetry()}
            type="button"
          >
            重试上一次表达
          </button>
        )}
        {supportMode === "support" && (
          <aside className="max-w-2xl rounded-3xl border border-[#b9c8bd] bg-[#f3f5ef] px-5 py-4">
            <h2 className="text-sm font-medium">先把现实中的支持放在前面</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
              如果你担心自己或他人此刻的安全，请暂停独自承受，联系身边可信任的人、当地紧急服务或危机支持。PAS 不能替代现实中的专业帮助。
            </p>
          </aside>
        )}
        {memoryCandidate && (
          <MemoryCandidateCard
            candidate={memoryCandidate}
            onDismiss={() => {
              setMemoryCandidate(null);
              setMemoryNotice("这条候选记忆没有保存。");
            }}
            onSaved={() => {
              setMemoryCandidate(null);
              setMemoryNotice("已按你的确认保存。你之后可以查看、修改或删除它。");
            }}
          />
        )}
        {memoryNotice && (
          <p className="text-sm text-[var(--muted)]" role="status">
            {memoryNotice}
          </p>
        )}
      </div>
      <form className="sticky bottom-4 mt-8 rounded-[1.75rem] border border-[var(--line)] bg-[rgba(250,248,243,0.94)] p-3 shadow-[0_20px_60px_rgba(36,54,52,0.12)] backdrop-blur" onSubmit={handleSubmit}>
        <fieldset
          aria-describedby="response-preference-help"
          className="px-2 pt-1"
          disabled={pending}
        >
          <legend className="text-sm font-medium text-[var(--ink)]">
            这一轮希望 PAS 怎么回应？
            <span className="ml-1 font-normal text-[var(--muted)]">（可选）</span>
          </legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {responsePreferences.map((preference) => {
              const selected = responsePreference === preference.value;
              return (
                <button
                  aria-pressed={selected}
                  className={
                    selected
                      ? "min-h-11 rounded-full border border-[var(--ink)] bg-[var(--ink)] px-4 py-2 text-sm font-medium text-white outline-none focus-visible:ring-2 focus-visible:ring-[var(--ink)] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                      : "min-h-11 rounded-full border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--muted)] outline-none hover:text-[var(--ink)] focus-visible:ring-2 focus-visible:ring-[var(--ink)] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  }
                  key={preference.value}
                  onClick={() =>
                    setResponsePreference((current) =>
                      current === preference.value ? null : preference.value,
                    )
                  }
                  type="button"
                >
                  <span aria-hidden="true">{selected ? "✓ " : ""}</span>
                  {preference.label}
                </button>
              );
            })}
          </div>
          <p
            className="mt-2 text-xs leading-5 text-[var(--muted)]"
            id="response-preference-help"
          >
            只影响这一轮的回应方式，不会改写你的文字；安全提醒仍会优先。
          </p>
        </fieldset>
        <label className="sr-only" htmlFor="reflection">写下此刻的想法</label>
        <textarea
          className="mt-2 min-h-24 w-full resize-none bg-transparent px-3 py-2 leading-7 outline-none placeholder:text-[var(--muted)] disabled:cursor-not-allowed disabled:opacity-60"
          disabled={pending}
          id="reflection"
          maxLength={8000}
          onChange={(event) => setInput(event.target.value)}
          placeholder="写下此刻最想整理的事情…"
          ref={inputRef}
          value={input}
        />
        <div className="flex items-center justify-between gap-3 px-2 pb-1">
          <p className="text-xs text-[var(--muted)]">PAS 不提供诊断，也不替你做决定</p>
          {pending ? (
            <button
              className="rounded-full border border-[var(--line)] bg-[var(--surface)] px-5 py-2.5 text-sm font-medium text-[var(--ink)] disabled:cursor-not-allowed disabled:opacity-40"
              disabled={requestStatus === "stopping"}
              onClick={handleStop}
              type="button"
            >
              {requestStatus === "stopping" ? "正在停止…" : "停止回应"}
            </button>
          ) : (
            <button className="rounded-full bg-[var(--ink)] px-5 py-2.5 text-sm font-medium text-white transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40" disabled={!input.trim()} type="submit">
              继续探索
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
