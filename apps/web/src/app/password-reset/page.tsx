"use client";
import { useState } from "react";
import Link from "next/link";
import { requestPasswordReset } from "@/lib/api";

export default function PasswordResetRequestPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await requestPasswordReset(email);
    } catch {
      // Intentionally ignore errors here; always show the generic message
      // to avoid leaking whether the email exists.
    } finally {
      setLoading(false);
      setSubmitted(true);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-blue-400">Openisec HPCR-DRTL</h1>
          <p className="text-slate-400 mt-2">パスワードリセット</p>
        </div>
        <div className="bg-slate-800 rounded-2xl p-8 shadow-xl border border-slate-700">
          {submitted ? (
            <div className="text-center">
              <h2 className="text-xl font-semibold mb-4">メールを送信しました</h2>
              <p className="text-slate-400 text-sm leading-relaxed">
                ご入力いただいたメールアドレス宛にパスワードリセット用のリンクを送信しました（該当するアカウントが存在する場合）。
                メールが届かない場合は、迷惑メールフォルダもご確認ください。
              </p>
              <Link href="/" className="inline-block mt-6 text-blue-400 hover:underline text-sm">
                ログイン画面に戻る
              </Link>
            </div>
          ) : (
            <>
              <h2 className="text-xl font-semibold mb-2">パスワードをお忘れですか？</h2>
              <p className="text-slate-400 text-sm mb-6">
                登録済みのメールアドレスを入力してください。リセット用のリンクをお送りします。
              </p>
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
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 rounded-lg py-2.5 font-semibold transition-colors"
                >
                  {loading ? "送信中..." : "リセットリンクを送信"}
                </button>
              </form>
              <p className="text-center text-sm text-slate-400 mt-6">
                <Link href="/" className="text-blue-400 hover:underline">
                  ログイン画面に戻る
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}