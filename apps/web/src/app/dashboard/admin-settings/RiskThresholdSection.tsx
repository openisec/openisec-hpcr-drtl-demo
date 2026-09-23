"use client";
import { useEffect, useState } from "react";
import { updateOrganization } from "@/lib/api";

interface OrgRow {
  id: string;
  name: string;
  is_active: boolean;
  risk_score_threshold: number;
  is_personal?: boolean;
}

type PersonalFilter = "exclude" | "include";

export default function RiskThresholdSection({
  orgs,
  loading,
  onOrgsChanged,
}: {
  orgs: OrgRow[];
  loading: boolean;
  onOrgsChanged: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busyOrgId, setBusyOrgId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ orgId: string; message: string } | null>(null);
  const [savedOrgId, setSavedOrgId] = useState<string | null>(null);
  // 「個人」組織は通常このテーブルで確認するニーズが限定的なため、
  // デフォルトでは除外して表示する(Excelの列フィルタのようなイメージ)。
  const [personalFilter, setPersonalFilter] = useState<PersonalFilter>("exclude");

  // 組織一覧は上位(admin-settings/page.tsx)で一括取得し、propsで受け取る
  // (以前はこのコンポーネント単体でも取得しており、他セクションと合わせて
  // 同じデータを3重に取得していたため、1本化して通信数を減らした)。
  useEffect(() => {
    setDrafts(
      Object.fromEntries(orgs.map((o) => [o.id, String(o.risk_score_threshold)]))
    );
  }, [orgs]);

  const handleSave = async (org: OrgRow) => {
    const raw = drafts[org.id];
    const value = Number(raw);
    setRowError(null);
    if (!Number.isInteger(value) || value < 0 || value > 100) {
      setRowError({ orgId: org.id, message: "0〜100の整数で入力してください" });
      return;
    }
    setBusyOrgId(org.id);
    setSavedOrgId(null);
    try {
      await updateOrganization(org.id, { risk_score_threshold: value });
      setSavedOrgId(org.id);
      onOrgsChanged();
    } catch (err: any) {
      setRowError({
        orgId: org.id,
        message: err?.response?.data?.detail ?? "更新に失敗しました",
      });
    } finally {
      setBusyOrgId(null);
    }
  };

  const visibleOrgs = orgs.filter((o) => personalFilter === "include" || !o.is_personal);

  return (
    <section className="mb-10">
      <div className="mb-4">
        <h2 className="text-xl font-bold mb-1">リスクスコア閾値設定</h2>
        <p className="text-slate-400 text-sm">
          この閾値以上は承認者へ分析開始時に即座にメール通知されます。利用者と承認者の間で内容について確認しつつ意思決定を進めてください。また、利用者がログした直後に承認者への承認を求める承認依頼が送られ、承認者が承認しなければ、その意思決定は「完了」しません。(デフォルト: 70)
        </p>
      </div>

      {loading ? (
        <div className="text-center text-slate-400 py-8">読み込み中...</div>
      ) : visibleOrgs.length === 0 ? (
        <div className="text-center text-slate-400 py-8 border border-dashed border-slate-700 rounded-xl">
          表示できる組織がありません。
        </div>
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
                <th className="text-left px-5 py-3">リスクスコア閾値</th>
                <th className="text-left px-5 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {visibleOrgs.map((o) => (
                <tr key={o.id} className="border-t border-slate-700 align-top">
                  <td className="px-5 py-3">{o.name}</td>
                  <td className="px-5 py-3">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={drafts[o.id] ?? ""}
                      disabled={busyOrgId === o.id}
                      onChange={(e) =>
                        setDrafts((d) => ({ ...d, [o.id]: e.target.value }))
                      }
                      className="w-24 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm disabled:opacity-50"
                    />
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex flex-col gap-1.5 items-start">
                      <button
                        onClick={() => handleSave(o)}
                        disabled={busyOrgId === o.id || drafts[o.id] === String(o.risk_score_threshold)}
                        className="text-xs text-blue-400 hover:underline disabled:opacity-50"
                      >
                        保存
                      </button>
                      {savedOrgId === o.id && (
                        <p className="text-xs text-green-400">保存しました</p>
                      )}
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
