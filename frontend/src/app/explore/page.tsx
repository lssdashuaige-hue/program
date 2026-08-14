import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { ReflectionRoom } from "@/components/reflection-room";

export const metadata: Metadata = {
  title: "反思空间",
  description: "从此刻真实的体验开始一次开放、非诊断式的自我探索。",
};

export default function ExplorePage() {
  return (
    <AppShell active="explore">
      <ReflectionRoom />
    </AppShell>
  );
}
