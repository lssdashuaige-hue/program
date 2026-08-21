import "client-only";

import type { MemoryCandidate } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export type MemoryStatus = "active" | "paused" | "superseded";

export type SavedMemory = {
  id: string;
  lineage_id: string;
  source_message_id: string | null;
  supersedes_id: string | null;
  kind: MemoryCandidate["kind"];
  content: string;
  original_content: string;
  confidence: MemoryCandidate["confidence"];
  confirmed: true;
  status: MemoryStatus;
  version: number;
  version_origin: "source_quote" | "user_revision";
  confirmed_at: string;
  paused_at: string | null;
  superseded_at: string | null;
  created_at: string;
  updated_at: string;
};

export type DataControlState = {
  memory_enabled: boolean;
  memory_enabled_at: string | null;
  memory_feature_available: boolean;
  temporary_sessions_supported: true;
  stored_memories_used_as_model_context: false;
  memories: SavedMemory[];
};

export class DataControlApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null = null,
  ) {
    super(message);
    this.name = "DataControlApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function parseMemory(value: unknown): SavedMemory | null {
  if (!isRecord(value)) return null;
  const kind = value.kind;
  const confidence = value.confidence;
  const status = value.status;
  const versionOrigin = value.version_origin;
  if (
    typeof value.id !== "string" ||
    typeof value.lineage_id !== "string" ||
    !isNullableString(value.source_message_id) ||
    !isNullableString(value.supersedes_id) ||
    (kind !== "experience" &&
      kind !== "reflection" &&
      kind !== "pattern" &&
      kind !== "need") ||
    typeof value.content !== "string" ||
    typeof value.original_content !== "string" ||
    (confidence !== "low" && confidence !== "medium") ||
    value.confirmed !== true ||
    (status !== "active" && status !== "paused" && status !== "superseded") ||
    !Number.isInteger(value.version) ||
    (value.version as number) < 1 ||
    (versionOrigin !== "source_quote" && versionOrigin !== "user_revision") ||
    typeof value.confirmed_at !== "string" ||
    !isNullableString(value.paused_at) ||
    !isNullableString(value.superseded_at) ||
    typeof value.created_at !== "string" ||
    typeof value.updated_at !== "string"
  ) {
    return null;
  }
  return {
    id: value.id,
    lineage_id: value.lineage_id,
    source_message_id: value.source_message_id,
    supersedes_id: value.supersedes_id,
    kind,
    content: value.content,
    original_content: value.original_content,
    confidence,
    confirmed: true,
    status,
    version: value.version as number,
    version_origin: versionOrigin,
    confirmed_at: value.confirmed_at,
    paused_at: value.paused_at,
    superseded_at: value.superseded_at,
    created_at: value.created_at,
    updated_at: value.updated_at,
  };
}

async function getAccessToken(): Promise<string> {
  const supabase = createClient();
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession();
  if (error || !session?.access_token) {
    throw new DataControlApiError("请先登录后再管理你的数据。", 401);
  }
  return session.access_token;
}

async function dataControlFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const accessToken = await getAccessToken();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
        Authorization: `Bearer ${accessToken}`,
      },
    });
  } catch {
    throw new DataControlApiError("PAS 暂时无法连接到数据控制服务。");
  }
  if (!response.ok) {
    const message =
      response.status === 401
        ? "登录状态已经失效，请重新登录。"
        : response.status === 404
          ? "没有找到这条属于你的记录。"
          : response.status === 409
            ? "数据已经变化或当前设置不允许这项操作，请刷新后重试。"
            : "PAS 暂时无法完成这项数据控制操作。";
    throw new DataControlApiError(message, response.status);
  }
  return response;
}

async function parseMemoryResponse(response: Response): Promise<SavedMemory> {
  const memory = parseMemory((await response.json()) as unknown);
  if (!memory) {
    throw new DataControlApiError("PAS 返回了无法识别的记忆记录。");
  }
  return memory;
}

export async function loadDataControlState(): Promise<DataControlState> {
  const response = await dataControlFetch("/data-control");
  const value = (await response.json()) as unknown;
  if (
    !isRecord(value) ||
    typeof value.memory_enabled !== "boolean" ||
    !isNullableString(value.memory_enabled_at) ||
    typeof value.memory_feature_available !== "boolean" ||
    value.temporary_sessions_supported !== true ||
    value.stored_memories_used_as_model_context !== false ||
    !Array.isArray(value.memories)
  ) {
    throw new DataControlApiError("PAS 返回了无法识别的数据控制状态。");
  }
  const memories = value.memories.map(parseMemory);
  if (memories.some((memory) => memory === null)) {
    throw new DataControlApiError("PAS 返回了无法识别的记忆记录。");
  }
  return {
    memory_enabled: value.memory_enabled,
    memory_enabled_at: value.memory_enabled_at,
    memory_feature_available: value.memory_feature_available,
    temporary_sessions_supported: true,
    stored_memories_used_as_model_context: false,
    memories: memories as SavedMemory[],
  };
}

export async function updateMemoryEnabled(
  enabled: boolean,
): Promise<{ memory_enabled: boolean; memory_enabled_at: string | null }> {
  const response = await dataControlFetch("/data-control/memory", {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
  const value = (await response.json()) as unknown;
  if (
    !isRecord(value) ||
    value.memory_enabled !== enabled ||
    !isNullableString(value.memory_enabled_at)
  ) {
    throw new DataControlApiError("PAS 没有确认这次记忆设置变更。");
  }
  return {
    memory_enabled: enabled,
    memory_enabled_at: value.memory_enabled_at,
  };
}

export async function confirmMemoryCandidate(
  candidate: MemoryCandidate,
): Promise<SavedMemory> {
  if (!candidate.source_message_id) {
    throw new DataControlApiError("缺少这条候选记忆的原始消息来源。");
  }
  const response = await dataControlFetch("/data-control/memories", {
    method: "POST",
    body: JSON.stringify({
      source_message_id: candidate.source_message_id,
      kind: candidate.kind,
      content: candidate.content,
      confidence: candidate.confidence,
    }),
  });
  return parseMemoryResponse(response);
}

export async function reviseMemory(
  memoryId: string,
  expectedVersion: number,
  content: string,
): Promise<SavedMemory> {
  const response = await dataControlFetch(
    `/data-control/memories/${encodeURIComponent(memoryId)}/revisions`,
    {
      method: "POST",
      body: JSON.stringify({ expected_version: expectedVersion, content }),
    },
  );
  return parseMemoryResponse(response);
}

export async function updateMemoryStatus(
  memoryId: string,
  status: "active" | "paused",
): Promise<SavedMemory> {
  const response = await dataControlFetch(
    `/data-control/memories/${encodeURIComponent(memoryId)}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({ status }),
    },
  );
  return parseMemoryResponse(response);
}

export async function deleteMemoryLineage(lineageId: string): Promise<void> {
  await dataControlFetch(
    `/data-control/memories/${encodeURIComponent(lineageId)}`,
    { method: "DELETE" },
  );
}

export async function downloadDataExport(): Promise<void> {
  const response = await dataControlFetch("/data-control/export");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = `pas-data-export-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function permanentlyDeleteAccount(): Promise<void> {
  await dataControlFetch("/data-control/account", {
    method: "DELETE",
    body: JSON.stringify({ confirmation: "删除我的 PAS 账户" }),
  });
}
