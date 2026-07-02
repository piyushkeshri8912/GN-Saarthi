import { useState, useRef, useEffect } from "react";
import { Send, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SourceCard from "./SourceCard";
import { Message } from "../../types";

interface ChatWindowProps {
  messages: Message[];
  loading: boolean;
  onSendMessage: (text: string) => void;
}

export default function ChatWindow({ messages, loading, onSendMessage }: ChatWindowProps) {
  const [inputText, setInputText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const starterPrompts = [
    "What are the Norms for branch change?",
    "Show me the Bus schedule.",
    "Explain credits requirement for BTech?",
    "Norms for claiming online credits?",
  ];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || loading) return;
    onSendMessage(inputText);
    setInputText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [inputText]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      
      {/* Messages Feed */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center p-4 max-w-xl mx-auto">
            <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-white border border-zinc-200 dark:border-zinc-700/35 shadow-inner">
              <Sparkles className="h-5 w-5 animate-pulse text-zinc-500 dark:text-zinc-400" />
            </div>
            <h3 className="text-lg font-bold text-zinc-900 dark:text-white font-display">Ask GN Saarthi</h3>
            <p className="mt-2 text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
              Your AI guide to IIT Gandhinagar. Query curriculum policies, campus facilities, and transport timings.
            </p>
 
            {/* Quick Starter Prompts */}
            <div className="mt-6 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
              {starterPrompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => onSendMessage(prompt)}
                  className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950/20 p-3 text-left text-xs font-semibold text-zinc-600 dark:text-slate-400 transition-all hover:border-zinc-400 hover:bg-zinc-50 dark:hover:border-zinc-700/55 dark:hover:bg-zinc-900/20 dark:hover:text-slate-200 cursor-pointer shadow-sm dark:shadow-none"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => {
            const isUser = message.sender === "user";
            return (
              <div
                key={message.id}
                className={`max-w-[92%] flex flex-col space-y-1.5 ${
                  isUser ? "ml-auto items-end" : "mr-auto items-start"
                }`}
              >
                <div
                  className={`rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed w-fit ${
                    isUser
                      ? "bg-zinc-900 dark:bg-zinc-800 text-white shadow-sm border border-zinc-950 dark:border-zinc-700"
                      : "bg-white dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 text-zinc-800 dark:text-slate-200"
                  }`}
                >
                  {isUser ? (
                    <span className="whitespace-pre-wrap break-words">{message.text}</span>
                  ) : (
                    <div className="max-w-none text-sm break-words">
                      {message.text.trim() === "" ? (
                        <div className="flex items-center space-x-1.5 py-1 px-0.5">
                          <div className="w-1.5 h-1.5 bg-zinc-400 dark:bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }}></div>
                          <div className="w-1.5 h-1.5 bg-zinc-400 dark:bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }}></div>
                          <div className="w-1.5 h-1.5 bg-zinc-400 dark:bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }}></div>
                        </div>
                      ) : (
                        <ReactMarkdown 
                          remarkPlugins={[remarkGfm]}
                          components={{
                            a: ({node, ...props}) => <a target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline font-semibold" {...props} />,
                            p: ({node, ...props}) => <p className="mb-1.5 last:mb-0 leading-relaxed" {...props} />,
                            ul: ({node, ...props}) => <ul className="list-disc pl-5 mb-2 mt-1 space-y-1" {...props} />,
                            ol: ({node, ...props}) => <ol className="list-decimal pl-5 mb-2 mt-1 space-y-1" {...props} />,
                            li: ({node, ...props}) => <li className="leading-relaxed" {...props} />,
                            h1: ({node, ...props}) => <h1 className="text-base font-extrabold mb-1.5 mt-2.5 text-zinc-900 dark:text-white" {...props} />,
                            h2: ({node, ...props}) => <h2 className="text-sm font-extrabold mb-1.5 mt-2.5 text-zinc-900 dark:text-white" {...props} />,
                            h3: ({node, ...props}) => <h3 className="text-xs font-extrabold mb-1 mt-2 text-zinc-900 dark:text-white" {...props} />,
                            strong: ({node, ...props}) => <strong className="font-extrabold text-zinc-950 dark:text-white" {...props} />,
                            em: ({node, ...props}) => <em className="italic text-zinc-800 dark:text-zinc-200" {...props} />,
                            table: ({node, ...props}) => (
                              <div className="overflow-x-auto my-2 rounded-xl border border-zinc-200 dark:border-zinc-800 shadow-sm">
                                <table className="w-full text-xs text-left" {...props} />
                              </div>
                            ),
                            thead: ({node, ...props}) => <thead className="bg-zinc-100 dark:bg-zinc-800 text-[10px] uppercase font-bold text-zinc-700 dark:text-zinc-300" {...props} />,
                            tbody: ({node, ...props}) => <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800 bg-white dark:bg-zinc-950/20" {...props} />,
                            th: ({node, ...props}) => <th className="px-3 py-2 font-bold" {...props} />,
                            td: ({node, ...props}) => <td className="px-3 py-2 text-zinc-700 dark:text-zinc-300" {...props} />,
                          }}
                        >
                          {message.text.replace(/\s*\[sources?\s*\d+(?:[\s,]+(?:sources?\s*)?\d+)*\]/gi, "")}
                        </ReactMarkdown>
                      )}
                    </div>
                  )}
                </div>
 
                {/* References & Citations */}
                {!isUser && message.sources && message.sources.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <p className="text-[9px] font-black uppercase tracking-widest text-zinc-400 dark:text-slate-500">
                      Reference Sources & Citations:
                    </p>
                    <div className="grid gap-1.5 sm:grid-cols-2">
                      {message.sources.map((source, idx) => (
                        <SourceCard key={idx} source={source} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
 
        {/* Loading / Typing Dots */}
        {loading && (
          <div className="max-w-[92%] mr-auto">
            <div className="flex items-center gap-1.5 rounded-2xl bg-zinc-100 dark:bg-zinc-900/30 border border-zinc-200 dark:border-zinc-800 px-3.5 py-2.5 text-zinc-400 w-fit">
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.3s]"></div>
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.15s]"></div>
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400"></div>
            </div>
          </div>
        )}
 
        <div ref={messagesEndRef} />
      </div>
 
      {/* Message Inputs */}
      <form onSubmit={handleSubmit} className="border-t border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/30 p-2.5 pb-4 sm:pb-2.5 transition-colors">
        <div className="relative flex items-end">
          <textarea
            ref={textareaRef}
            rows={1}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onFocus={() => {
              setTimeout(() => {
                messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
              }, 300);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                // Check if device has a touch screen or is mobile-sized
                const isMobile = window.matchMedia("(pointer: coarse)").matches || window.innerWidth < 768;
                if (!isMobile) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }
            }}
            placeholder="Ask queries related to IIT Gandhinagar"
            disabled={loading}
            className="w-full rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 py-3 pr-10 pl-3.5 text-sm text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:border-zinc-400 dark:focus:border-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-450 dark:focus:ring-zinc-600 disabled:opacity-50 transition-colors resize-none overflow-y-auto max-h-40 min-h-[44px]"
          />
          <button
            type="submit"
            disabled={!inputText.trim() || loading}
            className="absolute right-1.5 bottom-1.5 flex h-7.5 w-7.5 items-center justify-center rounded-lg bg-zinc-900 dark:bg-zinc-800 text-white transition hover:bg-zinc-800 dark:hover:bg-zinc-700 disabled:bg-zinc-100 dark:disabled:bg-zinc-900 disabled:text-zinc-300 dark:disabled:text-zinc-600 cursor-pointer border border-zinc-800 dark:border-zinc-700/35"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </form>
    </div>
  );
}
