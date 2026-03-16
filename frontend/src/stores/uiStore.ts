import { create } from "zustand";

interface UIState {
  consoleOpen: boolean;
  toggleConsole: () => void;
  setConsoleOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  consoleOpen: false,
  toggleConsole: () => set((s) => ({ consoleOpen: !s.consoleOpen })),
  setConsoleOpen: (open) => set({ consoleOpen: open }),
}));
