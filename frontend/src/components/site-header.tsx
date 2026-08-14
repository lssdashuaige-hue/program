import Link from "next/link";
import { OpenRingMark } from "@/components/open-ring-mark";

export type AppSection = "explore" | "history" | "map" | "privacy";
type PublicSection = "home" | "auth" | "safety";

type SiteHeaderProps =
  | { variant: "app"; active: AppSection }
  | { variant: "public"; active?: PublicSection };

const appLinks: Array<{ href: string; label: string; section: AppSection }> = [
  { href: "/explore", label: "探索", section: "explore" },
  { href: "/history", label: "历史", section: "history" },
  { href: "/map", label: "心理地图", section: "map" },
  { href: "/settings/privacy", label: "记忆与隐私", section: "privacy" },
];

function Brand() {
  return (
    <Link
      aria-label="PAS 首页"
      className="flex min-h-11 items-center gap-3 rounded-full pr-2"
      href="/"
    >
      <OpenRingMark />
      <span aria-hidden="true" className="flex items-baseline gap-3">
        <span className="text-sm font-semibold tracking-[0.22em]">PAS</span>
        <span className="hidden text-xs text-[var(--muted)] sm:inline">
          个人反思空间
        </span>
      </span>
    </Link>
  );
}

export function SiteHeader(props: SiteHeaderProps) {
  return (
    <header className="sticky top-0 z-50 border-b border-[rgba(212,217,209,0.78)] bg-[rgba(245,242,235,0.9)] backdrop-blur-xl">
      <div className="mx-auto flex min-h-18 w-full max-w-6xl items-center justify-between gap-4 px-5 sm:px-8">
        <Brand />

        {props.variant === "app" ? (
          <>
            <nav
              aria-label="应用主要导航"
              className="hidden items-center gap-1 md:flex"
            >
              {appLinks.map((link) => {
                const isCurrent = props.active === link.section;
                return (
                  <Link
                    aria-current={isCurrent ? "page" : undefined}
                    className={
                      isCurrent
                        ? "flex min-h-11 items-center rounded-full bg-[var(--sage-soft)] px-4 text-sm font-semibold text-[var(--ink)]"
                        : "flex min-h-11 items-center rounded-full px-4 text-sm text-[var(--muted)] hover:bg-[rgba(223,232,224,0.55)] hover:text-[var(--ink)]"
                    }
                    href={link.href}
                    key={link.href}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </nav>
            <Link
              className="button-quiet px-3"
              href="/help/safety"
            >
              安全与边界
            </Link>
          </>
        ) : (
          <>
            <nav
              aria-label="网站主要导航"
              className="hidden items-center gap-1 md:flex"
            >
              <Link className="button-quiet" href="/#how-it-works">
                如何运作
              </Link>
              <Link
                aria-current={props.active === "safety" ? "page" : undefined}
                className="button-quiet"
                href="/help/safety"
              >
                安全与边界
              </Link>
              <Link
                aria-current={props.active === "auth" ? "page" : undefined}
                className="button-quiet"
                href="/auth"
              >
                登录
              </Link>
              <Link className="button-primary ml-1" href="/explore">
                开始探索
              </Link>
            </nav>
            <nav
              aria-label="移动端快捷导航"
              className="flex items-center gap-1 md:hidden"
            >
              <Link className="button-quiet px-3" href="/help/safety">
                安全
              </Link>
              <Link className="button-primary px-4" href="/explore">
                开始探索
              </Link>
            </nav>
          </>
        )}
      </div>
    </header>
  );
}
