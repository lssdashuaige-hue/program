export type ConversationStatus = "active" | "archived";

export type ConversationSummary = {
  id: string;
  title: string | null;
  status: ConversationStatus;
  created_at: string;
  updated_at: string;
};

export type ConversationMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};
