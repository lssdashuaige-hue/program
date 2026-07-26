import Link from "next/link";
import { ReflectionRoom } from "@/components/reflection-room";

export default function ExplorePage() {
  return (
    <main>
      <nav className="mx-auto flex h-20 w-full max-w-6xl items-center justify-between px-5 sm:px-8">
        <Link className="text-sm font-semibold tracking-[0.18em]" href="/">PAS</Link>
        <Link className="text-sm text-[var(--muted)] hover:text-[var(--ink)]" href="/">返回首页</Link>
      </nav>
      <ReflectionRoom />
    </main>
  );
}
