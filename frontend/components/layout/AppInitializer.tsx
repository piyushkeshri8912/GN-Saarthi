"use client";

import { useEffect } from "react";
import { onAuthStateChanged, signOut as firebaseSignOut } from "firebase/auth";
import { auth } from "../../lib/firebase";
import api from "../../lib/api";
import { useAuthStore } from "../../store/authStore";
import { User } from "../../types";
import AuthGuard from "../auth/AuthGuard";
// GlobalChatbot import removed for chatbot-only dedicated layout

export default function AppInitializer({ children }: { children: React.ReactNode }) {
  const { user, setUser, setLoading, clear } = useAuthStore();

  useEffect(() => {
    // Listen to Firebase Authentication state updates exactly ONCE at the application root level
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        setLoading(true);
        try {
          // Token is dynamically injected via Axios interceptors in api.ts
          const response = await api.post<User>("/auth/verify");
          setUser(response.data);
        } catch (error: any) {
          console.error("Backend auth verification failed:", error);
          const errMsg = error?.response?.data?.detail || "Access restricted to @iitgn.ac.in accounts.";
          await firebaseSignOut(auth);
          clear();
          useAuthStore.getState().setError(errMsg);
        }
      } else {
        clear();
      }
    });

    return () => unsubscribe();
  }, [setUser, setLoading, clear]);

  return (
    <AuthGuard>
      <div className="flex h-screen w-screen overflow-hidden bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 transition-colors duration-200">
        {/* Main page content area */}
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-y-auto">
          {children}
        </div>
      </div>
    </AuthGuard>
  );
}
