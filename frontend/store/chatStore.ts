import { create } from "zustand";
import { Message } from "../types";

interface ChatState {
  messages: Message[];
  loading: boolean;
  sessionId: string;
  setMessages: (messages: Message[] | ((prev: Message[]) => Message[])) => void;
  setLoading: (loading: boolean) => void;
  setSessionId: (sessionId: string) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  loading: false,
  sessionId: "",
  setMessages: (newMessages) => set((state) => ({
    messages: typeof newMessages === "function" ? newMessages(state.messages) : newMessages
  })),
  setLoading: (loading) => set({ loading }),
  setSessionId: (sessionId) => set({ sessionId }),
}));
