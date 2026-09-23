"use client";
import { useState } from "react";
import Link from "next/link";
import { preRegister } from "@/lib/api";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [emailConfirm, setEmailConfirm] = useState("");
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (email !== emailConfirm) {
      setError("メールアドレスが一致しません");
      return;
    }

    setLoading(true);
    try {
      await preRegister(email);
    } catch {
      // 既存ユーザーの有無に関わらず、常に同じ汎用メッセージを表示する
      // (enumeration対策。バックエンド側と挙動を合わせる)
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
          <p className="text-slate-400 mt-2">アカウント作成 - 仮登録</p>
        </div>
        <div className="bg-slate-800 rounded-2xl p-8 shadow-xl border border-slate-700">
          {submitted ? (
            <div className="text-center">
              <h2 className="text-xl font-semibold mb-4">確認メールを送信しました</h2>
              <p className="text-slate-400 text-sm leading-relaxed">
                ご入力いただいたメールアドレス宛に確認メールを送信しました（該当するアドレスが未登録の場合）。
                メール内のリンクから本登録を続けてください。メールが届かない場合は、迷惑メールフォルダもご確認ください。
              </p>
              <Link href="/" className="inline-block mt-6 text-blue-400 hover:underline text-sm">
                ログイン画面に戻る
              </Link>
            </div>
          ) : (
            <>
              <h2 className="text-xl font-semibold mb-2">まずはメールアドレスをご確認ください</h2>
              <p className="text-slate-400 text-sm mb-6">
                入力いただいたメールアドレス宛に確認メールをお送りします。
              </p>
              <form onSubmit={handleSubmit} className="space-y-4" autoComplete="off">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">メールアドレス</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                    placeholder="you@example.com"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">メールアドレス確認</label>
                  <input
                    type="email"
                    value={emailConfirm}
                    onChange={(e) => setEmailConfirm(e.target.value)}
                    autoComplete="off"
                    className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                    placeholder="you@example.com"
                    required
                  />
                </div>
                {error && <p className="text-red-400 text-sm">{error}</p>}
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 rounded-lg py-2.5 font-semibold transition-colors"
                >
                  {loading ? "送信中..." : "メールアドレスを確認する"}
                </button>
              </form>
              <p className="text-center text-sm text-slate-400 mt-6">
                すでにアカウントをお持ちですか？{" "}
                <Link href="/" className="text-blue-400 hover:underline">
                  ログイン
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
