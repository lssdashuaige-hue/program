import { createClient } from "@/lib/supabase/client";

export type MemoryCandidate = {
  kind: "experience" | "reflection" | "pattern" | "need";
  content: string;
  confidence: "low" | "medium";
  confirmation_prompt: string;
  source_message_id?: string;
};

export type SupportMode = "reflection" | "support";

export type ResponseSource =
  | "review"
  | "safety_guard"
  | "review_safety_envelope"
  | "safe_fallback";

export type PersistenceResult =
  | { status: "not_requested" }
  | {
      status: "saved" | "already_saved";
      conversation_id: string;
      user_message_id: string;
      assistant_message_id: string;
    }
  | {
      status: "not_saved_support" | "not_saved_fallback";
      conversation_id?: string;
    }
  | {
      status: "failed";
      conversation_id?: string;
    };

export type ChatResponse = {
  response: string;
  mode: string;
  support_mode: SupportMode;
  response_source: ResponseSource;
  persistence: PersistenceResult;
  memory_candidate?: MemoryCandidate;
};

const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

type SendReflectionOptions = {
  clientTurnId: string;
  conversationId: string | null;
  signal?: AbortSignal;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function normalizePersistence(
  value: unknown,
  authenticated: boolean,
): PersistenceResult {
  if (!isRecord(value) || typeof value.status !== "string") {
    return authenticated ? { status: "failed" } : { status: "not_requested" };
  }

  if (value.status === "not_requested") {
    return { status: "not_requested" };
  }

  if (value.status === "saved" || value.status === "already_saved") {
    if (
      typeof value.conversation_id === "string" &&
      typeof value.user_message_id === "string" &&
      typeof value.assistant_message_id === "string"
    ) {
      return {
        status: value.status,
        conversation_id: value.conversation_id,
        user_message_id: value.user_message_id,
        assistant_message_id: value.assistant_message_id,
      };
    }
    return {
      status: "failed",
      conversation_id:
        typeof value.conversation_id === "string"
          ? value.conversation_id
          : undefined,
    };
  }

  if (
    value.status === "not_saved_support" ||
    value.status === "not_saved_fallback"
  ) {
    return {
      status: value.status,
      conversation_id:
        typeof value.conversation_id === "string"
          ? value.conversation_id
          : undefined,
    };
  }

  return {
    status: "failed",
    conversation_id:
      typeof value.conversation_id === "string"
        ? value.conversation_id
        : undefined,
  };
}

function normalizeResponseSource(
  value: unknown,
  supportMode: SupportMode,
): ResponseSource {
  if (
    value === "review" ||
    value === "safety_guard" ||
    value === "review_safety_envelope" ||
    value === "safe_fallback"
  ) {
    return value;
  }

  return supportMode === "support" ? "safety_guard" : "review";
}

export async function sendReflection(
  message: string,
  options: SendReflectionOptions,
): Promise<ChatResponse> {
  const supabase = createClient();
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError) {
    throw new Error("暂时无法确认登录状态，请稍后再试。");
  }

  const accessToken = session?.access_token;
  if (options.conversationId && !accessToken) {
    throw new Error("登录状态已经失效。请重新登录后继续这段探索。");
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${apiUrl}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      message,
      conversation_id: options.conversationId ?? undefined,
      client_turn_id: options.clientTurnId,
    }),
    signal: options.signal,
  });

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new Error("登录状态已经失效。请重新登录后继续探索。");
    }
    if (response.status === 404) {
      throw new Error("这段探索不存在，或你没有访问权限。");
    }
    if (response.status === 409) {
      throw new Error("这次重试与原来的表达不一致，请作为一条新表达发送。");
    }
    if (response.status === 503) {
      throw new Error("PAS 的 AI 与安全审核当前不可用，请稍后再试。");
    }
    throw new Error("PAS 暂时无法回应，请稍后再试。");
  }

  const result = (await response.json()) as unknown;
  if (!isRecord(result) || typeof result.response !== "string") {
    throw new Error("PAS 返回了无法识别的回应，请稍后再试。");
  }

  const supportMode: SupportMode =
    result.support_mode === "support" ? "support" : "reflection";

  return {
    response: result.response,
    mode: typeof result.mode === "string" ? result.mode : "safety-guard",
    support_mode: supportMode,
    response_source: normalizeResponseSource(result.response_source, supportMode),
    persistence: normalizePersistence(result.persistence, Boolean(accessToken)),
    memory_candidate: isRecord(result.memory_candidate)
      ? (result.memory_candidate as MemoryCandidate)
      : undefined,
  };
}
