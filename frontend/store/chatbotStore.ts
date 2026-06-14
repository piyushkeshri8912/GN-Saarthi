import { create } from "zustand";

interface ChatbotState {
  isOpen: boolean;
  width: number;
  setIsOpen: (isOpen: boolean) => void;
  setWidth: (width: number) => void;
}

export const useChatbotStore = create<ChatbotState>((set) => ({
  isOpen: false,
  width: 400, // Default width is 400px
  setIsOpen: (isOpen) => set({ isOpen }),
  setWidth: (width) => set({ width }),
}));
