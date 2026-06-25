"use client";
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { createMessage, recordDecision } from "@/lib/api";
import Link from "next/link";

interface HpcrdtlMessage {
  id: string;
  session_id: string;
  history: string;
  pro: string[];
  con: string[];
  recommendation: string;
  decision: string | null;
  reason: string | null;
  target_date: string | null;
  risk_score: number;
  risk_category: string[];
  response_confidence_score: number;
  response_confidence_level: string;
  log: string | null;
  status: string;
  created_at: string;
}

export default function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = use(params);
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [message, setMessage] = useState<HpcrdtlMessage | null>(null);
  const [decision, setDecision] = useState("");
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

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setAnalyzing(true);
    setMessage(null);
    setDecided(false);
    try {
      const res = await createMessage(sessionId, query.trim());
      setMessage(res.data);
    } catch {
      alert("分析に失敗しました。再度お試しください。");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!decision.trim() || !message) return;
    setRecording(true);
    try {
      await recordDecision(sessionId, message.id, decision.trim(), reason.trim() || undefined, targetDate);
      setDecided(true);
    } catch {
      alert("決定の記録に失敗しました。");
    } finally {
      setRecording(false);
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
        <Link href="/dashboard" className="text-slate-400 hover:text-white transition-colors">
          ← 戻る
        </Link>
        <h1 className="text-xl font-bold text-blue-400">HPCR-DRTL 分析</h1>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8">
        <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 mb-6">
          <h2 className="font-semibold mb-4">意思決定クエリ</h2>
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
        </div>

        {analyzing && (
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 mb-6 text-center">
            <div className="inline-block w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-slate-400">Gemini AIが分析中です...</p>
          </div>
        )}

        {message && !analyzing && (
          <div className="space-y-4 mb-6">
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

            {!decided ? (
              <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                <h3 className="font-semibold mb-3">Decision — あなたの決定</h3>
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
                    <textarea
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="AIの推奨を採用・修正・見送りした、あなたの判断理由をお書きください..."
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
                      className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                    />
                  </div>
                  <div className="flex gap-3">
                    <button
                      type="submit"
                      disabled={recording}
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
                  <p className="text-slate-300 text-sm leading-relaxed">{reason || "—"}</p>
                </div>
                <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5">
                  <h3 className="font-semibold text-slate-400 mb-2">Target — 実施ターゲット日</h3>
                  <p className="text-slate-300 text-sm">{targetDate}</p>
                </div>
                <div className="bg-green-900 border border-green-700 rounded-2xl p-5 text-center">
                  <p className="text-green-300 font-semibold text-lg">✓ 決定が記録されました</p>
                  <button
                    onClick={() => router.push("/dashboard")}
                    className="mt-3 text-sm text-slate-400 hover:text-white transition-colors"
                  >
                    ダッシュボードに戻る
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}