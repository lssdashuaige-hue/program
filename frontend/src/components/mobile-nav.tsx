import Link from "next/link";
import type { AppSection } from "@/components/site-header";

type MobileNavProps = {
  active: AppSection;
};

const links: Array<{ href: string; label: string; section: AppSection }> = [
  { href: "/explore", label: "探索", section: "explore" },
  { href: "/history", label: "历史", section: "history" },
  { href: "/map", label: "地图", section: "map" },
  { href: "/settings/privacy", label: "设置", section: "privacy" },
];

export function MobileNav({ active }: MobileNavProps) {
  return (
    <nav
      aria-label="应用移动导航"
      className="fixed inset-x-3 bottom-3 z-50 grid grid-cols-4 rounded-[1.4rem] border border-[var(--line)] bg-[rgba(255,253,248,0.94)] p-1.5 shadow-[0_18px_50px_rgba(36,54,52,0.18)] backdrop-blur-xl md:hidden"
    >
      {links.map((link) => {
        const isCurrent = active === link.section;
        return (
          <Link
            aria-current={isCurrent ? "page" : undefined}
            className={
              isCurrent
                ? "flex min-h-12 flex-col items-center justify-center gap-1 rounded-2xl bg-[var(--sage-soft)] px-2 text-xs font-semibold text-[var(--ink)]"
                : "flex min-h-12 flex-col items-center justify-center gap-1 rounded-2xl px-2 text-xs text-[var(--muted)]"
            }
            href={link.href}
            key={link.href}
          >
            <span
              aria-hidden="true"
              className={
                isCurrent
                  ? "h-1 w-5 rounded-full bg-[var(--sage-deep)]"
                  : "h-1 w-1 rounded-full bg-[var(--line-strong)]"
              }
            />
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
