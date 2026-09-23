"use client";
import { use, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createMessage, recordDecision, getSession, saveDraftQuery, saveDraftDecision, approveMessage, rejectMessage, closeSession, deleteSession } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

// AIの推奨に対する判定。UI表示は日本語、保存値(DB)は英語コード。
const AI_RECOMMENDATION_OPTIONS: { value: string; label: string }[] = [
  { value: "adopted", label: "採用" },
  { value: "modified", label: "修正" },
  { value: "rejected", label: "見送り" },
];

interface HpcrdtlMessage {
  id: string;
  session_id: string;
  query?: string | null;
  history: string;
  pro: string[];
  con: string[];
  recommendation: string;
  decision: string | null;
  ai_recommendation_action: string | null;
  reason: string | null;
  target_date: string | null;
  decided_at?: string | null;
  risk_score: number;
  risk_category: string[];
  response_confidence_score: number;
  response_confidence_level: string;
  log: string | null;
  status: string;
  created_at: string;
  approval_status?: string | null;
  approved_by_name?: string | null;
  approved_by_email?: string | null;
  approval_comment?: string | null;
  approved_at?: string | null;
  addendum?: string | null;
  addendum_updated_at?: string | null;
}

export default function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = use(params);
  const router = useRouter();
  const currentUser = useAuthStore((s) => s.user);
  const [query, setQuery] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<HpcrdtlMessage | null>(null);
  const [sessionCreatedBy, setSessionCreatedBy] = useState<string | null>(null);
  const [decision, setDecision] = useState("");
  const [aiRecommendationAction, setAiRecommendationAction] = useState("");
  const [reason, setReason] = useState("");
  const [targetDate, setTargetDate] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    const d = String(now.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  });
  const [recording, setRecording] = useState(false);
  const [decided, setDecided] = useState(false);
  const [sessionStatus, setSessionStatus] = useState<string>("draft");
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [rejectComment, setRejectComment] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [closing, setClosing] = useState(false);
  // 「追加コメントを入れて終了する」を押した後、実際に終了(close)を確定
  // するまでの間、追記入力フォームを表示するための状態。
  const [showFinalizeForm, setShowFinalizeForm] = useState(false);
  const [addendum, setAddendum] = useState("");
  const [actionError, setActionError] = useState("");
  const [viewerIsApprover, setViewerIsApprover] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  // F. セッション共有(read-only): 作成者本人でなければ、組織内の他ユーザーの
  // セッションを閲覧しているということなので、常にread-only表示にする。
  const isOwner = sessionCreatedBy === null || sessionCreatedBy === currentUser?.id;
  const isApprover = viewerIsApprover;
  // 下書きの自動保存: 初回ロード完了前や、サーバーから復元した直後の値では
  // 保存APIを呼びたくないため、ユーザー操作による変更かどうかを追跡する。
  const isRestoring = useRef(true);
  const draftSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSession = async () => {
    try {
      const res = await getSession(sessionId);
      const sessionData = res.data;
      setSessionCreatedBy(sessionData.created_by ?? null);
      setSessionStatus(sessionData.status);
      setViewerIsApprover(Boolean(sessionData.viewer_is_approver));
      const existing = sessionData.messages?.[0] as HpcrdtlMessage | undefined;
      if (existing) {
        setQuery(existing.query ?? "");
        setMessage(existing);
        // decision/reason/target_date は「進行中(未確定)」でも「確定」でも同じ
        // カラムを使うため、値があれば常に復元する。確定済みかどうかは
        // decided_at の有無で判定する。
        if (existing.decision) setDecision(existing.decision);
        if (existing.ai_recommendation_action) setAiRecommendationAction(existing.ai_recommendation_action);
        if (existing.reason) setReason(existing.reason);
        if (existing.target_date) setTargetDate(existing.target_date);
        setDecided(Boolean(existing.decided_at));
        if (existing.addendum) setAddendum(existing.addendum);
      } else if (sessionData.draft_query) {
        // まだ分析前(下書き)の場合、入力途中のクエリを復元
        setQuery(sessionData.draft_query);
      }
    } catch {
      router.push("/dashboard");
    } finally {
      setLoading(false);
      // 復元処理が終わった後の変更のみを自動保存の対象にする
      isRestoring.current = false;
    }
  };

  // D. リロード・再訪問時に、保存済みのクエリ・分析結果・決定内容を復元する。
  // A案: 1セッション=1メッセージのため、messages[0]（あれば）を復元対象とする。
  useEffect(() => {
    fetchSession();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // 下書き入力を1秒デバウンスして自動保存(分析済み・復元直後は保存しない)
  useEffect(() => {
    if (isRestoring.current || message || !isOwner) return;
    if (draftSaveTimer.current) clearTimeout(draftSaveTimer.current);
    draftSaveTimer.current = setTimeout(() => {
      saveDraftQuery(sessionId, query).catch(() => {
        // 自動保存の失敗はユーザー操作を妨げないよう静かに無視する
      });
    }, 1000);
    return () => {
      if (draftSaveTimer.current) clearTimeout(draftSaveTimer.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  // Decision/Reason/Target の入力途中内容も、同様に1秒デバウンスで自動保存する。
  // 分析済み(message あり = セッションは「進行中」)かつ未確定(decided
  // でない)の間だけ対象。「下書き」(分析前・message なし)段階では
  // そもそも message が存在しないため、この自動保存は発火しない。
  const decisionDraftSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (isRestoring.current || !message || decided || !isOwner) return;
    if (decisionDraftSaveTimer.current) clearTimeout(decisionDraftSaveTimer.current);
    decisionDraftSaveTimer.current = setTimeout(() => {
      saveDraftDecision(sessionId, message.id, decision, aiRecommendationAction, reason, targetDate).catch(() => {
        // 自動保存の失敗はユーザー操作を妨げないよう静かに無視する
      });
    }, 1000);
    return () => {
      if (decisionDraftSaveTimer.current) clearTimeout(decisionDraftSaveTimer.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decision, aiRecommendationAction, reason, targetDate]);

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || message || !isOwner) return;
    setAnalyzing(true);
    try {
      const res = await createMessage(sessionId, query.trim());
      setMessage(res.data);
      setSessionStatus("open");
    } catch {
      alert("分析に失敗しました。再度お試しください。");
    } finally {
      setAnalyzing(false);
    }
  };

  // F. セッション共有(read-only): 作成者本人でなければ、組織内の他ユーザーの
  // セッションを閲覧しているということなので、常にread-only表示にする。
  const decisionFieldsComplete = Boolean(
    decision.trim() && aiRecommendationAction && reason.trim() && targetDate
  );

  const handleDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!decisionFieldsComplete || !message || !isOwner) return;
    setRecording(true);
    setActionError("");
    try {
      const res = await recordDecision(sessionId, message.id, decision.trim(), aiRecommendationAction, reason.trim(), targetDate);
      setDecided(true);
      setSessionStatus(res.data.session_status ?? "completed");
    } catch {
      alert("決定の記録に失敗しました。");
    } finally {
      setRecording(false);
    }
  };

  const handleApprove = async () => {
    if (!message) return;
    setApproving(true);
    setActionError("");
    try {
      await approveMessage(sessionId, message.id);
      await fetchSession();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail ?? "承認に失敗しました。");
    } finally {
      setApproving(false);
    }
  };

  const handleReject = async () => {
    if (!message) return;
    setRejecting(true);
    setActionError("");
    try {
      await rejectMessage(sessionId, message.id, rejectComment.trim() || undefined);
      setShowRejectForm(false);
      setRejectComment("");
      await fetchSession();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail ?? "差し戻しに失敗しました。");
    } finally {
      setRejecting(false);
    }
  };

  // 完了(completed)状態のセッションを、追加コメント(addendum)とともに
  // 終了(closed)へ確定させる。何らかの対応を実施した結果として終了させる
  // 操作であるため、追加コメントは必須とする(未入力ではボタンが無効化される)。
  // 以前はボタン押下と同時に即座に終了状態へ遷移していたため、追記を
  // 入力する前にステータスだけ終了してしまう不具合があった。今はコメント
  // 入力後の「終了」押下で、追記の保存とステータス変更を同一リクエストで
  // まとめて行う。
  const handleFinalize = async () => {
    if (!isOwner || !addendum.trim()) return;
    setClosing(true);
    setActionError("");
    try {
      const res = await closeSession(sessionId, addendum.trim());
      setSessionStatus(res.data.status ?? "closed");
      setShowFinalizeForm(false);
      await fetchSession();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail ?? "終了処理に失敗しました。");
    } finally {
      setClosing(false);
    }
  };

  // 削除は基本的に全ての意思決定ログで可能だが、承認済みのものはバック
  // エンド側で拒否される(エラーメッセージを表示する)。「削除してよろしい
  // ですが？」の確認を挟み、再度「削除してOK」を押した場合のみ実行する。
  const handleDelete = async () => {
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteSession(sessionId);
      router.push("/dashboard");
    } catch (err: any) {
      setDeleteError(err?.response?.data?.detail ?? "削除に失敗しました。");
      setShowDeleteConfirm(false);
    } finally {
      setDeleting(false);
    }
  };

  const riskColor = (score: number) => {
    if (score >= 70) return "text-red-400";
    if (score >= 40) return "text-yellow-400";
    return "text-green-400";
  };

  const confidenceColor = (level: string) => {
    const map: Record<string, string> = {
      high: "text-green-400",
      medium: "text-yellow-400",
      low: "text-orange-400",
      insufficient_context: "text-red-400",
    };
    return map[level] ?? "text-slate-400";
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-700 px-6 py-4 flex items-center gap-4">
        <button
          onClick={() => router.push("/dashboard")}
          className="text-slate-400 hover:text-white transition-colors"
        >
          ← 戻る
        </button>
        <h1 className="text-xl font-bold text-blue-400">HPCR-DRTL 分析</h1>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8">
        {loading ? (
          <div className="text-center text-slate-400 py-12">読み込み中...</div>
        ) : (
        <>
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 mb-6">
          <h2 className="font-semibold mb-4">意思決定クエリ</h2>
          {message || !isOwner ? (
            // A案: 分析済みセッションは再分析不可。他人のセッションもread-only。
            <p className="text-slate-300 text-sm leading-relaxed whitespace-pre-wrap">
              {query || "(クエリなし)"}
            </p>
          ) : (
            <form onSubmit={handleAnalyze} className="space-y-3">
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="判断が必要な状況や課題を入力してください..."
                rows={4}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 resize-none"
              />
              <button
                type="submit"
                disabled={analyzing}
                className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 px-6 py-2.5 rounded-lg font-semibold transition-colors"
              >
                {analyzing ? "AI分析中... (数秒かかります)" : "分析開始"}
              </button>
            </form>
          )}
        </div>

        {analyzing && (
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 mb-6 text-center">
            <div className="inline-block w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-slate-400">Gemini AIが分析中です...</p>
          </div>
        )}

        {message && !analyzing && (
          <div className="space-y-4 mb-6">
            {(() => {
              const statusLabel: Record<string, { text: string; cls: string }> = {
                open: { text: "進行中", cls: "bg-slate-700 text-slate-200" },
                awaiting_approval: { text: "承認待ち", cls: "bg-yellow-700 text-yellow-100" },
                completed: { text: "完了", cls: "bg-green-700 text-green-100" },
                // 「下書き」(slate系)との混同を避けるため、落ち着いたトーンの紫に変更。
                closed: { text: "終了", cls: "bg-purple-900 text-purple-200" },
              };
              const s = statusLabel[sessionStatus];
              return s ? (
                <span className={`inline-block text-xs px-3 py-1 rounded-full font-semibold ${s.cls}`}>
                  {s.text}
                </span>
              ) : null;
            })()}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                <p className="text-slate-400 text-sm mb-1">リスクスコア</p>
                <p className={`text-4xl font-bold ${riskColor(message.risk_score)}`}>
                  {message.risk_score}
                  <span className="text-lg text-slate-400">/100</span>
                </p>
                <div className="flex flex-wrap gap-1 mt-2">
                  {message.risk_category.map((c) => (
                    <span key={c} className="text-xs bg-slate-700 px-2 py-0.5 rounded-full">
                      {c}
                    </span>
                  ))}
                </div>
              </div>
              <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                <p className="text-slate-400 text-sm mb-1">信頼度</p>
                <p className={`text-4xl font-bold ${confidenceColor(message.response_confidence_level)}`}>
                  {message.response_confidence_score}
                  <span className="text-lg text-slate-400">/100</span>
                </p>
                <p className={`text-sm mt-1 ${confidenceColor(message.response_confidence_level)}`}>
                  {message.response_confidence_level}
                </p>
              </div>
            </div>

            <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
              <h3 className="font-semibold text-blue-300 mb-2">History — 経緯・文脈</h3>
              <p className="text-slate-300 text-sm leading-relaxed">{message.history}</p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-800 border border-green-800 rounded-2xl p-5">
                <h3 className="font-semibold text-green-400 mb-3">Pro — メリット</h3>
                <ul className="space-y-2">
                  {message.pro.map((p, i) => (
                    <li key={i} className="flex gap-2 text-sm text-slate-300">
                      <span className="text-green-400 mt-0.5">✓</span>
                      <span>{p}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="bg-slate-800 border border-red-900 rounded-2xl p-5">
                <h3 className="font-semibold text-red-400 mb-3">Con — デメリット</h3>
                <ul className="space-y-2">
                  {message.con.map((c, i) => (
                    <li key={i} className="flex gap-2 text-sm text-slate-300">
                      <span className="text-red-400 mt-0.5">✗</span>
                      <span>{c}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="bg-slate-800 border border-blue-700 rounded-2xl p-5">
              <h3 className="font-semibold text-blue-300 mb-2">Recommendation — 推奨事項</h3>
              <p className="text-slate-300 text-sm leading-relaxed">{message.recommendation}</p>
            </div>

            {!decided && isOwner ? (
              <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                <h3 className="font-semibold mb-3">Decision — あなたの決定</h3>
                {message.approval_status === "rejected" && (
                  <div className="bg-orange-900/30 border border-orange-700 rounded-lg px-4 py-3 mb-4">
                    <p className="text-orange-300 text-sm font-semibold mb-1">承認者により差し戻されました</p>
                    {message.approval_comment && (
                      <p className="text-slate-300 text-sm">{message.approval_comment}</p>
                    )}
                    <p className="text-slate-400 text-xs mt-1">
                      Decision・Reason・Targetを必要に応じて修正し、再度Logしてください。
                    </p>
                  </div>
                )}
                <form onSubmit={handleDecision} className="space-y-3">
                  <textarea
                    value={decision}
                    onChange={(e) => setDecision(e.target.value)}
                    placeholder="AIの推奨を参考に、あなたの決定内容をお書きください..."
                    rows={3}
                    className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 resize-none"
                  />
                  <div className="space-y-2">
                    <label className="text-slate-200 text-base font-medium block">
                      Reason — 判断理由
                    </label>
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400 text-sm whitespace-nowrap">AIの推奨を:</span>
                      <select
                        value={aiRecommendationAction}
                        onChange={(e) => setAiRecommendationAction(e.target.value)}
                        className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                      >
                        <option value="">選択してください</option>
                        {AI_RECOMMENDATION_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <textarea
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="あなたの判断理由をお書きください..."
                      rows={3}
                      className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 resize-none"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-slate-400 text-base font-medium block">
                      Target — 実施ターゲット日
                    </label>
                    <input
                      type="date"
                      value={targetDate}
                      min={new Date().toISOString().split("T")[0]}
                      onChange={(e) => setTargetDate(e.target.value)}
                      className="date-input-gray w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                    />
                  </div>
                  <style jsx global>{`
                    .date-input-gray::-webkit-calendar-picker-indicator {
                      filter: invert(64%) sepia(6%) saturate(383%) hue-rotate(179deg) brightness(90%) contrast(87%);
                      cursor: pointer;
                    }
                  `}</style>
                  <div className="space-y-2">
                    <div className="flex gap-3">
                      <button
                        type="submit"
                        disabled={recording || !decisionFieldsComplete}
                        className="bg-green-700 hover:bg-green-600 disabled:bg-slate-600 px-6 py-2.5 rounded-lg font-semibold transition-colors"
                      >
                        {recording ? "記録中..." : "Log - 決定を記録"}
                      </button>
                      <button
                        type="button"
                        onClick={() => router.push("/dashboard")}
                        className="text-slate-400 hover:text-white px-4 py-2.5 transition-colors"
                      >
                        後で決定する
                      </button>
                    </div>
                    {!decisionFieldsComplete && (
                      <p className="text-sm text-yellow-400">上記を全てご入力ください。</p>
                    )}
                  </div>
                </form>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                  <h3 className="font-semibold mb-2">Decision — あなたの決定</h3>
                  <p className="text-slate-300 text-sm leading-relaxed">{decision}</p>
                </div>
                <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                  <h3 className="font-semibold text-slate-200 mb-2">Reason — 判断理由</h3>
                  <p className="text-slate-400 text-sm mb-2">
                    AIの推奨を: {AI_RECOMMENDATION_OPTIONS.find((o) => o.value === aiRecommendationAction)?.label ?? "—"}
                  </p>
                  <p className="text-slate-300 text-sm leading-relaxed">{reason || "—"}</p>
                </div>
                <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                  <h3 className="font-semibold text-slate-400 mb-2">Target — 実施ターゲット日</h3>
                  <p className="text-slate-300 text-sm">{targetDate}</p>
                </div>
                <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                  <h3 className="font-semibold text-slate-400 mb-2">承認者と承認日</h3>
                  <p className="text-slate-300 text-sm">
                    {message.approval_status === "approved" && message.approved_by_name
                      ? `${message.approved_by_name}${
                          message.approved_by_email ? `　${message.approved_by_email}` : ""
                        }${
                          message.approved_at ? `　（${new Date(message.approved_at).toLocaleString("ja-JP")}）` : ""
                        }`
                      : ""}
                  </p>
                </div>
                {decided && isOwner && sessionStatus === "awaiting_approval" && (
                  <div className="bg-yellow-900/30 border border-yellow-700 rounded-2xl p-5 text-center space-y-3">
                    <p className="text-yellow-300 font-semibold text-lg">承認待ちです</p>
                    <p className="text-slate-300 text-sm leading-relaxed">
                      承認者の承認を得ましたら完了となります。又は、差戻しがあった場合は、あなたの決定と判断理由と実施ターゲットについて必要な修正を行った後、再度Logを実施いただく必要があります。
                    </p>
                  </div>
                )}

                {sessionStatus === "awaiting_approval" && isApprover && (
                  <div className="bg-slate-800 border border-yellow-700 rounded-2xl p-5 space-y-3">
                    <h3 className="font-semibold text-yellow-300">承認者としての操作</h3>
                    {actionError && <p className="text-red-400 text-sm">{actionError}</p>}
                    {!showRejectForm ? (
                      <div className="flex gap-3">
                        <button
                          onClick={handleApprove}
                          disabled={approving}
                          className="bg-green-700 hover:bg-green-600 disabled:bg-slate-600 px-6 py-2.5 rounded-lg font-semibold transition-colors"
                        >
                          {approving ? "処理中..." : "承認する"}
                        </button>
                        <button
                          onClick={() => setShowRejectForm(true)}
                          className="bg-slate-700 hover:bg-slate-600 px-6 py-2.5 rounded-lg font-semibold transition-colors"
                        >
                          差し戻す
                        </button>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <textarea
                          value={rejectComment}
                          onChange={(e) => setRejectComment(e.target.value)}
                          placeholder="差し戻し理由(任意)"
                          rows={2}
                          className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500 resize-none"
                        />
                        <div className="flex gap-3">
                          <button
                            onClick={handleReject}
                            disabled={rejecting}
                            className="bg-orange-700 hover:bg-orange-600 disabled:bg-slate-600 px-6 py-2.5 rounded-lg font-semibold transition-colors"
                          >
                            {rejecting ? "処理中..." : "差し戻しを確定"}
                          </button>
                          <button
                            onClick={() => setShowRejectForm(false)}
                            className="text-slate-400 hover:text-white px-4 py-2.5 transition-colors"
                          >
                            キャンセル
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {decided && isOwner && sessionStatus === "completed" && !showFinalizeForm && (
                  <div className="bg-green-900 border border-green-700 rounded-2xl p-5 text-center space-y-3">
                    <p className="text-green-300 font-semibold text-lg">✓ 決定が記録されました</p>
                    {message.approved_by_name && (
                      <p className="text-green-200 text-sm">
                        承認者: {message.approved_by_name}
                        {message.approved_by_email ? `（${message.approved_by_email}）` : ""} さんが承認しました
                      </p>
                    )}
                    <div className="flex justify-center gap-4">
                      <button
                        onClick={() => router.push("/dashboard")}
                        className="text-sm text-slate-400 hover:text-white transition-colors"
                      >
                        ダッシュボードに戻る
                      </button>
                      <button
                        onClick={() => setShowFinalizeForm(true)}
                        className="text-sm text-slate-300 hover:text-white transition-colors underline"
                      >
                        追加コメントを入れて終了する
                      </button>
                    </div>
                    {actionError && <p className="text-red-400 text-sm">{actionError}</p>}
                  </div>
                )}

                {decided && isOwner && sessionStatus === "completed" && showFinalizeForm && (
                  <div className="bg-slate-800 border border-slate-600 rounded-2xl p-5 space-y-3">
                    <p className="text-slate-300 font-semibold text-center">終了時の追加コメント</p>
                    <div className="space-y-2">
                      <textarea
                        value={addendum}
                        onChange={(e) => setAddendum(e.target.value)}
                        placeholder="追記を入力..."
                        rows={3}
                        autoFocus
                        className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500 resize-none"
                      />
                      <div className="flex justify-center gap-4">
                        <button
                          onClick={() => setShowFinalizeForm(false)}
                          disabled={closing}
                          className="text-sm text-slate-400 hover:text-white transition-colors disabled:opacity-50"
                        >
                          キャンセル
                        </button>
                        <button
                          onClick={handleFinalize}
                          disabled={closing || !addendum.trim()}
                          className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 px-5 py-2 rounded-lg text-sm font-semibold transition-colors"
                        >
                          {closing ? "処理中..." : "終了"}
                        </button>
                      </div>
                      {actionError && <p className="text-red-400 text-sm">{actionError}</p>}
                    </div>
                  </div>
                )}

                {sessionStatus === "closed" && (
                  <>
                    {message.addendum && (
                      <div className="bg-slate-800 border border-slate-600 rounded-2xl p-5 space-y-3">
                        <p className="text-slate-300 font-semibold text-center">終了時の追加コメント</p>
                        <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
                          <p className="text-xs text-slate-500 mb-1">
                            追記{message.addendum_updated_at ? `(${new Date(message.addendum_updated_at).toLocaleString("ja-JP")})` : ""}
                          </p>
                          <p className="text-slate-300 text-sm whitespace-pre-wrap">{message.addendum}</p>
                        </div>
                      </div>
                    )}
                    <div className="bg-purple-950 border border-purple-800 rounded-2xl p-5 text-center space-y-3">
                      <p className="text-purple-200 font-semibold text-lg">✓ 終了時の追加コメントが記録されました</p>
                      <button
                        onClick={() => router.push("/dashboard")}
                        className="text-sm text-slate-400 hover:text-white transition-colors"
                      >
                        ダッシュボードに戻る
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {isOwner && !loading && (
          <div className="mt-8 border-t border-slate-700 pt-6">
            {!showDeleteConfirm ? (
              <button
                onClick={() => {
                  setDeleteError("");
                  setShowDeleteConfirm(true);
                }}
                className="text-sm text-red-400 hover:text-red-300 transition-colors"
              >
                この意思決定ログの削除
              </button>
            ) : (
              <div className="bg-red-950/30 border border-red-800 rounded-xl p-4 space-y-3">
                <p className="text-red-300 text-sm">削除してよろしいですが？</p>
                <div className="flex gap-3">
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="bg-red-700 hover:bg-red-600 disabled:bg-slate-600 px-5 py-2 rounded-lg text-sm font-semibold transition-colors"
                  >
                    {deleting ? "削除中..." : "削除してOK"}
                  </button>
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    disabled={deleting}
                    className="text-slate-400 hover:text-white px-4 py-2 text-sm transition-colors disabled:opacity-50"
                  >
                    キャンセル
                  </button>
                </div>
              </div>
            )}
            {deleteError && <p className="text-red-400 text-sm mt-2">{deleteError}</p>}
          </div>
        )}
        </>
        )}
      </main>
    </div>
  );
}