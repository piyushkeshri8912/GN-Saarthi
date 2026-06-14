"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect root to chat page (AuthGuard will force login redirect if needed)
    router.replace("/chat");
  }, [router]);

  return null;
}
