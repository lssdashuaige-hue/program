import Link from "next/link";
import { EmailSignInForm } from "@/components/email-sign-in-form";

type Props = {
  searchParams: Promise<{ error?: string; next?: string }>;
};

function safeNextPath(value: string | undefined): string {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/explore";
}

export default async function AuthPage({ searchParams }: Props) {
  const params = await searchParams;
  const nextPath = safeNextPath(params.next);

  return (
    <main className="min-h-screen px-5 py-12 sm:px-8">
      <div className="mx-auto max-w-md">
        <Link className="text-sm font-semibold tracking-[0.18em]" href="/">
          PAS
        </Link>
        <section className="mt-16 rounded-[2rem] border border-[var(--line)] bg-[var(--surface)] p-7 shadow-[0_24px_80px_rgba(36,54,52,0.08)] sm:p-9">
          <p className="text-xs font-medium tracking-[0.18em] text-[var(--muted)] uppercase">
            Private reflection space
          </p>
          <h1 className="mt-4 text-3xl font-medium tracking-[-0.04em]">
            登录你的探索空间
          </h1>
          <p className="mt-4 leading-7 text-[var(--muted)]">
            PAS 使用一次性邮箱链接登录。只有登录后，你主动确认的候选记忆才会保存。
          </p>
          {params.error && (
            <p className="mt-5 text-sm leading-6 text-[#9f3a38]">
              登录链接无效或已经过期，请重新发送。
            </p>
          )}
          <EmailSignInForm nextPath={nextPath} />
        </section>
      </div>
    </main>
  );
}
