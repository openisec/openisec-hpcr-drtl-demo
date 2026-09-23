"use client";
import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { verifyEmail, register, login as loginApi, getMe } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

function RegisterCompleteForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [tokenStatus, setTokenStatus] = useState<"checking" | "valid" | "invalid">("checking");
  const [email, setEmail] = useState("");

  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [orgName, setOrgName] = useState("");
  const [familyName, setFamilyName] = useState("");
  const [givenName, setGivenName] = useState("");
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [agreePrivacy, setAgreePrivacy] = useState(false);
  const [marketingOptIn, setMarketingOptIn] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) {
      setTokenStatus("invalid");
      return;
    }
    // verify-emailはトークンを消費しない(consumed_atはregister()成功時に
    // 立つ)ため、emailの表示・トークン有効性の再確認のために呼び直せる。
    verifyEmail(token)
      .then((res) => {
        setEmail(res.data.email);
        setTokenStatus("valid");
      })
      .catch(() => {
        setTokenStatus("invalid");
      });
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== passwordConfirm) {
      setError("パスワードと確認用パスワードが一致しません");
      return;
    }

    setLoading(true);
    try {
      await register(
        email,
        password,
        passwordConfirm,
        familyName,
        givenName,
        orgName,
        agreeTerms,
        agreePrivacy,
        marketingOptIn,
        token
      );
      await loginApi(email, password);
      const meRes = await getMe();
      useAuthStore.getState().setUser(meRes.data);
      router.push("/dashboard");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg).join(" / "));
      } else if (typeof detail === "string") {
        setError(detail);
      } else {
        setError("登録に失敗しました");
      }
    } finally {
      setLoading(false);
    }
  };

  if (tokenStatus === "checking") {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-400">
        確認しています...
      </div>
    );
  }

  if (tokenStatus === "invalid") {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-blue-400">Openisec HPCR-DRTL</h1>
          </div>
          <div className="bg-slate-800 rounded-2xl p-8 shadow-xl border border-slate-700 text-center">
            <h2 className="text-xl font-semibold mb-4">リンクが無効です</h2>
            <p className="text-slate-400 text-sm leading-relaxed mb-6">
              このリンクは無効か、有効期限が切れている可能性があります。お手数ですが仮登録からやり直してください。
            </p>
            <Link href="/register" className="text-blue-400 hover:underline text-sm">
              仮登録をやり直す
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-blue-400">Openisec HPCR-DRTL</h1>
          <p className="text-slate-400 mt-2">アカウント作成 - 本登録</p>
        </div>
        <div className="bg-slate-800 rounded-2xl p-8 shadow-xl border border-slate-700">
          <p className="text-slate-400 text-sm mb-6">
            メールアドレスの確認が完了しました。残りの情報をご入力ください。
          </p>
          {/* autoComplete="off" をform全体にも指定し、ブラウザが保存済みの
              ログイン情報(email/password)を無関係なフィールドへ誤って
              流し込む挙動を防ぐ。各inputにも用途に応じたautoCompleteを
              個別指定する。 */}
          <form onSubmit={handleSubmit} className="space-y-4" autoComplete="off">
            <div>
              <label className="block text-sm text-slate-400 mb-1">メールアドレス</label>
              <input
                type="email"
                value={email}
                readOnly
                autoComplete="off"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2.5 text-slate-400 cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">パスワード</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                placeholder="12文字以上、大小英字・数字・記号を含む"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">パスワード確認</label>
              <input
                type="password"
                value={passwordConfirm}
                onChange={(e) => setPasswordConfirm(e.target.value)}
                autoComplete="new-password"
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">組織名</label>
              <input
                type="text"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                autoComplete="organization"
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                placeholder="株式会社Example または 個人"
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-slate-400 mb-1">姓</label>
                <input
                  type="text"
                  value={familyName}
                  onChange={(e) => setFamilyName(e.target.value)}
                  autoComplete="family-name"
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder="山田"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">名</label>
                <input
                  type="text"
                  value={givenName}
                  onChange={(e) => setGivenName(e.target.value)}
                  autoComplete="given-name"
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder="太郎"
                  required
                />
              </div>
            </div>
            <p className="text-xs text-slate-500 -mt-2">
              姓・名それぞれにスペースは含めないでください。
            </p>
            <div className="space-y-3 pt-2">
              <label className="flex items-start gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={agreeTerms}
                  onChange={(e) => setAgreeTerms(e.target.checked)}
                  className="mt-1"
                  required
                />
                <span>
                  <span className="text-red-400 text-xs mr-1">[必須同意]</span>
                  <Link href="/disclaimer" target="_blank" className="text-blue-400 hover:underline">
                    利用上の注意・免責事項
                  </Link>
                  に同意します
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={agreePrivacy}
                  onChange={(e) => setAgreePrivacy(e.target.checked)}
                  className="mt-1"
                  required
                />
                <span>
                  <span className="text-red-400 text-xs mr-1">[必須同意]</span>
                  <Link href="/privacy" target="_blank" className="text-blue-400 hover:underline">
                    プライバシーポリシー
                  </Link>
                  に同意します
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={marketingOptIn}
                  onChange={(e) => setMarketingOptIn(e.target.checked)}
                  className="mt-1"
                />
                <span>
                  <span className="text-slate-500 text-xs mr-1">[任意]</span>
                  Openisecからの機能更新、イベント、キャンペーン等の案内メールの受信を希望します
                </span>
              </label>
            </div>
            {error && <p className="text-red-400 text-sm">{error}</p>}
            <button
              type="submit"
              disabled={loading || !agreeTerms || !agreePrivacy}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 rounded-lg py-2.5 font-semibold transition-colors"
            >
              {loading ? "登録中..." : "登録する"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function RegisterCompletePage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-slate-400">読み込み中...</div>}>
      <RegisterCompleteForm />
    </Suspense>
  );
}
