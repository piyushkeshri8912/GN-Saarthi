"use client";

import Navbar from "../../components/layout/Navbar";
import ChatWindow from "../../components/chat/ChatWindow";
import { useChat } from "../../hooks/useChat";

export default function ChatPage() {
  const { messages, loading, sendMessage } = useChat();

  return (
    <div className="flex h-screen flex-col bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 transition-colors duration-200 overflow-hidden pb-0 sm:pb-4">
      <Navbar />
      
      <main className="flex-1 px-0 py-0 sm:px-6 sm:py-4 lg:px-8 max-w-7xl mx-auto w-full overflow-hidden">
        <div className="h-full flex flex-col overflow-hidden">
          <div className="flex-1 border-0 sm:border border-zinc-200 dark:border-zinc-800 rounded-none sm:rounded-2xl bg-zinc-50/10 dark:bg-zinc-900/5 sm:shadow-inner overflow-hidden flex flex-col">
            <ChatWindow
              messages={messages}
              loading={loading}
              onSendMessage={sendMessage}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
