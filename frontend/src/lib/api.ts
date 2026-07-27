export type MemoryCandidate = {
  kind: "experience" | "reflection" | "pattern" | "need";
  content: string;
  confidence: "low" | "medium";
  confirmation_prompt: string;
};

export type ChatResponse = {
  response: string;
  mode: string;
  memory_candidate?: MemoryCandidate;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function sendReflection(message: string): Promise<ChatResponse> {
  const response = await fetch(`${apiUrl}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    throw new Error("PAS 暂时无法回应，请稍后再试。");
  }

  return response.json() as Promise<ChatResponse>;
}
