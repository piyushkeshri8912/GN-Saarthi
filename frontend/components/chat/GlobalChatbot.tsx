"use client";

import { useState, useEffect } from "react";
import { MessageSquare, X, Bot, Sparkles } from "lucide-react";
import ChatWindow from "./ChatWindow";
import { useChat } from "../../hooks/useChat";
import { useChatbotStore } from "../../store/chatbotStore";

export default function GlobalChatbot() {
  const { isOpen, setIsOpen, width, setWidth } = useChatbotStore();
  const [isResizing, setIsResizing] = useState(false);
  const { messages, loading, sendMessage, clearChat } = useChat();
  const [windowWidth, setWindowWidth] = useState(1200);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
    setWindowWidth(window.innerWidth);
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const isMobile = isMounted && windowWidth < 768;

  const startResizing = (mouseDownEvent: React.MouseEvent) => {
    if (isMobile) return;
    mouseDownEvent.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    if (!isResizing || isMobile) return;

    const handleMouseMove = (mouseMoveEvent: MouseEvent) => {
      // Calculate new width: since the panel is right-aligned, width is window width minus mouse X
      const newWidth = window.innerWidth - mouseMoveEvent.clientX;
      
      // Enforce min and max width constraints
      const minWidth = 320;
      const maxWidth = Math.min(800, window.innerWidth * 0.8);
      
      if (newWidth >= minWidth && newWidth <= maxWidth) {
        setWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing, isMobile, setWidth]);

  return (
    <>
      {/* Floating Toggle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-tr from-zinc-700 to-zinc-900 text-white shadow-lg shadow-zinc-950/40 border border-zinc-700/50 transition-transform duration-200 hover:scale-105 active:scale-95 cursor-pointer group"
          title="Open GN Saarthi Assistant"
        >
          {/* Pulsing Outer Glow */}
          <span className="absolute -inset-0.5 animate-ping rounded-full bg-zinc-800/30 opacity-75"></span>
          <MessageSquare className="relative h-6 w-6 group-hover:rotate-6 transition-transform" />
        </button>
      )}

      {/* Sidebar Panel Container */}
      <div
        className={`fixed inset-y-0 right-0 z-50 md:relative md:inset-auto md:h-screen bg-white dark:bg-zinc-900/95 border-zinc-200 dark:border-zinc-800 backdrop-blur-xl flex flex-col overflow-hidden shrink-0 transition-colors duration-200 ${
          isOpen ? "border-l shadow-2xl" : ""
        } ${
          isResizing ? "" : "transition-[width] duration-300 ease-out"
        }`}
        style={{
          width: isOpen ? (isMobile ? "100vw" : `${width}px`) : "0px",
        }}
      >
        {/* Resize Handle */}
        {isOpen && !isMobile && (
          <div
            onMouseDown={startResizing}
            className={`absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-zinc-700/40 active:bg-zinc-700/60 transition-colors z-50 group flex items-center justify-center ${
              isResizing ? "bg-zinc-700/50" : "bg-transparent"
            }`}
            title="Drag to resize"
          >
            {/* Visual handle indicator */}
            <div className="w-[2px] h-8 rounded-full bg-zinc-300 dark:bg-zinc-700 group-hover:bg-zinc-500 dark:group-hover:bg-zinc-400 transition-colors" />
          </div>
        )}

        {/* Chatbot Content */}
        {isOpen && (
          <div className="flex flex-col h-full w-full min-w-[320px]">
            {/* Sidebar Header */}
            <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950/40 px-4 py-2.5 shrink-0 transition-colors duration-200">
              <div className="flex items-center gap-3">
                <div className="flex h-7.5 w-7.5 items-center justify-center rounded-xl bg-zinc-100 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-700/30 text-zinc-800 dark:text-white">
                  <Bot className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-zinc-900 dark:text-white flex items-center gap-1.5 font-display">
                    GN Saarthi Assistant <Sparkles className="h-3.5 w-3.5 text-zinc-500 dark:text-zinc-400" />
                  </h3>
                  <span className="text-[9px] uppercase tracking-wider text-zinc-500 dark:text-slate-500 font-bold block -mt-0.5">
                    IITGN Portal Companion
                  </span>
                </div>
              </div>

              {/* Header Controls */}
              <div className="flex items-center gap-3">
                {messages.length > 0 && (
                  <button
                    onClick={clearChat}
                    className="rounded bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-950/60 border border-zinc-200 dark:border-zinc-800 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200 transition-colors"
                  >
                    Reset Chat
                  </button>
                )}
                <button
                  onClick={() => setIsOpen(false)}
                  className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200 transition-colors cursor-pointer"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            {/* Chat Body (Scrollable ChatWindow occupying full height minus header) */}
            <div className="flex-1 overflow-hidden bg-zinc-50 dark:bg-zinc-950/10">
              <ChatWindow
                messages={messages}
                loading={loading}
                onSendMessage={sendMessage}
              />
            </div>
          </div>
        )}
      </div>
    </>
  );
}
