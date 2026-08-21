import type { MemoryCandidate } from "@/lib/api";
import {
  confirmMemoryCandidate,
  DataControlApiError,
} from "@/lib/data-control";

export type SaveMemoryResult =
  | { status: "saved" }
  | { status: "signed_out" }
  | { status: "error"; message: string };

export async function saveConfirmedMemory(
  candidate: MemoryCandidate,
): Promise<SaveMemoryResult> {
  try {
    await confirmMemoryCandidate(candidate);
  } catch (error) {
    if (error instanceof DataControlApiError && error.status === 401) {
      return { status: "signed_out" };
    }
    return {
      status: "error",
      message:
        error instanceof DataControlApiError
          ? error.message
          : "这条记忆暂时没有保存，请稍后重试。",
    };
  }

  return { status: "saved" };
}
