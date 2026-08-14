import { OpenRingMark } from "@/components/open-ring-mark";

type PageIntroProps = {
  description: string;
  eyebrow: string;
  note?: string;
  title: string;
};

export function PageIntro({
  description,
  eyebrow,
  note,
  title,
}: PageIntroProps) {
  return (
    <header className="flex items-start justify-between gap-8 border-b border-[var(--line)] pb-8">
      <div className="max-w-3xl">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="mt-4 text-4xl leading-tight font-medium tracking-[-0.045em] sm:text-5xl">
          {title}
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-8 text-[var(--muted)] sm:text-lg">
          {description}
        </p>
        {note && <p className="status-chip mt-5">{note}</p>}
      </div>
      <OpenRingMark className="mt-2 hidden sm:inline-grid" />
    </header>
  );
}
