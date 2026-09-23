"use client";
import { useState } from "react";
import { createOrganization, updateOrganization } from "@/lib/api";

interface OrgRow {
  id: string;
  name: string;
  is_active: boolean;
  risk_score_threshold: number;
  is_personal?: boolean;
}

type PersonalFilter = "exclude" | "include";

export default function OrganizationSection({
  orgs,
  loading,
  onOrgsChanged,
}: {
  orgs: OrgRow[];
  loading: boolean;
  onOrgsChanged: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [editingOrgId, setEditingOrgId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [busyOrgId, setBusyOrgId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ orgId: string; message: string } | null>(null);
  // 「個人」組織は通常このテーブルで確認するニーズが限定的なため、
  // デフォルトでは除外して表示する(Excelの列フィルタのようなイメージ)。
  const [personalFilter, setPersonalFilter] = useState<PersonalFilter>("exclude");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newOrgName.trim()) return;
    setCreating(true);
    setCreateError("");
    try {
      await createOrganization(newOrgName.trim());
      setNewOrgName("");
      setShowForm(false);
      onOrgsChanged();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setCreateError(
        Array.isArray(detail)
          ? detail.map((d: any) => d.msg).join(" / ")
          : typeof detail === "string"
          ? detail
          : "組織の作成に失敗しました"
      );
    } finally {
      setCreating(false);
    }
  };

  const startEdit = (o: OrgRow) => {
    setEditingOrgId(o.id);
    setEditName(o.name);
    setRowError(null);
  };

  const handleRename = async (o: OrgRow) => {
    if (!editName.trim() || editName.trim() === o.name) {
      setEditingOrgId(null);
      return;
    }
    setBusyOrgId(o.id);
    setRowError(null);
    try {
      await updateOrganization(o.id, { name: editName.trim() });
      setEditingOrgId(null);
      onOrgsChanged();
    } catch (err: any) {
      setRowError({ orgId: o.id, message: err?.response?.data?.detail ?? "名称の変更に失敗しました" });
    } finally {
      setBusyOrgId(null);
    }
  };

  const handleToggleActive = async (o: OrgRow) => {
    if (!confirm(`「${o.name}」を${o.is_active ? "無効化" : "有効化"}しますか？`)) return;
    setBusyOrgId(o.id);
    setRowError(null);
    try {
      await updateOrganization(o.id, { is_active: !o.is_active });
      onOrgsChanged();
    } catch (err: any) {
      setRowError({ orgId: o.id, message: err?.response?.data?.detail ?? "更新に失敗しました" });
    } finally {
      setBusyOrgId(null);
    }
  };

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold mb-1">組織管理</h2>
          <p className="text-slate-400 text-sm">組織の作成・名称変更・無効化(Platform adminのみ)</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="bg-slate-700 hover:bg-slate-600 px-6 py-2.5 rounded-lg font-semibold transition-colors whitespace-nowrap"
        >
          {showForm ? "閉じる" : "+ 組織を作成"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-slate-800 border border-slate-700 rounded-xl p-6 mb-6 space-y-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">組織名</label>
            <input
              type="text"
              value={newOrgName}
              onChange={(e) => setNewOrgName(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
              placeholder="株式会社Example"
              required
            />
            <p className="text-xs text-slate-500 mt-1">
              組織の箱を作成します。メンバーは作成後、下の「メンバー管理」から追加してください。
            </p>
          </div>
          {createError && <p className="text-red-400 text-sm">{createError}</p>}
          <button
            type="submit"
            disabled={creating}
            className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 rounded-lg px-6 py-2.5 font-semibold transition-colors"
          >
            {creating ? "作成中..." : "組織を作成する"}
          </button>
        </form>
      )}

      {loading ? (
        <div className="text-center text-slate-400 py-8">読み込み中...</div>
      ) : (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/50 text-slate-400">
              <tr>
                <th className="text-left px-5 py-3">
                  <div className="flex items-center gap-2">
                    <span>組織名</span>
                    <select
                      value={personalFilter}
                      onChange={(e) => setPersonalFilter(e.target.value as PersonalFilter)}
                      className="bg-slate-900 border border-slate-600 rounded px-1.5 py-0.5 text-xs text-slate-300 font-normal focus:outline-none focus:border-blue-500"
                      title="「組織名」列のフィルタ"
                    >
                      <option value="exclude">「個人」を含まない</option>
                      <option value="include">「個人」を含む</option>
                    </select>
                  </div>
                </th>
                <th className="text-left px-5 py-3">状態</th>
                <th className="text-left px-5 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {orgs
                .filter((o) => personalFilter === "include" || !o.is_personal)
                .map((o) => (
                <tr key={o.id} className="border-t border-slate-700 align-top">
                  <td className="px-5 py-3">
                    {editingOrgId === o.id ? (
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm"
                        autoFocus
                      />
                    ) : (
                      o.name
                    )}
                  </td>
                  <td className="px-5 py-3">
                    {o.is_active ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-green-700 text-green-100">有効</span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-600 text-slate-200">無効化済み</span>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex flex-col gap-1.5 items-start">
                      {editingOrgId === o.id ? (
                        <div className="flex gap-3">
                          <button
                            onClick={() => handleRename(o)}
                            disabled={busyOrgId === o.id}
                            className="text-xs text-blue-400 hover:underline disabled:opacity-50"
                          >
                            保存
                          </button>
                          <button
                            onClick={() => setEditingOrgId(null)}
                            className="text-xs text-slate-400 hover:underline"
                          >
                            キャンセル
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => startEdit(o)}
                          disabled={busyOrgId === o.id}
                          className="text-xs text-blue-400 hover:underline disabled:opacity-50"
                        >
                          名称を変更
                        </button>
                      )}
                      <button
                        onClick={() => handleToggleActive(o)}
                        disabled={busyOrgId === o.id}
                        className="text-xs text-blue-400 hover:underline disabled:opacity-50"
                      >
                        {o.is_active ? "無効化する" : "有効化する"}
                      </button>
                      {rowError?.orgId === o.id && (
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
