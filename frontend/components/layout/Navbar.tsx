"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "../../store/authStore";
import { signOut } from "firebase/auth";
import { auth } from "../../lib/firebase";
import { MessageSquare, LayoutDashboard, Bell, Calendar, Shield, LogOut, Menu, X, Sun, Moon, FileText } from "lucide-react";
import { useState, useEffect } from "react";
import { useChatbotStore } from "../../store/chatbotStore";
import Image from "next/image";

export default function Navbar() {
  const pathname = usePathname();
  const { user, clear } = useAuthStore();
  
  const logout = async () => {
    try {
      await signOut(auth);
      clear();
    } catch (error) {
      console.error("Logout failed:", error);
    }
  };
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [windowWidth, setWindowWidth] = useState(1200); // safe SSR fallback
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    setIsMounted(true);
    setWindowWidth(window.innerWidth);
    
    // Read theme preference from localStorage or default to light mode
    const savedTheme = localStorage.getItem("theme") as "light" | "dark" | null;
    const initialTheme = savedTheme || "light";
    setTheme(initialTheme);
    if (initialTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }

    const handleResize = () => {
      setWindowWidth(window.innerWidth);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("theme", nextTheme);
    if (nextTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  const { isOpen, width: chatbotWidth } = useChatbotStore();
  
  // Collapse navigation if effective width (browser width minus chatbot) drops below 850px
  const isMobileView = isMounted && (isOpen ? windowWidth - chatbotWidth : windowWidth) < 850;

  // Auto-close mobile menu if user switches to desktop view
  useEffect(() => {
    if (!isMobileView) {
      setMobileMenuOpen(false);
    }
  }, [isMobileView]);

  if (!user) return null;

  const navItems = [
    { name: "Chat", href: "/chat", icon: MessageSquare },
    { name: "Reference Docs", href: "/reference-docs", icon: FileText },
  ];

  const isAdmin = user.role === "admin";
  const isActive = (href: string) => pathname === href;

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-zinc-200 dark:border-zinc-800 bg-white/85 dark:bg-zinc-950/80 backdrop-blur-md transition-colors duration-200">
      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          
          {/* Logo Brand */}
          <div className="flex items-center gap-6">
            <Link href="/chat" className="flex items-center gap-2.5">
              <div className="relative h-8 w-8 overflow-hidden rounded-lg">
                <Image
                  src="/logo.png"
                  alt="IITGN Logo"
                  fill
                  className="object-contain"
                />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-bold tracking-tight text-zinc-900 dark:text-white leading-tight">
                  GN Saarthi
                </span>
                <span className="text-[9px] uppercase tracking-wider text-slate-500 font-bold -mt-0.5">
                  IIT Gandhinagar
                </span>
              </div>
            </Link>
 
            {/* Desktop Navigation Links */}
            <div className={`${isMobileView ? "hidden" : "flex"} items-center gap-1.5`}>
              {navItems.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.href);
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold tracking-wide uppercase transition-all duration-200 cursor-pointer ${
                      active
                        ? "bg-zinc-900 text-white border border-zinc-900 dark:bg-zinc-800/40 dark:text-white dark:border-zinc-700/50"
                        : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-slate-400 dark:hover:bg-slate-800/40 dark:hover:text-slate-200"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {item.name}
                  </Link>
                );
              })}

              {isAdmin && (
                <Link
                  href="/admin/upload"
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold tracking-wide uppercase transition-all duration-200 cursor-pointer ${
                    isActive("/admin/upload") || pathname.startsWith("/admin/")
                      ? "bg-zinc-900 text-white border border-zinc-900 dark:bg-zinc-800/40 dark:text-white dark:border-zinc-700/50"
                      : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-slate-400 dark:hover:bg-slate-800/40 dark:hover:text-slate-200"
                  }`}
                >
                  <Shield className="h-3.5 w-3.5 text-zinc-400" />
                  Admin Console
                </Link>
              )}
            </div>
          </div>

          {/* User Profile & Actions */}
          <div className={`${isMobileView ? "hidden" : "flex"} items-center gap-4`}>
            {/* Theme Toggle Button */}
            <button
              onClick={toggleTheme}
              className="rounded-lg p-2 border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer text-zinc-600 dark:text-zinc-300"
              title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>

            <div className="flex flex-col items-end">
              <span className="text-xs font-bold text-zinc-800 dark:text-slate-350">{user.email.split("@")[0]}</span>
              <span
                className={`mt-0.5 rounded px-1.5 py-0.5 text-[8px] font-black uppercase tracking-widest ${
                  isAdmin
                    ? "bg-zinc-900 text-white border border-zinc-900 dark:bg-zinc-800/40 dark:text-white dark:border-zinc-700/50"
                    : "bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-slate-800 dark:text-slate-450 dark:border-slate-700/40"
                }`}
              >
                {user.role}
              </span>
            </div>

            <button
              onClick={logout}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-zinc-200 transition-all duration-200 cursor-pointer"
            >
              <LogOut className="h-3.5 w-3.5" />
              Logout
            </button>
          </div>

          {/* Mobile Menu Button Section */}
          <div className={`${isMobileView ? "flex" : "hidden"} items-center gap-2`}>
            {/* Theme Toggle Button */}
            <button
              onClick={toggleTheme}
              className="rounded-lg p-2 border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer text-zinc-600 dark:text-zinc-300"
              title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>

            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="inline-flex items-center justify-center rounded-lg p-2 text-zinc-600 dark:text-slate-450 hover:bg-zinc-100 dark:hover:bg-slate-800/50 hover:text-zinc-900 dark:hover:text-slate-200 cursor-pointer"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && isMobileView && (
        <div className="mt-2 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/90 backdrop-blur-xl px-2 pt-2 pb-3 space-y-1 shadow-2xl transition-colors duration-200">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            return (
              <Link
                key={item.name}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-semibold tracking-wide uppercase transition-all ${
                  active
                    ? "bg-zinc-900 text-white border border-zinc-900 dark:bg-zinc-800/40 dark:text-white dark:border-zinc-700/50"
                    : "text-zinc-600 dark:text-slate-400 hover:bg-zinc-100 dark:hover:bg-slate-800/40 hover:text-zinc-900 dark:hover:text-slate-200"
                }`}
              >
                <Icon className="h-4 w-4" />
                {item.name}
              </Link>
            );
          })}

          {isAdmin && (
            <Link
              href="/admin/upload"
              onClick={() => setMobileMenuOpen(false)}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-semibold tracking-wide uppercase transition-all ${
                isActive("/admin/upload")
                  ? "bg-zinc-900 text-white border border-zinc-900 dark:bg-zinc-800/40 dark:text-white dark:border-zinc-700/50"
                  : "text-zinc-600 dark:text-slate-400 hover:bg-zinc-100 dark:hover:bg-slate-800/40 hover:text-zinc-900 dark:hover:text-slate-200"
              }`}
            >
              <Shield className="h-4 w-4 text-zinc-400" />
              Admin Console
            </Link>
          )}

          <div className="my-2 border-t border-zinc-200 dark:border-zinc-800"></div>

          <div className="flex items-center justify-between px-3 py-1">
            <div className="flex flex-col">
              <span className="text-xs font-bold text-zinc-800 dark:text-slate-350 truncate max-w-[180px]">
                {user.email}
              </span>
              <span className="text-[10px] text-zinc-500 uppercase font-black">{user.role}</span>
            </div>
            <button
              onClick={() => {
                setMobileMenuOpen(false);
                logout();
              }}
              className="flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-600 dark:text-slate-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-slate-200 transition-all"
            >
              <LogOut className="h-3.5 w-3.5" />
              Logout
            </button>
          </div>
        </div>
      )}
    </nav>
  );
}
