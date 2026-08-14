import "server-only";

import type {
  ConversationMessage,
  ConversationStatus,
  ConversationSummary,
} from "@/lib/conversation-types";
import { createClient } from "@/lib/supabase/server";

const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export class ConversationsApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null = null,
  ) {
    super(message);
    this.name = "ConversationsApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseConversation(value: unknown): ConversationSummary | null {
  if (!isRecord(value)) return null;

  const status: ConversationStatus | null =
    value.status === "active" || value.status === "archived"
      ? value.status
      : null;

  if (
    typeof value.id !== "string" ||
    !(typeof value.title === "string" || value.title === null) ||
    !status ||
    typeof value.created_at !== "string" ||
    typeof value.updated_at !== "string"
  ) {
    return null;
  }

  return {
    id: value.id,
    title: value.title,
    status,
    created_at: value.created_at,
    updated_at: value.updated_at,
  };
}

function parseMessage(value: unknown): ConversationMessage | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.id !== "string" ||
    (value.role !== "user" && value.role !== "assistant") ||
    typeof value.content !== "string" ||
    typeof value.created_at !== "string"
  ) {
    return null;
  }

  return {
    id: value.id,
    role: value.role,
    content: value.content,
    created_at: value.created_at,
  };
}

async function authenticatedFetch(
  path: string,
  accessToken: string,
): Promise<unknown> {
  let response: Response;

  try {
    response = await fetch(`${apiUrl}${path}`, {
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });
  } catch {
    throw new ConversationsApiError("PAS 暂时无法连接到探索历史服务。");
  }

  if (!response.ok) {
    throw new ConversationsApiError(
      response.status === 404
        ? "这段探索不存在，或你没有访问权限。"
        : "PAS 暂时无法读取探索历史。",
      response.status,
    );
  }

  try {
    return (await response.json()) as unknown;
  } catch {
    throw new ConversationsApiError("探索历史服务返回了无法识别的数据。");
  }
}

export async function getVerifiedAccessToken(): Promise<string | null> {
  const supabase = await createClient();
  const { data: claimsData, error: claimsError } =
    await supabase.auth.getClaims();

  if (claimsError || !claimsData?.claims?.sub) {
    return null;
  }

  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError || !session?.access_token) {
    return null;
  }

  return session.access_token;
}

export async function getConversations(
  accessToken: string,
  options: { limit?: number; offset?: number } = {},
): Promise<ConversationSummary[]> {
  const limit = Math.min(Math.max(options.limit ?? 30, 1), 100);
  const offset = Math.max(options.offset ?? 0, 0);
  const payload = await authenticatedFetch(
    `/conversations?limit=${limit}&offset=${offset}`,
    accessToken,
  );

  if (!isRecord(payload) || !Array.isArray(payload.items)) {
    throw new ConversationsApiError("探索历史服务返回了无法识别的数据。");
  }

  const conversations = payload.items.map(parseConversation);
  if (conversations.some((item) => item === null)) {
    throw new ConversationsApiError("探索历史服务返回了无法识别的数据。");
  }

  return conversations as ConversationSummary[];
}

export async function getConversation(
  accessToken: string,
  conversationId: string,
): Promise<ConversationSummary> {
  const payload = await authenticatedFetch(
    `/conversations/${encodeURIComponent(conversationId)}`,
    accessToken,
  );
  const conversation = parseConversation(payload);

  if (!conversation) {
    throw new ConversationsApiError("探索历史服务返回了无法识别的数据。");
  }

  return conversation;
}

export async function getConversationMessages(
  accessToken: string,
  conversationId: string,
): Promise<ConversationMessage[]> {
  const payload = await authenticatedFetch(
    `/conversations/${encodeURIComponent(conversationId)}/messages`,
    accessToken,
  );

  if (!isRecord(payload) || !Array.isArray(payload.items)) {
    throw new ConversationsApiError("探索历史服务返回了无法识别的数据。");
  }

  const messages = payload.items.map(parseMessage);
  if (messages.some((item) => item === null)) {
    throw new ConversationsApiError("探索历史服务返回了无法识别的数据。");
  }

  return messages as ConversationMessage[];
}
