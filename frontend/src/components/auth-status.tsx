"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export function AuthStatus() {
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const supabase = createClient();

    void supabase.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? null);
      setReady(true);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user.email ?? null);
      setReady(true);
    });

    return () => subscription.unsubscribe();
  }, []);

  if (!ready) {
    return (
      <span className="text-xs text-[var(--muted)]">正在确认登录状态…</span>
    );
  }

  if (!email) {
    return (
      <Link
        className="rounded-full border border-[var(--line)] px-3 py-1.5 text-xs text-[var(--muted)] hover:text-[var(--ink)]"
        href="/auth?next=/explore"
      >
        登录后可保存确认内容
      </Link>
    );
  }

  return (
    <span className="max-w-52 truncate rounded-full border border-[#b9c8bd] bg-[#f3f5ef] px-3 py-1.5 text-xs text-[#52705f]">
      已登录 · {email}
    </span>
  );
}
