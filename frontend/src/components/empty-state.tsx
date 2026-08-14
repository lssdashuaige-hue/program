import Link from "next/link";
import { OpenRingMark } from "@/components/open-ring-mark";

type EmptyStateProps = {
  actionHref?: string;
  actionLabel?: string;
  description: string;
  title: string;
};

export function EmptyState({
  actionHref,
  actionLabel,
  description,
  title,
}: EmptyStateProps) {
  return (
    <section className="quiet-card flex flex-col items-start gap-5 p-6 sm:flex-row sm:items-center sm:p-8">
      <OpenRingMark className="shrink-0" />
      <div className="max-w-2xl flex-1">
        <h2 className="text-xl font-medium tracking-[-0.025em]">{title}</h2>
        <p className="mt-2 leading-7 text-[var(--muted)]">{description}</p>
      </div>
      {actionHref && actionLabel && (
        <Link className="button-secondary shrink-0" href={actionHref}>
          {actionLabel}
        </Link>
      )}
    </section>
  );
}
