import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PAS — Psychological AI System",
  description: "不是定义你，而是帮助你理解自己。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full">
      <body className="min-h-full antialiased">{children}</body>
    </html>
  );
}
