"use client";
import { useEffect, useState } from "react";
import {
  getMembers,
  createMember,
  updateMember,
  reissueTempPassword,
} from "@/lib/api";
import { useAuthStore } from "@/store/auth";

interface Member {
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  organization_id: string;
  organization_name: string;
  must_change_password: boolean;
  is_active: boolean;
  created_at: string;
  // このユーザー自身の「個人」組織のID(存在する場合)。組織変更プルダウンで
  // 他人の個人組織を選択肢から除外するために使用する。
  personal_org_id?: string | null;
}

interface OrgOption {
  id: string;
  name: string;
  is_personal?: boolean;
}

export default function MembersSection({
  orgOptions,
}: {
  // 組織一覧は上位(admin-settings/page.tsx)で一括取得し、propsで受け取る
  // (以前はこのコンポーネント単体でも取得しており、他セクションと合わせて
  // 同じデータを3重に取得していたため、1本化して通信数を減らした)。
  orgOptions: OrgOption[];
}) {
  const user = useAuthStore((s) => s.user);
  const isPlatformAdmin = !!user?.is_platform_admin;

  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);

  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState("");
  const [familyName, setFamilyName] = useState("");
  const [givenName, setGivenName] = useState("");
  const [role, setRole] = useState("member");
  const [targetOrgId, setTargetOrgId] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [createdResult, setCreatedResult] = useState<{
    email: string;
    temp_password: string | null;
    message: string;
  } | null>(null);

  const [reissuedResult, setReissuedResult] = useState<{ email: string; temp_password: string } | null>(null);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ userId: string; message: string } | null>(null);

  const fetchMembers = async () => {
    setLoading(true);
    try {
      const res = await getMembers();
      setMembers(res.data.members);
    } catch (err: any) {
      if (err?.response?.status === 403) {
        setForbidden(true);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMembers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 「追加先組織」プルダウンの初期選択値は、propsのorgOptionsが届き次第設定する。
  useEffect(() => {
    if (isPlatformAdmin && orgOptions.length > 0 && !targetOrgId) {
      setTargetOrgId(orgOptions[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgOptions]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError("");
    setCreatedResult(null);
    try {
      const res = await createMember(
        email,
        familyName,
        givenName,
        role,
        isPlatformAdmin ? targetOrgId : undefined
      );
      setCreatedResult({
        email: res.data.email,
        temp_password: res.data.temp_password,
        message: res.data.message,
      });
      setEmail("");
      setFamilyName("");
      setGivenName("");
      setRole("member");
      setShowForm(false);
      await fetchMembers();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg).join(" / "));
      } else if (typeof detail === "string") {
        setError(detail);
      } else {
        setError("メンバーの作成に失敗しました");
      }
    } finally {
      setCreating(false);
    }
  };

  const handleRoleChange = async (m: Member, newRole: string) => {
    setBusyUserId(m.user_id);
    setRowError(null);
    try {
      await updateMember(m.organization_id, m.user_id, { role: newRole });
      await fetchMembers();
    } catch (err: any) {
      setRowError({ userId: m.user_id, message: err?.response?.data?.detail ?? "ロールの変更に失敗しました" });
    } finally {
      setBusyUserId(null);
    }
  };

  const handleOrgChange = async (m: Member, newOrgId: string) => {
    if (newOrgId === m.organization_id) return;
    if (!confirm(`${m.full_name} (${m.email}) を「${m.organization_name}」から別の組織へ移動しますか？`)) {
      return;
    }
    setBusyUserId(m.user_id);
    setRowError(null);
    try {
      await updateMember(m.organization_id, m.user_id, { new_organization_id: newOrgId });
      await fetchMembers();
    } catch (err: any) {
      setRowError({ userId: m.user_id, message: err?.response?.data?.detail ?? "組織の変更に失敗しました" });
    } finally {
      setBusyUserId(null);
    }
  };

  const handleToggleActive = async (m: Member) => {
    setBusyUserId(m.user_id);
    setRowError(null);
    try {
      await updateMember(m.organization_id, m.user_id, { is_active: !m.is_active });
      await fetchMembers();
    } catch (err: any) {
      setRowError({ userId: m.user_id, message: err?.response?.data?.detail ?? "更新に失敗しました" });
    } finally {
      setBusyUserId(null);
    }
  };

  const handleReissue = async (m: Member) => {
    if (!confirm(`${m.full_name} (${m.email}) の一時パスワードを再発行しますか？\n現在のパスワードは使用できなくなります。`)) {
      return;
    }
    setBusyUserId(m.user_id);
    setRowError(null);
    setReissuedResult(null);
    try {
      const res = await reissueTempPassword(m.organization_id, m.user_id);
      setReissuedResult({ email: m.email, temp_password: res.data.temp_password });
      await fetchMembers();
    } catch (err: any) {
      setRowError({ userId: m.user_id, message: err?.response?.data?.detail ?? "再発行に失敗しました" });
    } finally {
      setBusyUserId(null);
    }
  };

  if (forbidden) {
    return (
      <section className="mb-10">
        <div className="text-center text-slate-400 py-8 border border-dashed border-slate-700 rounded-xl">
          この機能は組織の管理者のみアクセスできます。
        </div>
      </section>
    );
  }

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold mb-1">メンバー管理</h2>
          <p className="text-slate-400 text-sm">
            {isPlatformAdmin ? "全組織のメンバー一覧と新規追加" : "組織に所属するメンバーの一覧と新規追加"}
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="bg-blue-600 hover:bg-blue-500 px-6 py-2.5 rounded-lg font-semibold transition-colors whitespace-nowrap"
        >
          {showForm ? "閉じる" : "+ メンバー追加"}
        </button>
      </div>

      {createdResult && (
        <div className="bg-green-900/30 border border-green-700 rounded-xl px-5 py-4 mb-6">
          <p className="font-semibold mb-1">{createdResult.message}</p>
          {createdResult.temp_password ? (
            <>
              <p className="text-sm text-slate-300">
                {createdResult.email} への一時パスワードを、本人へお伝えください。
              </p>
              <p className="text-sm mt-2">
                一時パスワード:{" "}
                <code className="bg-slate-900 px-2 py-1 rounded text-blue-300 select-all">
                  {createdResult.temp_password}
                </code>
              </p>
              <p className="text-xs text-slate-400 mt-2">
                このパスワードは再表示できません。控え忘れた場合は一覧の「パスワード再発行」から新しい一時パスワードを発行できます。
              </p>
            </>
          ) : (
            <p className="text-sm text-slate-300">
              {createdResult.email} は既存アカウントです。本人はご自身の既存パスワードでログイン後、組織を切り替えてご利用いただけます。
            </p>
          )}
        </div>
      )}

      {reissuedResult && (
        <div className="bg-green-900/30 border border-green-700 rounded-xl px-5 py-4 mb-6">
          <p className="font-semibold mb-1">一時パスワードを再発行しました</p>
          <p className="text-sm text-slate-300">{reissuedResult.email} への新しい一時パスワード:</p>
          <p className="text-sm mt-2">
            <code className="bg-slate-900 px-2 py-1 rounded text-blue-300 select-all">
              {reissuedResult.temp_password}
            </code>
          </p>
          <p className="text-xs text-slate-400 mt-2">
            このパスワードは再表示できません。以前のパスワードは無効になっています。
          </p>
        </div>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className="bg-slate-800 border border-slate-700 rounded-xl p-6 mb-8 space-y-4">
          {isPlatformAdmin && (
            <div>
              <label className="block text-sm text-slate-400 mb-1">追加先組織</label>
              <select
                value={targetOrgId}
                onChange={(e) => setTargetOrgId(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                required
              >
                {orgOptions.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="block text-sm text-slate-400 mb-1">メールアドレス</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
              required
            />
            <p className="text-xs text-slate-500 mt-1">
              既に他の組織で登録済みのメールアドレスの場合、既存アカウントがこの組織にも追加されます(氏名は既存の登録内容が使われます)。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-slate-400 mb-1">姓</label>
              <input
                type="text"
                value={familyName}
                onChange={(e) => setFamilyName(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
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
                required
              />
            </div>
          </div>
          <p className="text-xs text-slate-500 -mt-2">
            姓・名それぞれにスペースは含めないでください。
          </p>
          <div>
            <label className="block text-sm text-slate-400 mb-1">ロール</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
            >
              <option value="member">メンバー</option>
              <option value="approver">承認者</option>
              <option value="admin">管理者</option>
            </select>
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={creating}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 rounded-lg py-2.5 font-semibold transition-colors"
          >
            {creating ? "作成中..." : "作成する"}
          </button>
        </form>
      )}

      {loading ? (
        <div className="text-center text-slate-400 py-12">読み込み中...</div>
      ) : members.length === 0 ? (
        <div className="text-center text-slate-400 py-12 border border-dashed border-slate-700 rounded-xl">
          メンバーがまだいません。
        </div>
      ) : (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/50 text-slate-400">
              <tr>
                <th className="text-left px-5 py-3">氏名</th>
                <th className="text-left px-5 py-3">メールアドレス</th>
                {isPlatformAdmin && <th className="text-left px-5 py-3">組織</th>}
                <th className="text-left px-5 py-3">ロール</th>
                <th className="text-left px-5 py-3">状態</th>
                <th className="text-left px-5 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={`${m.organization_id}-${m.user_id}`} className="border-t border-slate-700 align-top">
                  <td className="px-5 py-3">{m.full_name}</td>
                  <td className="px-5 py-3 text-slate-300">{m.email}</td>
                  {isPlatformAdmin && (
                    <td className="px-5 py-3">
                      <select
                        value={m.organization_id}
                        disabled={busyUserId === m.user_id}
                        onChange={(e) => handleOrgChange(m, e.target.value)}
                        className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm disabled:opacity-50"
                      >
                        {orgOptions
                          // 「個人」組織はこのユーザー自身の個人組織以外は選択肢から除外する。
                          // 表示ラベルは組織名のみに戻すが、この除外自体は維持する
                          // (複数人が同じ個人組織にマッピングされる事故をUI上でも防ぐため)。
                          .filter((o) => !o.is_personal || o.id === m.personal_org_id || o.id === m.organization_id)
                          .map((o) => (
                            <option key={o.id} value={o.id}>
                              {o.name}
                            </option>
                          ))}
                      </select>
                    </td>
                  )}
                  <td className="px-5 py-3">
                    <select
                      value={m.role}
                      disabled={busyUserId === m.user_id}
                      onChange={(e) => handleRoleChange(m, e.target.value)}
                      className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm disabled:opacity-50"
                    >
                      <option value="member">メンバー</option>
                      <option value="approver">承認者</option>
                      <option value="admin">管理者</option>
                    </select>
                  </td>
                  <td className="px-5 py-3 space-y-1">
                    {m.must_change_password && (
                      <div>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-700 text-yellow-100">
                          初回パスワード未変更
                        </span>
                      </div>
                    )}
                    <div>
                      {m.is_active ? (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-700 text-green-100">
                          有効
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-600 text-slate-200">
                          無効化済み
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex flex-col gap-1.5 items-start">
                      <button
                        onClick={() => handleToggleActive(m)}
                        disabled={busyUserId === m.user_id}
                        className="text-xs text-blue-400 hover:underline disabled:opacity-50"
                      >
                        {m.is_active ? "無効化する" : "有効化する"}
                      </button>
                      <button
                        onClick={() => handleReissue(m)}
                        disabled={busyUserId === m.user_id}
                        className="text-xs text-blue-400 hover:underline disabled:opacity-50"
                      >
                        パスワード再発行
                      </button>
                      {rowError?.userId === m.user_id && (
                        <p className="text-xs text-red-400">{rowError.message}</p>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
