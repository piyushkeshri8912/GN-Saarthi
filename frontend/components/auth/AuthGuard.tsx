"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuthStore } from "../../store/authStore";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user && pathname !== "/login") {
      router.replace("/login");
    }
  }, [user, loading, router, pathname]);

  if (loading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-radial from-slate-900 to-slate-950">
        <div className="flex flex-col items-center gap-4">
          {/* Custom Sleek Spinner */}
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-slate-700 border-t-cyan-500"></div>
          <p className="text-sm font-medium tracking-wide text-slate-400">Loading GN Saarthi...</p>
        </div>
      </div>
    );
  }

  // If not loading and no user, do not render children during redirect
  if (!user && pathname !== "/login") {
    return null;
  }

  return <>{children}</>;
}
