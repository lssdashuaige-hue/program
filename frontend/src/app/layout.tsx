import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  ),
  applicationName: "PAS",
  title: {
    default: "PAS — 帮助你理解自己",
    template: "%s · PAS",
  },
  description:
    "一处安静、可控的 AI 辅助自我理解空间。PAS 不做心理诊断，也不替你决定人生。",
  category: "self-understanding",
  openGraph: {
    title: "PAS — 帮助你理解自己",
    description:
      "一处安静、可控的 AI 辅助自我理解空间。不是定义你，而是帮助你理解自己。",
    images: [
      {
        url: "/og-pas-reflection.png",
        width: 1536,
        height: 1024,
        alt: "暖白纸张上的开放圆环，象征持续而不封闭的自我理解",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/og-pas-reflection.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full">
      <body className="min-h-full antialiased">
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        {children}
      </body>
    </html>
  );
}
