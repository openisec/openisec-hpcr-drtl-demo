"use client";
import { useState } from "react";
import Link from "next/link";
import { updateMyName, changePassword, getMe } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

export default function AccountPage() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  // --- 氏名変更 ---
  const [familyName, setFamilyName] = useState("");
  const [givenName, setGivenName] = useState("");
  const [nameError, setNameError] = useState("");
  const [nameSuccess, setNameSuccess] = useState("");
  const [nameSaving, setNameSaving] = useState(false);

  const handleNameSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setNameSaving(true);
    setNameError("");
    setNameSuccess("");
    try {
      await updateMyName(familyName, givenName);
      const meRes = await getMe();
      setUser(meRes.data);
      setNameSuccess("氏名を変更しました");
      setFamilyName("");
      setGivenName("");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setNameError(detail.map((d: any) => d.msg).join(" / "));
      } else if (typeof detail === "string") {
        setNameError(detail);
      } else {
        setNameError("氏名の変更に失敗しました");
      }
    } finally {
      setNameSaving(false);
    }
  };

  // --- パスワード変更 ---
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordSaving(true);
    setPasswordError("");
    setPasswordSuccess("");
    try {
      await changePassword(currentPassword, newPassword, newPasswordConfirm);
      setPasswordSuccess("パスワードを変更しました");
      setCurrentPassword("");
      setNewPassword("");
      setNewPasswordConfirm("");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setPasswordError(detail.map((d: any) => d.msg).join(" / "));
      } else if (typeof detail === "string") {
        setPasswordError(detail);
      } else {
        setPasswordError("パスワードの変更に失敗しました");
      }
    } finally {
      setPasswordSaving(false);
    }
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-700 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold text-blue-400">Openisec HPCR-DRTL</h1>
        <div className="flex items-center gap-4">
          <span className="text-slate-400 text-sm">{user?.email}</span>
          <Link href="/dashboard" className="text-sm text-slate-400 hover:text-white transition-colors">
            ダッシュボードへ戻る
          </Link>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8 space-y-8">
        <div>
          <h2 className="text-2xl font-bold mb-2">アカウント管理</h2>
          <p className="text-slate-400">氏名・パスワードなど、ご自身のアカウント情報を管理できます。</p>
        </div>

        {/* 氏名変更 */}
        <section className="bg-slate-800 border border-slate-700 rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-1">氏名</h3>
          <p className="text-slate-400 text-sm mb-4">
            現在の氏名: <span className="text-white">{user?.full_name ?? "-"}</span>
          </p>
          <form onSubmit={handleNameSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-slate-400 mb-1">姓</label>
                <input
                  type="text"
                  value={familyName}
                  onChange={(e) => setFamilyName(e.target.value)}
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
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                  placeholder="太郎"
                  required
                />
              </div>
            </div>
            <p className="text-xs text-slate-500 -mt-2">
              姓・名それぞれにスペースは含めないでください。
            </p>
            {nameError && <p className="text-red-400 text-sm">{nameError}</p>}
            {nameSuccess && <p className="text-green-400 text-sm">{nameSuccess}</p>}
            <button
              type="submit"
              disabled={nameSaving}
              className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 rounded-lg px-6 py-2.5 font-semibold transition-colors"
            >
              {nameSaving ? "変更中..." : "氏名を変更する"}
            </button>
          </form>
        </section>

        {/* パスワード変更 */}
        <section className="bg-slate-800 border border-slate-700 rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-4">パスワード</h3>
          <form onSubmit={handlePasswordSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">現在のパスワード</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                required
              />
            </div>
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
                value={newPasswordConfirm}
                onChange={(e) => setNewPasswordConfirm(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                required
              />
            </div>
            {passwordError && <p className="text-red-400 text-sm">{passwordError}</p>}
            {passwordSuccess && <p className="text-green-400 text-sm">{passwordSuccess}</p>}
            <button
              type="submit"
              disabled={passwordSaving}
              className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 rounded-lg px-6 py-2.5 font-semibold transition-colors"
            >
              {passwordSaving ? "変更中..." : "パスワードを変更する"}
            </button>
          </form>
        </section>

        {/*
          今後、課金・プラン関連情報をここに追加する想定
          (例: 現在のプラン、請求先情報、支払い方法など)
        */}
      </main>
    </div>
  );
}
