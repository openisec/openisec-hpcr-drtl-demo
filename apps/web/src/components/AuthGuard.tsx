"use client";
import { getMe, hasSessionFlag, clearSessionFlag } from "@/lib/api";
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth";

const PUBLIC_PATHS = ["/", "/register", "/password-reset", "/disclaimer", "/privacy"];

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, mustChangePassword, hydrated, setUser, setHydrated } = useAuthStore();

  useEffect(() => {
    if (hydrated) return;

    // ログイン試行の形跡が無ければ、/auth/me を叩かずに未ログイン扱いにする。
    // (HttpOnly Cookieのため実際の有効性はJSから直接確認できないが、
    //  一度もログインしていない/明示的にログアウト済みの場合は、
    //  無駄な401往復とConsoleエラー表示を避けられる)
    if (!hasSessionFlag()) {
      setHydrated(true);
      return;
    }

    getMe()
      .then((res) => setUser(res.data))
      .catch(() => {
        // Cookieが無効/期限切れ: 未ログイン状態として扱い、フラグも消しておく
        clearSessionFlag();
      })
      .finally(() => setHydrated(true));
  }, [hydrated, setHydrated]);

  useEffect(() => {
    if (!hydrated) return;

    const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));

    if (!user) {
      if (!isPublic) {
        const next = encodeURIComponent(pathname);
        router.replace(`/?next=${next}`);
      }
      return;
    }
    if (mustChangePassword) {
      if (pathname !== "/change-password") router.replace("/change-password");
      return;
    }
    if (pathname === "/change-password") {
      router.replace("/dashboard");
    }
  }, [user, mustChangePassword, hydrated, pathname, router]);

  return <>{children}</>;
}