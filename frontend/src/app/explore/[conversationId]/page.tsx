import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { ReflectionRoom } from "@/components/reflection-room";
import {
  ConversationsApiError,
  getConversation,
  getConversationMessages,
  getVerifiedAccessToken,
} from "@/lib/conversations";

export const metadata: Metadata = {
  title: "继续探索",
  description: "回到一段已保存的探索，并从原来的上下文继续。",
};

type Props = {
  params: Promise<{ conversationId: string }>;
};

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default async function SavedExplorationPage({ params }: Props) {
  const { conversationId } = await params;
  if (!uuidPattern.test(conversationId)) {
    notFound();
  }

  const nextPath = `/explore/${conversationId}`;
  const accessToken = await getVerifiedAccessToken();
  if (!accessToken) {
    redirect(`/auth?next=${encodeURIComponent(nextPath)}`);
  }

  let exploration = null;

  try {
    const [conversation, messages] = await Promise.all([
      getConversation(accessToken, conversationId),
      getConversationMessages(accessToken, conversationId),
    ]);
    exploration = { conversation, messages };
  } catch (error) {
    if (error instanceof ConversationsApiError) {
      if (error.status === 401) {
        redirect(`/auth?next=${encodeURIComponent(nextPath)}`);
      }
      if (error.status === 404) {
        notFound();
      }
    }

  }

  if (!exploration) {
    return (
      <AppShell active="explore">
        <div className="mx-auto w-full max-w-4xl px-5 py-12 sm:px-8">
          <EmptyState
            actionHref="/history"
            actionLabel="返回探索历史"
            description="PAS 暂时无法读取这段探索。这不是空白会话；我们不会在缺少原始上下文时假装已经恢复。"
            title="暂时无法恢复这段探索"
          />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell active="explore">
      <ReflectionRoom
        initialConversation={{
          id: exploration.conversation.id,
          title: exploration.conversation.title,
        }}
        initialMessages={exploration.messages}
      />
    </AppShell>
  );
}
