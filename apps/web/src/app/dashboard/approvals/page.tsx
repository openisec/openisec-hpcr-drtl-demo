"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getApprovalQueue, approveMessage, rejectMessage } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

interface ApprovalQueueItem {
  session_id: string;
  message_id: string;
  title: string;
  risk_score: number;
  session_status: string;
  created_by_name: string | null;
  latest_approved_at: string | null;
  latest_approved_by_name: string | null;
  latest_rejected_at: string | null;
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("ja-JP");
}

export default function ApprovalsPage() {
  const user = useAuthStore((s) => s.user);
  const [items, setItems] = useState<ApprovalQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [busyMessageId, setBusyMessageId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectComment, setRejectComment] = useState("");
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null);

  const fetchQueue = async () => {
    setLoading(true);
    try {
      const res = await getApprovalQueue();
      setItems(res.data.items);
    } catch (err: any) {
      if (err?.response?.status === 403) {
        setForbidden(true);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueue();
  }, []);

  const handleApprove = async (item: ApprovalQueueItem) => {
    setBusyMessageId(item.message_id);
    setRowError(null);
    try {
      await approveMessage(item.session_id, item.message_id);
      await fetchQueue();
    } catch (err: any) {
      setRowError({ id: item.message_id, message: err?.response?.data?.detail ?? "承認に失敗しました" });
    } finally {
      setBusyMessageId(null);
    }
  };

  const handleReject = async (item: ApprovalQueueItem) => {
    setBusyMessageId(item.message_id);
    setRowError(null);
    try {
      await rejectMessage(item.session_id, item.message_id, rejectComment.trim() || undefined);
      setRejectingId(null);
      setRejectComment("");
      await fetchQueue();
    } catch (err: any) {
      setRowError({ id: item.message_id, message: err?.response?.data?.detail ?? "差し戻しに失敗しました" });
    } finally {
      setBusyMessageId(null);
    }
  };

  const riskColor = (score: number) => {
    if (score >= 70) return "text-red-400";
    if (score >= 40) return "text-yellow-400";
    return "text-green-400";
  };

  const statusBadge = (status: string) => {
    const map: Record<string, { text: string; cls: string }> = {
      awaiting_approval: { text: "承認待ち", cls: "bg-yellow-700 text-yellow-100" },
      open: { text: "進行中(差戻し済み)", cls: "bg-orange-700 text-orange-100" },
      completed: { text: "完了", cls: "bg-green-700 text-green-100" },
      // 「下書き」(slate系)との混同を避けるため、落ち着いたトーンの紫に変更。
      closed: { text: "終了", cls: "bg-purple-900 text-purple-200" },
    };
    const s = map[status] ?? { text: status, cls: "bg-slate-600 text-slate-200" };
    return <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${s.cls}`}>{s.text}</span>;
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

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold mb-1">要承認</h1>
          <p className="text-slate-400 text-sm">承認が必要になったことがある意思決定ログの一覧です(過去分を含む)。</p>
        </div>

        {forbidden ? (
          <div className="text-center text-slate-400 py-12 border border-dashed border-slate-700 rounded-xl">
            この画面は承認者のみアクセスできます。
          </div>
        ) : loading ? (
          <div className="text-center text-slate-400 py-12">読み込み中...</div>
        ) : items.length === 0 ? (
          <div className="text-center text-slate-400 py-12 border border-dashed border-slate-700 rounded-xl">
            現在、要承認となったことがある項目はありません。
          </div>
        ) : (
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/50 text-slate-400">
                <tr>
                  <th className="text-left px-5 py-3">対象</th>
                  <th className="text-left px-5 py-3">作成者</th>
                  <th className="text-left px-5 py-3">リスクスコア</th>
                  <th className="text-left px-5 py-3">状態</th>
                  <th className="text-left px-5 py-3">差し戻し日時(最新)</th>
                  <th className="text-left px-5 py-3">承認日時(最新)</th>
                  <th className="text-left px-5 py-3">承認者</th>
                  <th className="text-left px-5 py-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.message_id} className="border-t border-slate-700 align-top">
                    <td className="px-5 py-3">
                      <Link
                        href={`/dashboard/${item.session_id}`}
                        prefetch={false}
                        className="text-blue-300 hover:underline"
                      >
                        {item.title}
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-slate-300">{item.created_by_name ?? "—"}</td>
                    <td className="px-5 py-3">
                      <span className={`font-bold ${riskColor(item.risk_score)}`}>
                        {item.risk_score}/100
                      </span>
                    </td>
                    <td className="px-5 py-3">{statusBadge(item.session_status)}</td>
                    <td className="px-5 py-3 text-slate-300">{formatDateTime(item.latest_rejected_at)}</td>
                    <td className="px-5 py-3 text-slate-300">{formatDateTime(item.latest_approved_at)}</td>
                    <td className="px-5 py-3 text-slate-300">{item.latest_approved_by_name ?? "—"}</td>
                    <td className="px-5 py-3">
                      {item.session_status !== "awaiting_approval" ? (
                        <span className="text-xs text-slate-500">—</span>
                      ) : (
                      <div className="flex flex-col gap-1.5 items-start">
                        {rejectingId === item.message_id ? (
                          <div className="space-y-2 w-56">
                            <textarea
                              value={rejectComment}
                              onChange={(e) => setRejectComment(e.target.value)}
                              placeholder="差し戻し理由(任意)"
                              rows={2}
                              className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs"
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleReject(item)}
                                disabled={busyMessageId === item.message_id}
                                className="text-xs bg-orange-700 hover:bg-orange-600 disabled:opacity-50 px-3 py-1.5 rounded"
                              >
                                差し戻し確定
                              </button>
                              <button
                                onClick={() => { setRejectingId(null); setRejectComment(""); }}
                                className="text-xs text-slate-400 hover:text-white"
                              >
                                キャンセル
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleApprove(item)}
                              disabled={busyMessageId === item.message_id}
                              className="text-xs bg-green-700 hover:bg-green-600 disabled:opacity-50 px-3 py-1.5 rounded"
                            >
                              承認する
                            </button>
                            <button
                              onClick={() => setRejectingId(item.message_id)}
                              disabled={busyMessageId === item.message_id}
                              className="text-xs bg-slate-700 hover:bg-slate-600 disabled:opacity-50 px-3 py-1.5 rounded"
                            >
                              差し戻す
                            </button>
                          </div>
                        )}
                        {rowError?.id === item.message_id && (
                          <p className="text-xs text-red-400">{rowError.message}</p>
                        )}
                      </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
