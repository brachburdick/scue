import { create } from "zustand";

type ViewMode = "directory" | "flat";

interface FolderState {
  currentFolder: string;
  viewMode: ViewMode;

  setCurrentFolder: (folder: string) => void;
  setViewMode: (mode: ViewMode) => void;
  navigateUp: () => void;
  navigateToFolder: (folder: string) => void;
}

export const useFolderStore = create<FolderState>((set) => ({
  currentFolder: "",
  viewMode: "flat",

  setCurrentFolder: (currentFolder) => set({ currentFolder }),
  setViewMode: (viewMode) => set({ viewMode }),

  navigateUp: () =>
    set((state) => {
      const parts = state.currentFolder.split("/");
      parts.pop();
      return { currentFolder: parts.join("/") };
    }),

  navigateToFolder: (folder) =>
    set({ currentFolder: folder, viewMode: "directory" }),
}));
