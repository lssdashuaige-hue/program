import type { ReactNode } from "react";
import { MobileNav } from "@/components/mobile-nav";
import { SiteHeader, type AppSection } from "@/components/site-header";

type AppShellProps = {
  active: AppSection;
  children: ReactNode;
};

export function AppShell({ active, children }: AppShellProps) {
  return (
    <div className="min-h-screen pb-24 md:pb-0">
      <SiteHeader active={active} variant="app" />
      <main id="main-content">{children}</main>
      <footer className="mx-auto mt-16 flex w-full max-w-6xl flex-col gap-3 border-t border-[var(--line)] px-5 py-8 text-xs leading-6 text-[var(--muted)] sm:px-8 md:flex-row md:items-center md:justify-between">
        <p>PAS 不做心理诊断，也不替你决定人生。</p>
        <p>理解自己，活得更自由。</p>
      </footer>
      <MobileNav active={active} />
    </div>
  );
}
