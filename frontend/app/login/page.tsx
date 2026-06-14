"use client";

import { useState, useEffect } from "react";
import { signInWithPopup } from "firebase/auth";
import { auth, googleProvider } from "../../lib/firebase";
import { useRouter } from "next/navigation";
import { useAuthStore } from "../../store/authStore";
import { Shield, Sparkles, HelpCircle, ArrowRight } from "lucide-react";
import Image from "next/image";

export default function LoginPage() {
  const { user, loading, error, setError } = useAuthStore();
  const [signingIn, setSigningIn] = useState(false);
  const router = useRouter();

  useEffect(() => {
    // If user is already authenticated, direct to chat
    if (user && !loading) {
      router.replace("/chat");
    }
  }, [user, loading, router]);

  const handleGoogleSignIn = async () => {
    setError(null);
    setSigningIn(true);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err: any) {
      console.error("Sign in failed:", err);
      if (err?.code === "auth/popup-closed-by-user" || err?.message?.includes("popup-closed-by-user")) {
        setSigningIn(false);
        return;
      }
      setError("Sign-in failed. Please verify your internet connection and try again.");
      setSigningIn(false);
    }
  };

  if (loading) {
    return null;
  }

  return (
    <div className="relative h-full flex flex-col justify-between bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 overflow-hidden font-sans transition-colors duration-200">
      {/* Top Corporate Branding Header */}
      <header className="w-full border-b border-zinc-200 dark:border-zinc-800 bg-white/60 dark:bg-zinc-950/60 backdrop-blur-md px-6 py-4 z-10 transition-colors">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative h-9 w-9 overflow-hidden rounded-lg">
              <Image
                src="/logo.png"
                alt="IITGN Logo"
                fill
                className="object-contain"
              />
            </div>
            <div>

              <span className="text-sm font-bold tracking-tight text-zinc-900 dark:text-white -mt-0.5 block">
                GN Saarthi Portal
              </span>
              <span className="text-xs uppercase tracking-widest text-zinc-500 font-bold block">
                IIT Gandhinagar
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Grid Body */}
      <main className="flex-1 overflow-y-auto flex items-center justify-center py-6 sm:py-12 px-6 sm:px-12 max-w-7xl mx-auto w-full z-10 gap-16">
               {/* Left Columns - Hero Info Panel (Visible on large screens) */}
        <div className="hidden lg:flex flex-col justify-center max-w-lg space-y-6 flex-1">
          <div className="space-y-4">
            <h2 className="text-4xl font-extrabold tracking-tight text-zinc-900 dark:text-white leading-tight">
              Welcome to GN Saarthi
            </h2>
            <p className="text-zinc-600 dark:text-slate-400 text-sm leading-relaxed">
              Get answers to all your queries instantly using the GN Saarthi chatbot.
            </p>
          </div>

          {/* Generated Campus Graphic Frame */}
          <div className="relative h-64 w-full rounded-2xl border border-zinc-200 dark:border-zinc-800 overflow-hidden shadow-2xl bg-zinc-900">
            <Image
              src="/login_hero.jpg"
              alt="IITGN Campus Illustration"
              fill
              className="object-cover transition-transform duration-500"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-zinc-50 dark:from-zinc-950 via-transparent to-transparent"></div>
          </div>
        </div>

        {/* Right Column - Premium Login Box */}
        <div className="w-full max-w-md flex-1 flex flex-col gap-6">
          {/* Mobile Screen Header Intro (Visible only on mobile/tablet below lg) */}
          <div className="block lg:hidden space-y-2.5">
            <h2 className="text-2xl font-extrabold tracking-tight text-zinc-900 dark:text-white leading-tight">
              Welcome to GN Saarthi
            </h2>
            <p className="text-sm text-zinc-600 dark:text-slate-400 leading-relaxed">
              Get answers to all your queries instantly using the GN Saarthi chatbot.
            </p>
          </div>

          {/* Mobile Hero Image (Visible only on mobile/tablet below lg) */}
          <div className="block lg:hidden relative h-48 w-full rounded-2xl border border-zinc-200 dark:border-zinc-800 overflow-hidden shadow-lg bg-zinc-900">
            <Image
              src="/login_hero.jpg"
              alt="IITGN Campus Illustration"
              fill
              className="object-cover"
              priority
            />
            <div className="absolute inset-0 bg-gradient-to-t from-zinc-955/55 via-transparent to-transparent"></div>
          </div>

          <div className="relative rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/40 dark:bg-zinc-900/30 p-8 backdrop-blur-xl shadow-2xl overflow-hidden transition-colors">
            {/* Top decorative gradient bar */}
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-zinc-800 via-zinc-400 to-zinc-950"></div>

            <div className="flex flex-col items-center text-center">
              <h3 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">
                Log In to access
              </h3>

              <div className="my-6 w-full border-t border-zinc-200 dark:border-zinc-800"></div>

              {error && (
                <div className="mb-6 w-full rounded-xl border border-red-500/20 bg-red-500/10 p-3.5 text-left text-xs font-medium text-red-400">
                  <span className="font-bold block uppercase tracking-wide text-[10px] text-red-500 mb-0.5">Access Authorization Warning</span>
                  {error}
                </div>
              )}

              <button
                onClick={handleGoogleSignIn}
                disabled={signingIn}
                className="group relative flex w-full items-center justify-center gap-3 rounded-xl bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-800 dark:hover:bg-zinc-700 py-3.5 px-4 text-sm font-semibold text-white shadow-lg shadow-zinc-950/20 dark:shadow-zinc-950/40 transition-all duration-200 active:scale-[0.98] disabled:opacity-50 cursor-pointer border border-zinc-950 dark:border-zinc-700"
              >
                {signingIn ? (
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white"></div>
                ) : (
                  <>
                    <svg className="h-5 w-5 fill-current text-white" viewBox="0 0 24 24">
                      <path d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114-3.524 0-6.386-2.862-6.386-6.386 0-3.524 2.862-6.386 6.386-6.386 1.77 0 3.324.72 4.453 1.87l3.18-3.18C19.663 2.517 16.143 1 12.24 1 6.033 1 1 6.033 1 12.24s5.033 11.24 11.24 11.24c5.897 0 10.867-4.23 10.867-11.24 0-.693-.075-1.35-.195-1.955H12.24z" />
                    </svg>
                    Continue with Google Auth
                  </>
                )}
              </button>

              <div className="mt-8 flex items-center justify-center gap-2 rounded-xl bg-zinc-100 dark:bg-zinc-950/40 border border-zinc-200 dark:border-zinc-800 p-3.5 text-zinc-500 transition-colors">
                <Shield className="h-4 w-4 shrink-0 text-zinc-500 dark:text-zinc-400" />
                <span className="text-[10px] text-zinc-650 dark:text-slate-400 font-semibold tracking-wide text-left leading-normal">
                  Access to @iitgn.ac.in domain only
                </span>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer Branding */}
      <footer className="w-full border-t border-zinc-200 dark:border-zinc-800 bg-white/40 dark:bg-zinc-950/40 py-6 text-center text-xs text-zinc-500 dark:text-zinc-400 z-10 px-4 transition-colors">
        <div className="mx-auto max-w-7xl flex flex-col sm:flex-row sm:items-center sm:justify-center gap-4">
          <p>© 2026 IIT Gandhinagar. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
