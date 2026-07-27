"use client";

import { FormEvent, useState } from "react";
import { createClient } from "@/lib/supabase/client";

type Props = {
  nextPath: string;
};

export function EmailSignInForm({ nextPath }: Props) {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = email.trim();
    if (!normalizedEmail || pending) return;

    setPending(true);
    setNotice(null);
    setError(null);

    try {
      const supabase = createClient();
      const callbackUrl = new URL("/auth/callback", window.location.origin);
      callbackUrl.searchParams.set("next", nextPath);

      const { error: signInError } = await supabase.auth.signInWithOtp({
        email: normalizedEmail,
        options: {
          emailRedirectTo: callbackUrl.toString(),
        },
      });

      if (signInError) {
        setError("登录邮件暂时无法发送，请稍后重试。");
      } else {
        setNotice("登录链接已经发送到你的邮箱。链接为一次性使用。");
      }
    } catch {
      setError("登录邮件暂时无法发送，请稍后重试。");
    }

    setPending(false);
  }

  return (
    <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
      <div>
        <label className="text-sm font-medium" htmlFor="email">
          邮箱
        </label>
        <input
          autoComplete="email"
          className="mt-2 w-full rounded-2xl border border-[var(--line)] bg-white px-4 py-3 outline-none focus:border-[#7f9a89]"
          id="email"
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          required
          type="email"
          value={email}
        />
      </div>
      <button
        className="w-full rounded-full bg-[var(--ink)] px-5 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
        disabled={pending || !email.trim()}
        type="submit"
      >
        {pending ? "正在发送…" : "发送一次性登录链接"}
      </button>
      {notice && <p className="text-sm leading-6 text-[#52705f]">{notice}</p>}
      {error && <p className="text-sm leading-6 text-[#9f3a38]">{error}</p>}
    </form>
  );
}
