import type { Metadata } from "next";
import Link from "next/link";
import { EmailSignInForm } from "@/components/email-sign-in-form";
import { OpenRingMark } from "@/components/open-ring-mark";
import { SiteHeader } from "@/components/site-header";
import { safeNextPath } from "@/lib/safe-next-path";

export const metadata: Metadata = {
  title: "登录探索空间",
  description: "使用一次性邮箱链接登录 PAS，保存符合安全规则的探索并继续自己的主题。",
};

type Props = {
  searchParams: Promise<{ error?: string; next?: string }>;
};

export default async function AuthPage({ searchParams }: Props) {
  const params = await searchParams;
  const nextPath = safeNextPath(params.next);

  return (
    <div className="min-h-screen">
      <SiteHeader active="auth" variant="public" />
      <main
        className="mx-auto grid min-h-[calc(100vh-4.5rem)] w-full max-w-6xl items-center gap-10 px-5 py-14 sm:px-8 lg:grid-cols-[0.88fr_1.12fr] lg:py-20"
        id="main-content"
      >
        <section className="max-w-lg">
          <OpenRingMark className="mb-8" />
          <p className="eyebrow">Private reflection space</p>
          <h1 className="mt-5 text-4xl leading-tight font-medium tracking-[-0.045em] sm:text-5xl">
            登录你的探索空间
          </h1>
          <p className="mt-5 text-base leading-8 text-[var(--muted)] sm:text-lg">
            登录不是开始探索的前提。当你希望保存并继续一段探索，或保留自己确认过的候选记忆时，再进入私密空间。
          </p>
          <ul className="mt-8 space-y-4 text-sm leading-7 text-[var(--muted)]">
            <li className="flex gap-3">
              <span aria-hidden="true" className="mt-2 h-2 w-2 shrink-0 rounded-full bg-[var(--sage-deep)]" />
              使用一次性邮箱链接，不需要设置密码。
            </li>
            <li className="flex gap-3">
              <span aria-hidden="true" className="mt-2 h-2 w-2 shrink-0 rounded-full bg-[var(--sage-deep)]" />
              符合安全保存规则且成功写入的探索会进入历史；候选记忆仍需你逐条明确确认。
            </li>
          </ul>
        </section>

        <section className="quiet-card bg-[var(--surface)] p-7 sm:p-9">
          <h2 className="text-2xl font-medium tracking-[-0.035em]">
            获取一次性登录链接
          </h2>
          <p className="mt-3 leading-7 text-[var(--muted)]">
            输入邮箱后，我们会发送一封一次性登录邮件。
          </p>
          {params.error && (
            <p
              className="mt-5 rounded-2xl border border-[#c9a9a2] bg-[#f6ece8] px-4 py-3 text-sm leading-6 text-[var(--clay)]"
              role="alert"
            >
              登录链接无效或已经过期，请重新发送。
            </p>
          )}
          <EmailSignInForm nextPath={nextPath} />
          <p className="mt-7 border-t border-[var(--line)] pt-5 text-xs leading-6 text-[var(--muted)]">
            继续即表示你理解当前 Alpha 的数据边界。你可以先查看
            <Link
              className="mx-1 font-semibold underline underline-offset-4"
              href="/settings/privacy"
            >
              记忆与隐私说明
            </Link>
            。
          </p>
        </section>
      </main>
    </div>
  );
}
