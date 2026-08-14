import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { PageIntro } from "@/components/page-intro";
import {
  ConversationsApiError,
  getConversations,
  getVerifiedAccessToken,
} from "@/lib/conversations";

export const metadata: Metadata = {
  title: "探索历史",
  description: "按主题回看自己的探索，并在原来的上下文中继续。",
};

const historyLayers = [
  {
    title: "你的原话",
    description: "保留当时的表达，不把系统转述伪装成你的结论。",
  },
  {
    title: "PAS 的已审核回应",
    description: "只显示 PAS 完成审核并成功写入的最终回应，不保存内部草稿。",
  },
  {
    title: "继续探索",
    description: "从原来的主题和上下文继续，而不是重新猜测你说过什么。",
  },
];

const PAGE_SIZE = 30;

type Props = {
  searchParams: Promise<{ page?: string | string[] }>;
};

function pageFromSearchParam(value: string | string[] | undefined): number {
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = Number.parseInt(raw ?? "1", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeZone: "Asia/Shanghai",
});

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未知" : dateFormatter.format(date);
}

export default async function HistoryPage({ searchParams }: Props) {
  const page = pageFromSearchParam((await searchParams).page);
  const accessToken = await getVerifiedAccessToken();
  if (!accessToken) {
    redirect("/auth?next=/history");
  }

  let conversations = null;
  let hasNextPage = false;
  let loadError: string | null = null;

  try {
    const loaded = await getConversations(accessToken, {
      limit: PAGE_SIZE + 1,
      offset: (page - 1) * PAGE_SIZE,
    });
    hasNextPage = loaded.length > PAGE_SIZE;
    conversations = loaded.slice(0, PAGE_SIZE);
  } catch (error) {
    if (error instanceof ConversationsApiError && error.status === 401) {
      redirect("/auth?next=/history");
    }
    loadError =
      error instanceof ConversationsApiError
        ? error.message
        : "PAS 暂时无法读取探索历史。";
  }

  return (
    <AppShell active="history">
      <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
        <PageIntro
          description="每段历史保留你的原话和 PAS 完成审核后成功写入的回应，让你可以在原来的主题中继续。"
          eyebrow="Exploration history"
          note={
            conversations
              ? `第 ${page} 页 · ${conversations.length} 段探索`
              : "读取状态"
          }
          title="把变化放回主题里看"
        />

        <div className="mt-10">
          {loadError ? (
            <EmptyState
              actionHref="/history"
              actionLabel="重新读取"
              description={`${loadError} 这不是“没有历史”的提示，你已经保存的内容不会因此被隐藏或改写。`}
              title="暂时无法读取探索历史"
            />
          ) : conversations?.length ? (
            <div>
              <ul className="grid gap-4 md:grid-cols-2">
                {conversations.map((conversation) => {
                  const title = conversation.title?.trim() || "未命名探索";
                  return (
                    <li
                      className="quiet-card flex flex-col p-6 sm:p-7"
                      key={conversation.id}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <span className="status-chip">
                          {conversation.status === "archived"
                            ? "已归档"
                            : "正在探索"}
                        </span>
                        <time
                          className="text-xs text-[var(--muted)]"
                          dateTime={conversation.updated_at}
                        >
                          更新于 {formatDate(conversation.updated_at)}
                        </time>
                      </div>
                      <h2 className="mt-5 text-xl font-medium tracking-[-0.025em]">
                        {title}
                      </h2>
                      <p className="mt-3 flex-1 text-sm leading-7 text-[var(--muted)]">
                        回到这段探索，查看原来的表达，并从已有上下文继续。
                      </p>
                      <Link
                        className="button-secondary mt-6 w-fit"
                        href={`/explore/${conversation.id}`}
                      >
                        继续这段探索
                      </Link>
                    </li>
                  );
                })}
              </ul>
              {(page > 1 || hasNextPage) && (
                <nav
                  aria-label="探索历史分页"
                  className="mt-8 flex items-center justify-between gap-4"
                >
                  {page > 1 ? (
                    <Link className="button-secondary" href={`/history?page=${page - 1}`}>
                      上一页
                    </Link>
                  ) : (
                    <span />
                  )}
                  {hasNextPage && (
                    <Link className="button-secondary" href={`/history?page=${page + 1}`}>
                      下一页
                    </Link>
                  )}
                </nav>
              )}
            </div>
          ) : (
            <EmptyState
              actionHref="/explore"
              actionLabel="开始一次探索"
              description="登录后，符合安全保存规则且成功写入的探索会出现在这里。内部草稿与审查理由不会进入历史。"
              title="这里还没有已保存的探索"
            />
          )}
        </div>

        <section aria-labelledby="history-structure" className="mt-14">
          <div className="max-w-2xl">
            <p className="eyebrow">历史如何保存</p>
            <h2
              className="mt-4 text-2xl font-medium tracking-[-0.035em] sm:text-3xl"
              id="history-structure"
            >
              三种内容会保持清楚区分
            </h2>
          </div>
          <ul className="mt-7 grid gap-4 md:grid-cols-3">
            {historyLayers.map((layer) => (
              <li className="quiet-card p-6" key={layer.title}>
                <h3 className="text-lg font-medium">{layer.title}</h3>
                <p className="mt-3 text-sm leading-7 text-[var(--muted)]">
                  {layer.description}
                </p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </AppShell>
  );
}
