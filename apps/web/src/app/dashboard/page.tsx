"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSessions, createSession, logout } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import Link from "next/link";

interface Session {
  id: string;
  title: string;
  status: string;
  created_at: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clearAuth);  
  const [sessions, setSessions] = useState<Session[]>([]);
  const [newTitle, setNewTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchSessions();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const res = await getSessions();
      setSessions(res.data);
    } catch {
      router.push("/");
    } finally {
      setLoading(false);
    }
  };

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

  const handleLogout = async () => {
  await logout();
  clearAuth();
  router.push("/");
  };

  const statusBadge = (status: string) => {
    const map: Record<string, string> = {
      draft: "bg-slate-600 text-slate-200",
      open: "bg-blue-600 text-white",
      closed: "bg-green-700 text-white",
    };
    const label: Record<string, string> = {
      draft: "下書き",
      open: "進行中",
      closed: "完了",
    };
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full ${map[status] ?? "bg-slate-600"}`}>
        {label[status] ?? status}
      </span>
    );
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-700 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold text-blue-400">Openisec HPCR-DRTL</h1>
        <div className="flex items-center gap-4">
          <span className="text-slate-400 text-sm">{user?.email}</span>
          <button
            onClick={handleLogout}
            className="text-sm text-slate-400 hover:text-white transition-colors"
          >
            ログアウト
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

        {loading ? (
          <div className="text-center text-slate-400 py-12">読み込み中...</div>
        ) : sessions.length === 0 ? (
          <div className="text-center text-slate-400 py-12 border border-dashed border-slate-700 rounded-xl">
            セッションがまだありません。上から新しいセッションを作成してください。
          </div>
        ) : (
          <div className="space-y-3">
            {sessions.map((s) => (
              <Link key={s.id} href={`/dashboard/${s.id}`}>
                <div className="bg-slate-800 border border-slate-700 hover:border-blue-500 rounded-xl px-5 py-4 transition-colors cursor-pointer">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{s.title}</span>
                    {statusBadge(s.status)}
                  </div>
                  <p className="text-slate-400 text-sm mt-1">
                    {new Date(s.created_at).toLocaleString("ja-JP")}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
