"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export function AuthStatus() {
  const [signedIn, setSignedIn] = useState(false);
  const [ready, setReady] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const signOutRequestedRef = useRef(false);
  const pathname = usePathname();

  useEffect(() => {
    const supabase = createClient();
    let active = true;

    void supabase.auth
      .getUser()
      .then(({ data }) => {
        if (active) setSignedIn(Boolean(data.user));
      })
      .catch(() => {
        if (active) setSignedIn(false);
      })
      .finally(() => {
        if (active) setReady(true);
      });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      setSignedIn(Boolean(session?.user));
      setReady(true);

      if (event === "SIGNED_OUT" && !signOutRequestedRef.current) {
        window.location.replace("/");
      }
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  async function handleSignOut() {
    if (signingOut) return;

    setSigningOut(true);
    signOutRequestedRef.current = true;

    let destination = "/";

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signOut({ scope: "local" });

      if (error) {
        destination = "/auth?logout=partial";
      }
    } catch {
      destination = "/auth?logout=partial";
    }

    // A full navigation clears the rendered private page and replaces its
    // history entry, instead of leaving sensitive client state mounted.
    window.location.replace(destination);
  }

  if (!ready) {
    return (
      <span
        aria-live="polite"
        className="text-xs text-[var(--muted)]"
        role="status"
      >
        正在确认登录状态…
      </span>
    );
  }

  if (!signedIn) {
    const nextPath = pathname?.startsWith("/") ? pathname : "/explore";

    return (
      <Link
        className="rounded-full border border-[var(--line)] px-3 py-1.5 text-xs text-[var(--muted)] hover:text-[var(--ink)]"
        href={`/auth?next=${encodeURIComponent(nextPath)}`}
      >
        登录
      </Link>
    );
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Link
        className="hidden rounded-full border border-[#b9c8bd] bg-[#f3f5ef] px-3 py-1.5 text-xs text-[#52705f] sm:inline-flex"
        href="/history"
      >
        我的空间
      </Link>
      <button
        aria-busy={signingOut}
        aria-label={
          signingOut ? "正在退出当前 PAS 登录会话" : "退出当前 PAS 登录会话"
        }
        className="button-quiet px-3 text-xs"
        disabled={signingOut}
        onClick={handleSignOut}
        type="button"
      >
        {signingOut ? (
          "正在退出…"
        ) : (
          <>
            <span className="sm:hidden">退出</span>
            <span className="hidden sm:inline">退出登录</span>
          </>
        )}
      </button>
    </div>
  );
}
