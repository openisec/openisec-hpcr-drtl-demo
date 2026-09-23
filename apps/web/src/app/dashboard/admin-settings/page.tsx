"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuthStore } from "@/store/auth";
import { getOrganizations } from "@/lib/api";
import RiskThresholdSection from "./RiskThresholdSection";
import OrganizationSection from "./OrganizationSection";
import MembersSection from "./MembersSection";

interface OrgRow {
  id: string;
  name: string;
  is_active: boolean;
  risk_score_threshold: number;
  is_personal?: boolean;
}

export default function AdminSettingsPage() {
  const user = useAuthStore((s) => s.user);
  const isPlatformAdmin = !!user?.is_platform_admin;

  // 組織一覧はこのページで一度だけ取得し、各セクションへpropsで渡す。
  // 以前はリスクスコア閾値設定・組織管理・メンバー管理の3コンポーネントが
  // それぞれ個別にGET /auth/organizationsを呼んでおり、同じデータを3重に
  // 取得していた(admin-settings画面が重く感じる一因になっていた)。
  const [orgs, setOrgs] = useState<OrgRow[]>([]);
  const [orgsLoading, setOrgsLoading] = useState(true);

  const fetchOrgs = useCallback(async () => {
    setOrgsLoading(true);
    try {
      const res = await getOrganizations();
      setOrgs(res.data.organizations);
    } finally {
      setOrgsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrgs();
  }, [fetchOrgs]);

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
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-2">管理設定</h1>
        </div>

        <RiskThresholdSection orgs={orgs} loading={orgsLoading} onOrgsChanged={fetchOrgs} />
        {isPlatformAdmin && (
          <OrganizationSection orgs={orgs} loading={orgsLoading} onOrgsChanged={fetchOrgs} />
        )}
        <MembersSection orgOptions={orgs} />
      </main>
    </div>
  );
}
