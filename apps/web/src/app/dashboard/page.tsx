"use client";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getSessions, getSharedSessions, createSession, logout, getMe, switchOrg } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import Link from "next/link";

interface Session {
  id: string;
  title: string;
  status: string;
  created_at: string;
  target_date?: string | null;
  approved_at?: string | null;
}

interface SharedSession {
  id: string;
  title: string;
  status: string;
  created_at: string;
  created_by: string;
  created_by_name?: string | null;
  created_by_email?: string | null;
  target_date?: string | null;
  approved_at?: string | null;
}

const LIMIT_OPTIONS = [20, 50, 100];
const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "すべて" },
  { value: "draft", label: "下書き" },
  { value: "open", label: "進行中" },
  { value: "awaiting_approval", label: "承認待ち" },
  { value: "completed", label: "完了" },
  { value: "closed", label: "終了" },
];

function DashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const clearAuth = useAuthStore((s) => s.clearAuth);

  const activeTab: "mine" | "shared" = searchParams.get("tab") === "shared" ? "shared" : "mine";

  // フィルタ・ページネーションの状態はURLクエリと同期する。
  // タブ切替時にリセットされるよう、常に「今表示しているタブの状態」のみをURLに反映する。
  const page = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);
  const limit = LIMIT_OPTIONS.includes(parseInt(searchParams.get("limit") ?? "20", 10))
    ? parseInt(searchParams.get("limit") ?? "20", 10)
    : 20;
  const fromDate = searchParams.get("from") ?? "";
  const toDate = searchParams.get("to") ?? "";
  const status = searchParams.get("status") ?? "";
  const q = searchParams.get("q") ?? "";
  const createdBy = searchParams.get("created_by") ?? "";

  // キーワード検索はデバウンスするため、入力欄自体は別途ローカル状態で持つ
  const [qInput, setQInput] = useState(q);
  useEffect(() => {
    setQInput(q);
  }, [q, activeTab]);

  const [sessions, setSessions] = useState<Session[]>([]);
  const [sharedSessions, setSharedSessions] = useState<SharedSession[]>([]);
  const [total, setTotal] = useState(0);
  const [newTitle, setNewTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  const activeMembership = user?.memberships.find((m) => m.organization_id === user.active_org_id);
  const canManageMembers = !!user?.is_platform_admin || activeMembership?.role === "admin";
  const isApprover = activeMembership?.role === "approver";
  const PERSONAL_ORG_NAMES = ["個人", "personal"];
  const isPersonalOrg = !!activeMembership &&
    PERSONAL_ORG_NAMES.includes(activeMembership.organization_name.trim().toLowerCase());

  // 組織スイッチ: 自分がmembership(admin)として登録されている組織のみ選択肢にする。
  // platform_adminであっても、全組織を無条件にリストしない(安易な他組織閲覧を防ぐ統制)。
  const [switchingOrg, setSwitchingOrg] = useState(false);
  const [pendingSwitchOrgId, setPendingSwitchOrgId] = useState<string | null>(null);
  const [switchPassword, setSwitchPassword] = useState("");
  const [switchError, setSwitchError] = useState("");

  const orgSwitchOptions = (user?.memberships ?? []).map((m) => ({
    id: m.organization_id,
    name: m.organization_name,
  }));

  const handleSwitchOrg = async (orgId: string, password: string) => {
    setSwitchingOrg(true);
    setSwitchError("");
    try {
      await switchOrg(orgId, password);
      const meRes = await getMe();
      setUser(meRes.data);
      // 組織スコープの一覧(セッション・管理設定・監査ログ等)を全て
      // 作り直すため、単純にページを再読み込みする。
      window.location.reload();
    } catch (err: any) {
      setSwitchError(err?.response?.data?.detail ?? "切り替えに失敗しました");
      setSwitchingOrg(false);
    }
  };

  // 個人/Personal組織には「組織内の他ユーザーのログ」タブが存在しない
  // (一人組織のため)。URL直打ちで shared タブに来た場合も自分のログへ戻す。
  useEffect(() => {
    if (isPersonalOrg && activeTab === "shared") {
      router.push("/dashboard");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPersonalOrg, activeTab]);

  // 作成者フィルタの選択肢は、現在読み込まれている「組織内の他ユーザーのログ」から
  // 重複を除いて抽出する(専用の一覧APIを設けるほどではないため簡易対応)。
  const creatorOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of sharedSessions) {
      map.set(s.created_by, s.created_by_name ?? s.created_by_email ?? s.created_by);
    }
    return Array.from(map.entries());
  }, [sharedSessions]);

  const updateParams = useCallback(
    (updates: Record<string, string | number | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === "" || value === undefined) {
          params.delete(key);
        } else {
          params.set(key, String(value));
        }
      }
      const qs = params.toString();
      router.push(`/dashboard${qs ? `?${qs}` : ""}`);
    },
    [router, searchParams]
  );

  const selectTab = (tab: "mine" | "shared") => {
    // タブを切り替える際は、フィルタ・ページ状態をリセットして混乱を避ける
    if (tab === "mine") {
      router.push("/dashboard");
    } else {
      router.push("/dashboard?tab=shared");
    }
  };

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getSessions({
        page,
        limit,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        status: status || undefined,
        q: q || undefined,
      });
      setSessions(res.data.items);
      setTotal(res.data.total);
    } catch {
      router.push("/");
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, limit, fromDate, toDate, status, q]);

  const fetchSharedSessions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getSharedSessions({
        page,
        limit,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        status: status || undefined,
        q: q || undefined,
        created_by: createdBy || undefined,
      });
      setSharedSessions(res.data.items);
      setTotal(res.data.total);
    } catch {
      // 一覧取得の失敗はタブ内で静かに扱う(ログイン自体は継続)
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, limit, fromDate, toDate, status, q, createdBy]);

  useEffect(() => {
    if (activeTab === "mine") {
      fetchSessions();
    } else {
      fetchSharedSessions();
    }
  }, [activeTab, fetchSessions, fetchSharedSessions]);

  // キーワード入力を1秒デバウンスしてURL(=検索実行)に反映
  const qDebounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (qDebounceTimer.current) clearTimeout(qDebounceTimer.current);
    qDebounceTimer.current = setTimeout(() => {
      if (qInput !== q) {
        updateParams({ q: qInput || null, page: 1 });
      }
    }, 500);
    return () => {
      if (qDebounceTimer.current) clearTimeout(qDebounceTimer.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      const res = await createSession(newTitle.trim());
      router.push(`/dashboard/${res.data.id}`);
    } catch {
      alert("セッション作成に失敗しました");
    } finally {
      setCreating(false);
    }
  };

  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await logout();
    } catch {
    // セッションが既に無効(期限切れ等)でも、ログアウト自体は
    // ローカル側の状態クリア+画面遷移で完了させる
    } finally {
      clearAuth();
      router.push("/");
    }
  };

  const statusBadge = (statusValue: string) => {
    const map: Record<string, string> = {
      draft: "bg-slate-600 text-slate-200",
      open: "bg-blue-600 text-white",
      awaiting_approval: "bg-yellow-700 text-yellow-100",
      completed: "bg-green-700 text-white",
      // 「下書き」(slate系)との混同を避けるため、落ち着いたトーンの紫に変更。
      closed: "bg-purple-900 text-purple-200",
    };
    const label: Record<string, string> = {
      draft: "下書き",
      open: "進行中",
      awaiting_approval: "承認待ち",
      completed: "完了",
      closed: "終了",
    };
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full ${map[statusValue] ?? "bg-slate-600"}`}>
        {label[statusValue] ?? statusValue}
      </span>
    );
  };

  const totalPages = Math.max(1, Math.ceil(total / limit));

  const renderFilters = () => (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 mb-6 flex flex-wrap gap-3 items-end">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-slate-400">キーワード</label>
        <input
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          placeholder="タイトル・決定・理由を検索..."
          className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500 w-56"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-slate-400">期間(開始)</label>
        <input
          type="date"
          value={fromDate}
          onChange={(e) => updateParams({ from: e.target.value || null, page: 1 })}
          className="date-input-gray bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-slate-400">期間(終了)</label>
        <input
          type="date"
          value={toDate}
          onChange={(e) => updateParams({ to: e.target.value || null, page: 1 })}
          className="date-input-gray bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
        />
      </div>
      <style jsx global>{`
        .date-input-gray::-webkit-calendar-picker-indicator {
          filter: invert(64%) sepia(6%) saturate(383%) hue-rotate(179deg) brightness(90%) contrast(87%);
          cursor: pointer;
        }
      `}</style>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-slate-400">ステータス</label>
        <select
          value={status}
          onChange={(e) => updateParams({ status: e.target.value || null, page: 1 })}
          className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      {activeTab === "shared" && (
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400">作成者</label>
          <select
            value={createdBy}
            onChange={(e) => updateParams({ created_by: e.target.value || null, page: 1 })}
            className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
          >
            <option value="">すべて</option>
            {creatorOptions.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="flex flex-col gap-1">
        <label className="text-xs text-slate-400">表示件数</label>
        <select
          value={limit}
          onChange={(e) => updateParams({ limit: e.target.value, page: 1 })}
          className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
        >
          {LIMIT_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}行
            </option>
          ))}
        </select>
      </div>
      {(fromDate || toDate || status || q || createdBy) && (
        <button
          onClick={() =>
            updateParams({ from: null, to: null, status: null, q: null, created_by: null, page: 1 })
          }
          className="text-xs text-slate-400 hover:text-white underline"
        >
          フィルタをクリア
        </button>
      )}
    </div>
  );

  const renderPagination = () => (
    <div className="flex items-center justify-between mt-6 text-sm text-slate-400">
      <span>
        全{total}件中 {(page - 1) * limit + 1}〜{Math.min(page * limit, total)}件を表示
      </span>
      <div className="flex items-center gap-3">
        <button
          disabled={page <= 1}
          onClick={() => updateParams({ page: page - 1 })}
          className="px-3 py-1.5 rounded-lg border border-slate-600 disabled:opacity-40 disabled:cursor-not-allowed hover:border-blue-500 transition-colors"
        >
          ← 前へ
        </button>
        <span>
          {page} / {totalPages}
        </span>
        <button
          disabled={page >= totalPages}
          onClick={() => updateParams({ page: page + 1 })}
          className="px-3 py-1.5 rounded-lg border border-slate-600 disabled:opacity-40 disabled:cursor-not-allowed hover:border-blue-500 transition-colors"
        >
          次へ →
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-700 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold text-blue-400">Openisec HPCR-DRTL</h1>
        <div className="flex items-center gap-4">
          {canManageMembers && (
            <Link href="/dashboard/admin-settings" className="text-sm text-slate-400 hover:text-white transition-colors">
              管理設定
            </Link>
          )}
          {canManageMembers && (
            <Link href="/dashboard/audit-logs" className="text-sm text-slate-400 hover:text-white transition-colors">
              監査ログ
            </Link>
          )}
          {isApprover && (
            <Link href="/dashboard/approvals" className="text-sm text-slate-400 hover:text-white transition-colors">
              要承認
            </Link>
          )}
          <Link href="/dashboard/account" className="text-sm text-slate-400 hover:text-white transition-colors">
            アカウント管理
          </Link>
          <span className="text-slate-400 text-sm">{user?.email}</span>
          <button
            onClick={handleLogout}
            disabled={loggingOut}
            className="text-sm text-slate-400 hover:text-white transition-colors disabled:opacity-50"
          >
            {loggingOut ? "ログアウト中..." : "ログアウト"}
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-bold mb-2">意思決定セッション</h2>
          <p className="text-slate-400">
            新しい意思決定の分析を開始するか、過去のセッションを確認してください。
          </p>
        </div>

        <div className="mb-6 flex items-center gap-3 text-sm">
          <span className="text-slate-400">所属組織:</span>
          <span className="text-slate-200 font-medium">{activeMembership?.organization_name ?? "—"}</span>
          {orgSwitchOptions.length > 1 && (
            <select
              value=""
              onChange={(e) => {
                if (e.target.value) setPendingSwitchOrgId(e.target.value);
                e.target.value = "";
              }}
              disabled={switchingOrg}
              className="bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200 disabled:opacity-50"
            >
              <option value="">組織を切り替え...</option>
              {orgSwitchOptions
                .filter((o) => o.id !== user?.active_org_id)
                .map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
            </select>
          )}
        </div>

        {pendingSwitchOrgId && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-sm">
              <h3 className="text-lg font-semibold mb-2">組織の切り替え</h3>
              <p className="text-sm text-slate-400 mb-4">
                本人確認のため、現在のパスワードを入力してください。
              </p>
              <input
                type="password"
                autoFocus
                value={switchPassword}
                onChange={(e) => setSwitchPassword(e.target.value)}
                placeholder="パスワード"
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-sm mb-2"
              />
              {switchError && <p className="text-red-400 text-xs mb-2">{switchError}</p>}
              <div className="flex justify-end gap-2 mt-4">
                <button
                  onClick={() => { setPendingSwitchOrgId(null); setSwitchPassword(""); setSwitchError(""); }}
                  className="text-sm text-slate-400 hover:text-white px-3 py-1.5"
                >
                  キャンセル
                </button>
                <button
                  onClick={() => handleSwitchOrg(pendingSwitchOrgId, switchPassword)}
                  disabled={switchingOrg || !switchPassword}
                  className="text-sm bg-blue-700 hover:bg-blue-600 disabled:opacity-50 px-4 py-1.5 rounded font-semibold"
                >
                  {switchingOrg ? "切り替え中..." : "切り替える"}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="flex gap-2 mb-6 border-b border-slate-700">
          <button
            onClick={() => selectTab("mine")}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "mine"
                ? "border-blue-500 text-white"
                : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            自分のログ
          </button>
          {!isPersonalOrg && (
            <button
              onClick={() => selectTab("shared")}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "shared"
                  ? "border-blue-500 text-white"
                  : "border-transparent text-slate-400 hover:text-white"
              }`}
            >
              組織内の他ユーザーのログ
            </button>
          )}
        </div>

        {activeTab === "mine" || isPersonalOrg ? (
          <>
            <form onSubmit={handleCreate} className="flex gap-3 mb-8">
              <input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="新しい意思決定のタイトルを入力..."
                className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
              />
              <button
                type="submit"
                disabled={creating}
                className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 px-6 py-2.5 rounded-lg font-semibold transition-colors whitespace-nowrap"
              >
                {creating ? "作成中..." : "+ 新規作成"}
              </button>
            </form>

            {renderFilters()}

            {loading ? (
              <div className="text-center text-slate-400 py-12">読み込み中...</div>
            ) : sessions.length === 0 ? (
              <div className="text-center text-slate-400 py-12 border border-dashed border-slate-700 rounded-xl">
                該当するセッションがありません。
              </div>
            ) : (
              <>
                <div className="space-y-3">
                  {sessions.map((s) => (
                    <Link key={s.id} href={`/dashboard/${s.id}`} prefetch={false}>
                      <div className="bg-slate-800 border border-slate-700 hover:border-blue-500 rounded-xl px-5 py-4 transition-colors cursor-pointer">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{s.title}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-slate-400 whitespace-nowrap">
                              {s.approved_at ? `Approved: ${new Date(s.approved_at).toLocaleDateString("ja-JP")}` : ""}
                            </span>
                            <span className="text-xs text-slate-400 whitespace-nowrap">
                              {s.target_date ? `Target: ${s.target_date}` : ""}
                            </span>
                            {statusBadge(s.status)}
                          </div>
                        </div>
                        <p className="text-slate-400 text-sm mt-1">
                          {new Date(s.created_at).toLocaleString("ja-JP")}
                        </p>
                      </div>
                    </Link>
                  ))}
                </div>
                {renderPagination()}
              </>
            )}
          </>
        ) : (
          <>
            {renderFilters()}

            {loading ? (
              <div className="text-center text-slate-400 py-12">読み込み中...</div>
            ) : sharedSessions.length === 0 ? (
              <div className="text-center text-slate-400 py-12 border border-dashed border-slate-700 rounded-xl">
                該当するセッションがありません。
              </div>
            ) : (
              <>
                <div className="space-y-3">
                  {sharedSessions.map((s) => (
                    <Link key={s.id} href={`/dashboard/${s.id}`} prefetch={false}>
                      <div className="bg-slate-800 border border-slate-700 hover:border-blue-500 rounded-xl px-5 py-4 transition-colors cursor-pointer">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{s.title}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-slate-400 whitespace-nowrap">
                              {s.approved_at ? `Approved: ${new Date(s.approved_at).toLocaleDateString("ja-JP")}` : ""}
                            </span>
                            <span className="text-xs text-slate-400 whitespace-nowrap">
                              {s.target_date ? `Target: ${s.target_date}` : ""}
                            </span>
                            {statusBadge(s.status)}
                          </div>
                        </div>
                        <p className="text-slate-400 text-sm mt-1">
                          作成者: {s.created_by_name ?? s.created_by_email ?? "不明"}
                          {" ・ "}
                          {new Date(s.created_at).toLocaleString("ja-JP")}
                        </p>
                      </div>
                    </Link>
                  ))}
                </div>
                {renderPagination()}
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="text-center text-slate-400 py-12">読み込み中...</div>}>
      <DashboardContent />
    </Suspense>
  );
}
