import { useState, useRef, useEffect } from "react";
import api from "../lib/api";
import { Message, SourceChunk } from "../types";
import { auth } from "../lib/firebase";

export const useChat = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const sessionIdRef = useRef<string>("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      let sid = sessionStorage.getItem("gn_saarthi_session_id");
      if (!sid) {
        sid = crypto.randomUUID();
        sessionStorage.setItem("gn_saarthi_session_id", sid);
      }
      sessionIdRef.current = sid;
    }
  }, []);

  const sendMessage = async (text: string) => {
    if (!text.trim()) return;

    // Create and append user message
    const userMsg: Message = {
      id: crypto.randomUUID(),
      sender: "user",
      text: text,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      // Get Firebase ID token
      const currentUser = auth.currentUser;
      const token = currentUser ? await currentUser.getIdToken() : "";

      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
      
      // Call RAG chat stream endpoint
      const response = await fetch(`${baseUrl}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ 
          message: text,
          session_id: sessionIdRef.current 
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData?.detail || `Server error: ${response.status}`);
      }

      if (!response.body) {
        throw new Error("No response body received from server");
      }

      // Create and append bot message with empty text initially
      const botMsgId = crypto.randomUUID();
      const initialBotMsg: Message = {
        id: botMsgId,
        sender: "bot",
        text: "",
        timestamp: new Date().toISOString(),
        sources: [],
      };

      setMessages((prev) => [...prev, initialBotMsg]);
      setLoading(false);

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      
      let finished = false;
      let buffer = "";
      let accumulatedText = "";
      
      const wordQueue: string[] = [];
      let isTypingActive = false;

      // Typewriter word renderer
      const typeNextWord = () => {
        if (wordQueue.length > 0) {
          // Adjust batch size to catch up if queue grows too long
          const batchSize = Math.max(1, Math.floor(wordQueue.length / 8));
          for (let i = 0; i < batchSize; i++) {
            if (wordQueue.length > 0) {
              const word = wordQueue.shift();
              if (word !== undefined) {
                accumulatedText += word;
              }
            }
          }
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === botMsgId ? { ...msg, text: accumulatedText } : msg
            )
          );
          setTimeout(typeNextWord, 35); // 35ms delay per word/whitespace chunk for a clean typewriter speed
        } else {
          isTypingActive = false;
        }
      };

      while (!finished) {
        const { value, done } = await reader.read();
        if (done) {
          finished = true;
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            try {
              const jsonStr = trimmed.substring(6).trim();
              const data = JSON.parse(jsonStr);

              if (data.type === "text") {
                const content = data.content;
                const words = content.split(/(\s+)/).filter(Boolean);
                wordQueue.push(...words);
                if (!isTypingActive) {
                  isTypingActive = true;
                  typeNextWord();
                }
              } else if (data.type === "sources") {
                const sourcesList: SourceChunk[] = data.content;
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === botMsgId ? { ...msg, sources: sourcesList } : msg
                  )
                );
              } else if (data.type === "error") {
                console.error("Stream error event:", data.content);
                throw new Error(data.content);
              }
            } catch (e) {
              console.error("Failed to parse SSE line:", trimmed, e);
            }
          }
        }
      }

      // If there are leftover characters in the buffer, parse them
      if (buffer.trim()) {
        const trimmed = buffer.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            const jsonStr = trimmed.substring(6).trim();
            const data = JSON.parse(jsonStr);
            if (data.type === "text") {
              const words = data.content.split(/(\s+)/).filter(Boolean);
              wordQueue.push(...words);
              if (!isTypingActive) {
                isTypingActive = true;
                typeNextWord();
              }
            } else if (data.type === "sources") {
              const sourcesList: SourceChunk[] = data.content;
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === botMsgId ? { ...msg, sources: sourcesList } : msg
                )
              );
            }
          } catch (e) {
            // Ignore partial lines at the very end
          }
        }
      }

    } catch (error: any) {
      console.error("Chat request failed:", error);
      const errorMessage = error?.message || "Sorry, I encountered an error. Please try again.";
      
      const botMsgError: Message = {
        id: crypto.randomUUID(),
        sender: "bot",
        text: errorMessage,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, botMsgError]);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    if (typeof window !== "undefined") {
      const newSid = crypto.randomUUID();
      sessionStorage.setItem("gn_saarthi_session_id", newSid);
      sessionIdRef.current = newSid;
    }
  };

  return { messages, loading, sendMessage, clearChat };
};
