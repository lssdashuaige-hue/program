export type MemoryCandidate = {
  kind: "experience" | "reflection" | "pattern" | "need";
  content: string;
  confidence: "low" | "medium";
  confirmation_prompt: string;
};

export type SupportMode = "reflection" | "support";

export type ChatResponse = {
  response: string;
  mode: string;
  support_mode: SupportMode;
  memory_candidate?: MemoryCandidate;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function sendReflection(
  message: string,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await fetch(`${apiUrl}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });

  if (!response.ok) {
    if (response.status === 503) {
      throw new Error("PAS 的 AI 与安全审核当前不可用，请稍后再试。");
    }
    throw new Error("PAS 暂时无法回应，请稍后再试。");
  }

  const result = (await response.json()) as ChatResponse;

  return {
    ...result,
    support_mode: result.support_mode === "support" ? "support" : "reflection",
  };
}
