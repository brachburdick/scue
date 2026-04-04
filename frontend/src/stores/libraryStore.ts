import { create } from "zustand";
import type { LibraryTab, ImportMode } from "../types/library";

interface LibraryState {
  activeTab: LibraryTab;
  importMode: ImportMode;
  selectedTracks: Record<LibraryTab, Set<string>>;
  expandedPreview: string | null;
  searchText: Record<LibraryTab, string>;
  batchId: string | null;

  setActiveTab: (tab: LibraryTab) => void;
  setImportMode: (mode: ImportMode) => void;
  setSelectedTracks: (tab: LibraryTab, tracks: Set<string>) => void;
  toggleTrackSelection: (tab: LibraryTab, fingerprint: string) => void;
  setExpandedPreview: (fingerprint: string | null) => void;
  setSearchText: (tab: LibraryTab, text: string) => void;
  setBatchId: (id: string | null) => void;
}

const emptySelections: Record<LibraryTab, Set<string>> = {
  rekordbox: new Set(),
  hardware: new Set(),
  audio: new Set(),
  scue_library: new Set(),
};

const emptySearch: Record<LibraryTab, string> = {
  rekordbox: "",
  hardware: "",
  audio: "",
  scue_library: "",
};

export const useLibraryStore = create<LibraryState>((set) => ({
  activeTab: "rekordbox",
  importMode: "metadata",
  selectedTracks: { ...emptySelections },
  expandedPreview: null,
  searchText: { ...emptySearch },
  batchId: null,

  setActiveTab: (tab) => set({ activeTab: tab }),
  setImportMode: (mode) => set({ importMode: mode }),
  setSelectedTracks: (tab, tracks) =>
    set((s) => ({ selectedTracks: { ...s.selectedTracks, [tab]: tracks } })),
  toggleTrackSelection: (tab, fingerprint) =>
    set((s) => {
      const current = s.selectedTracks[tab];
      const next = new Set(current);
      if (next.has(fingerprint)) next.delete(fingerprint);
      else next.add(fingerprint);
      return { selectedTracks: { ...s.selectedTracks, [tab]: next } };
    }),
  setExpandedPreview: (fingerprint) => set({ expandedPreview: fingerprint }),
  setSearchText: (tab, text) =>
    set((s) => ({ searchText: { ...s.searchText, [tab]: text } })),
  setBatchId: (id) => set({ batchId: id }),
}));
