import type { MemoryCandidate } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

export type SaveMemoryResult =
  | { status: "saved" }
  | { status: "signed_out" }
  | { status: "error"; message: string };

export async function saveConfirmedMemory(
  candidate: MemoryCandidate,
): Promise<SaveMemoryResult> {
  const supabase = createClient();
  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError) {
    return { status: "error", message: "暂时无法确认登录状态，请稍后重试。" };
  }

  if (!user) {
    return { status: "signed_out" };
  }

  const { error } = await supabase.from("memories").insert({
    user_id: user.id,
    kind: candidate.kind,
    content: candidate.content,
    confidence: candidate.confidence,
    confirmed: true,
    source_message_id: candidate.source_message_id ?? null,
  });

  if (error) {
    return { status: "error", message: "这条记忆暂时没有保存，请稍后重试。" };
  }

  return { status: "saved" };
}
