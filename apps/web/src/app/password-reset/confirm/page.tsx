"use client";
import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { confirmPasswordReset } from "@/lib/api";

function PasswordResetConfirmForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!token) {
      setError("リセットリンクが無効です。お手数ですが再度リセットを申請してください。");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("パスワードが一致しません");
      return;
    }

    setLoading(true);
    try {
      await confirmPasswordReset(token, newPassword);
      setSuccess(true);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg).join(" / "));
      } else if (typeof detail === "string") {
        setError(detail);
      } else {
        setError("パスワードのリセットに失敗しました");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-blue-400">Openisec HPCR-DRTL</h1>
          <p className="text-slate-400 mt-2">新しいパスワードの設定</p>
        </div>
        <div className="bg-slate-800 rounded-2xl p-8 shadow-xl border border-slate-700">
          {success ? (
            <div className="text-center">
              <h2 className="text-xl font-semibold mb-4">パスワードを再設定しました</h2>
              <p className="text-slate-400 text-sm leading-relaxed mb-6">
                新しいパスワードでログインしてください。
              </p>
              <button
                onClick={() => router.push("/")}
                className="w-full bg-blue-600 hover:bg-blue-500 rounded-lg py-2.5 font-semibold transition-colors"
              >
                ログイン画面へ
              </button>
            </div>
          ) : !token ? (
            <div className="text-center">
              <h2 className="text-xl font-semibold mb-4">リンクが無効です</h2>
              <p className="text-slate-400 text-sm leading-relaxed mb-6">
                このリセットリンクは無効か期限切れの可能性があります。お手数ですが再度お試しください。
              </p>
              <Link href="/password-reset" className="text-blue-400 hover:underline text-sm">
                パスワードリセットをやり直す
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">新しいパスワード</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder="12文字以上、大小英字・数字・記号を含む"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">新しいパスワード（確認）</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
              {error && <p className="text-red-400 text-sm">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 rounded-lg py-2.5 font-semibold transition-colors"
              >
                {loading ? "設定中..." : "パスワードを再設定"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PasswordResetConfirmPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-slate-400">読み込み中...</div>}>
      <PasswordResetConfirmForm />
    </Suspense>
  );
}