"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { login, getMe } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

function isSafeNextPath(next: string | null): next is string {
  // オープンリダイレクト対策: サイト内の絶対パス(先頭が "/")のみ許可し、
  // "//evil.com" のようなプロトコル相対URLは弾く。
  return !!next && next.startsWith("/") && !next.startsWith("//");
}

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(email, password);
      const meRes = await getMe();
      useAuthStore.getState().setUser(meRes.data);
      const next = searchParams.get("next");
      if (meRes.data.must_change_password) {
        router.push("/change-password");
      } else if (isSafeNextPath(next)) {
        router.push(next);
      } else {
        router.push("/dashboard");
      }
    } catch {
      setError("メールアドレスまたはパスワードが正しくありません");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-blue-400">Openisec HPCR-DRTL</h1>
          <p className="text-slate-400 mt-2">意思決定支援プラットフォーム</p>
        </div>
        <div className="bg-slate-800 rounded-2xl p-8 shadow-xl border border-slate-700">
          <h2 className="text-xl font-semibold mb-6">ログイン</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">メールアドレス</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                placeholder="you@example.com"
                required
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm text-slate-400">パスワード</label>
                <Link href="/password-reset" className="text-xs text-blue-400 hover:underline">
                  パスワードをお忘れですか？
                </Link>
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                placeholder="••••••••"
                required
              />
            </div>
            {error && <p className="text-red-400 text-sm">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 rounded-lg py-2.5 font-semibold transition-colors"
            >
              {loading ? "ログイン中..." : "ログイン"}
            </button>
          </form>
          <p className="text-center text-sm text-slate-400 mt-6">
            アカウントをお持ちでない方は{" "}
            <Link href="/register" className="text-blue-400 hover:underline">
              新規登録
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen" />}>
      <LoginPageContent />
    </Suspense>
  );
}