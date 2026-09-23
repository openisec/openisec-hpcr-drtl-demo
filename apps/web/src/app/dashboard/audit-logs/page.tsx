"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuthStore } from "@/store/auth";
import {
  getOrgAuditLogs, getOrgAuditActions, exportOrgAuditLogs,
  getAuthAuditLogs, getAuthAuditActions, exportAuthAuditLogs,
} from "@/lib/api";

const LIMIT_OPTIONS = [20, 50, 100];

interface OrgAuditLogItem {
  id: string;
  action: string;
  actor_email: string | null;
  resource_type: string | null;
  target_user_id: string | null;
  target_user_email: string | null;
  occurred_at: string;
}

interface AuthAuditLogItem {
  id: string;
  action: string;
  actor_email: string | null;
  org_id: string | null;
  org_name: string | null;
  occurred_at: string;
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("ja-JP");
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  window.URL.revokeObjectURL(url);
}

export default function AuditLogsPage() {
  const user = useAuthStore((s) => s.user);
  const [tab, setTab] = useState<"org" | "auth">("org");

  // --- 共通フィルタ状態 ---
  const [action, setAction] = useState("");
  const [actorEmail, setActorEmail] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);

  const [actions, setActions] = useState<string[]>([]);
  const [items, setItems] = useState<(OrgAuditLogItem | AuthAuditLogItem)[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [exporting, setExporting] = useState(false);

  // タブ切替時にフィルタ・ページをリセット
  useEffect(() => {
    setAction("");
    setActorEmail("");
    setFromDate("");
    setToDate("");
    setPage(1);
  }, [tab]);

  const buildParams = useCallback(() => ({
    page,
    limit,
    action: action || undefined,
    actor_email: actorEmail || undefined,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
  }), [page, limit, action, actorEmail, fromDate, toDate]);

  const fetchActions = useCallback(async () => {
    try {
      const res = tab === "org" ? await getOrgAuditActions() : await getAuthAuditActions();
      setActions(res.data.actions);
    } catch {
      setActions([]);
    }
  }, [tab]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setForbidden(false);
    try {
      const params = buildParams();
      const res = tab === "org" ? await getOrgAuditLogs(params) : await getAuthAuditLogs(params);
      setItems(res.data.items);
      setTotal(res.data.total);
    } catch (err: any) {
      if (err?.response?.status === 403) {
        setForbidden(true);
        setItems([]);
        setTotal(0);
      }
    } finally {
      setLoading(false);
    }
  }, [tab, buildParams]);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const params = buildParams();
      const res = tab === "org" ? await exportOrgAuditLogs(params) : await exportAuthAuditLogs(params);
      downloadBlob(res.data, tab === "org" ? "audit_logs.csv" : "auth_audit_logs.csv");
    } finally {
      setExporting(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / limit));

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

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold mb-1">監査ログ</h1>
          <p className="text-slate-400 text-sm">
            組織内の操作履歴と認証イベントを確認できます。
          </p>
        </div>

        <div className="flex gap-2 mb-6 border-b border-slate-700">
          {[
            { key: "org" as const, label: "組織アクティビティ" },
            { key: "auth" as const, label: "認証ログ" },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
                tab === t.key
                  ? "border-blue-400 text-blue-300"
                  : "border-transparent text-slate-400 hover:text-white"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-3 items-end mb-4 bg-slate-800/50 border border-slate-700 rounded-xl p-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">アクション種別</label>
            <select
              value={action}
              onChange={(e) => { setAction(e.target.value); setPage(1); }}
              className="bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm"
            >
              <option value="">すべて</option>
              {actions.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">実行者メール</label>
            <input
              type="text"
              value={actorEmail}
              onChange={(e) => { setActorEmail(e.target.value); setPage(1); }}
              placeholder="部分一致"
              className="bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm w-48"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">開始日</label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => { setFromDate(e.target.value); setPage(1); }}
              className="bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm"
              style={{ colorScheme: "dark" }}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">終了日</label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => { setToDate(e.target.value); setPage(1); }}
              className="bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm"
              style={{ colorScheme: "dark" }}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">表示件数</label>
            <select
              value={limit}
              onChange={(e) => { setLimit(parseInt(e.target.value, 10)); setPage(1); }}
              className="bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm"
            >
              {LIMIT_OPTIONS.map((l) => (
                <option key={l} value={l}>{l}件</option>
              ))}
            </select>
          </div>
          <button
            onClick={() => { setAction(""); setActorEmail(""); setFromDate(""); setToDate(""); setPage(1); }}
            className="text-xs text-slate-400 hover:text-white px-2 py-1.5"
          >
            フィルタをクリア
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || forbidden}
            className="ml-auto text-xs bg-blue-700 hover:bg-blue-600 disabled:opacity-50 px-3 py-1.5 rounded font-semibold"
          >
            {exporting ? "出力中..." : "ログデータCSV出力"}
          </button>
        </div>

        {forbidden ? (
          <div className="text-center text-slate-400 py-12 border border-dashed border-slate-700 rounded-xl">
            この画面は組織管理者のみアクセスできます。
          </div>
        ) : loading ? (
          <div className="text-center text-slate-400 py-12">読み込み中...</div>
        ) : items.length === 0 ? (
          <div className="text-center text-slate-400 py-12 border border-dashed border-slate-700 rounded-xl">
            条件に一致するログはありません。
          </div>
        ) : (
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/50 text-slate-400">
                <tr>
                  <th className="text-left px-5 py-3">日時</th>
                  <th className="text-left px-5 py-3">アクション</th>
                  <th className="text-left px-5 py-3">実行者</th>
                  {tab === "org" ? (
                    <>
                      <th className="text-left px-5 py-3">対象種別</th>
                      <th className="text-left px-5 py-3">対象ユーザー</th>
                    </>
                  ) : (
                    <th className="text-left px-5 py-3">組織</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-t border-slate-700">
                    <td className="px-5 py-3 text-slate-300 whitespace-nowrap">
                      {formatDateTime(item.occurred_at)}
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-200 font-mono">
                        {item.action}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-300">{item.actor_email ?? "—"}</td>
                    {tab === "org" ? (
                      <>
                        <td className="px-5 py-3 text-slate-400">{(item as OrgAuditLogItem).resource_type ?? "—"}</td>
                        <td className="px-5 py-3 text-slate-400">
                          {(item as OrgAuditLogItem).target_user_email ?? "—"}
                        </td>
                      </>
                    ) : (
                      <td className="px-5 py-3 text-slate-400">
                        {(item as AuthAuditLogItem).org_name ?? "—"}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex items-center justify-between px-5 py-3 border-t border-slate-700 text-sm">
              <span className="text-slate-400">
                全{total}件中 {(page - 1) * limit + 1}〜{Math.min(page * limit, total)}件を表示
              </span>
              <div className="flex items-center gap-3">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                  className="text-slate-300 disabled:text-slate-600 hover:text-white"
                >
                  ← 前へ
                </button>
                <span className="text-slate-400">{page} / {totalPages}</span>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="text-slate-300 disabled:text-slate-600 hover:text-white"
                >
                  次へ →
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
