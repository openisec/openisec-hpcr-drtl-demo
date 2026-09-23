"use client";
import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { verifyEmail } from "@/lib/api";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<"checking" | "valid" | "invalid">("checking");
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("invalid");
      return;
    }
    verifyEmail(token)
      .then((res) => {
        setEmail(res.data.email);
        setStatus("valid");
      })
      .catch(() => {
        setStatus("invalid");
      });
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-blue-400">Openisec HPCR-DRTL</h1>
          <p className="text-slate-400 mt-2">メールアドレスの確認</p>
        </div>
        <div className="bg-slate-800 rounded-2xl p-8 shadow-xl border border-slate-700 text-center">
          {status === "checking" && (
            <p className="text-slate-400 text-sm">確認しています...</p>
          )}
          {status === "invalid" && (
            <>
              <h2 className="text-xl font-semibold mb-4">リンクが無効です</h2>
              <p className="text-slate-400 text-sm leading-relaxed mb-6">
                このリンクは無効か、有効期限が切れている可能性があります。お手数ですが再度お試しください。
              </p>
              <Link href="/register" className="text-blue-400 hover:underline text-sm">
                仮登録をやり直す
              </Link>
            </>
          )}
          {status === "valid" && (
            <>
              <h2 className="text-xl font-semibold mb-4">確認できました</h2>
              <p className="text-slate-400 text-sm leading-relaxed mb-6">
                {email} の確認が完了しました。続けて本登録にお進みください。
              </p>
              <Link
                href={`/register/complete?token=${encodeURIComponent(token)}`}
                className="inline-block w-full bg-blue-600 hover:bg-blue-500 rounded-lg py-2.5 font-semibold transition-colors"
              >
                本登録へ進む
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-slate-400">読み込み中...</div>}>
      <VerifyEmailContent />
    </Suspense>
  );
}
