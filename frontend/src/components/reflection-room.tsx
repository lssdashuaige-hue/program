"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import { AuthStatus } from "@/components/auth-status";
import { MemoryCandidateCard } from "@/components/memory-candidate-card";
import {
  type MemoryCandidate,
  type PersistenceResult,
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
};

type RequestStatus = "idle" | "sending" | "stopping";

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
      setInput((current) => (current.trim() ? current : message));
      setFailedRequest({ messageId, content: message, clientTurnId });

      if (caught instanceof Error && caught.name === "AbortError") {
        setRequestNotice(
          "已停止等待，你的文字已经放回输入框。若服务端此前已完成，使用同一内容重试会恢复已保存的结果。",
        );
      } else {
        setError(caught instanceof Error ? caught.message : "出现了未知错误。");
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
    const message = input.trim();
    if (!message || abortControllerRef.current) return;

    const previousRequest = failedRequest;
    const retryingSameExpression =
      previousRequest !== null && previousRequest.content === message;
    const messageId = retryingSameExpression
      ? previousRequest.messageId
      : `user-${messageIdRef.current++}`;
    const clientTurnId = retryingSameExpression
      ? previousRequest.clientTurnId
      : crypto.randomUUID();
    setInput("");
    setMessages((current) =>
      retryingSameExpression
        ? current.map((item) =>
              item.id === messageId ? { ...item, content: message } : item,
            )
        : [...current, { id: messageId, role: "user", content: message }],
    );
    await requestReflection(message, messageId, clientTurnId);
  }

  async function handleRetry() {
    if (!failedRequest || abortControllerRef.current) return;

    const request = failedRequest;
    setInput((current) => (current.trim() === request.content ? "" : current));
    await requestReflection(
      request.content,
      request.messageId,
      request.clientTurnId,
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
      <header className="mb-7 flex items-start justify-between gap-5 border-b border-[var(--line)] pb-6">
        <div>
          <p className="mb-2 text-xs font-medium tracking-[0.22em] text-[var(--muted)] uppercase">Reflection room</p>
          <h1 className="text-2xl font-medium tracking-[-0.03em] sm:text-3xl">
            {conversationId
              ? conversationTitle || "继续这段探索"
              : "今天，你想从哪里开始？"}
          </h1>
        </div>
        <AuthStatus />
      </header>
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
            <p>{message.content}</p>
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
        <label className="sr-only" htmlFor="reflection">写下此刻的想法</label>
        <textarea
          className="min-h-24 w-full resize-none bg-transparent px-3 py-2 leading-7 outline-none placeholder:text-[var(--muted)]"
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
