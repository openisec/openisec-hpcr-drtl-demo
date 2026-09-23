import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";
import Footer from "@/components/Footer";
import AuthGuard from "@/components/AuthGuard";

export const metadata: Metadata = {
  title: "Openisec HPCR-DRTL",
  description: "Human-in-the-loop Decision Support",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  await headers(); // Next.jsにnonceの存在を検知させ、内部スクリプトへ自動付与させるためのトリガー

  return (
    <html lang="ja">
      <body className="flex flex-col min-h-screen">
        <div className="flex-1">
          <AuthGuard>{children}</AuthGuard>
        </div>
        <Footer />
      </body>
    </html>
  );
}