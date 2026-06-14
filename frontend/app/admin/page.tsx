"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect overview to the upload/document-management page
    router.replace("/admin/upload");
  }, [router]);

  return null;
}
