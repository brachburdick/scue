/** Console store — ring-buffered log entries with recording support.
 *
 * Independent store: does NOT import any other store.
 */

import { create } from "zustand";
import type { ConsoleEntry, ConsoleSource, ConsoleSeverity } from "../types/console";

const MAX_ENTRIES = 200;

let nextId = 1;

interface ConsoleStoreState {
  entries: ConsoleEntry[];
  verboseMode: boolean;
  isRecording: boolean;
  recordBuffer: ConsoleEntry[];

  addEntry: (entry: Omit<ConsoleEntry, "id" | "timestamp">) => void;
  setVerboseMode: (verbose: boolean) => void;
  startRecording: () => void;
  stopRecording: () => ConsoleEntry[];
  clearEntries: () => void;
}

export type { ConsoleSource, ConsoleSeverity };

export const useConsoleStore = create<ConsoleStoreState>((set, get) => ({
  entries: [],
  verboseMode: false,
  isRecording: false,
  recordBuffer: [],

  addEntry: (partial) => {
    const entry: ConsoleEntry = {
      ...partial,
      id: String(nextId++),
      timestamp: Date.now(),
    };

    set((state) => {
      const updated = [...state.entries, entry];
      if (updated.length > MAX_ENTRIES) {
        updated.splice(0, updated.length - MAX_ENTRIES);
      }

      const newState: Partial<ConsoleStoreState> = { entries: updated };

      if (state.isRecording) {
        newState.recordBuffer = [...state.recordBuffer, entry];
      }

      return newState;
    });
  },

  setVerboseMode: (verbose) => set({ verboseMode: verbose }),

  startRecording: () => set({ isRecording: true, recordBuffer: [] }),

  stopRecording: () => {
    const buffer = get().recordBuffer;
    set({ isRecording: false, recordBuffer: [] });
    return buffer;
  },

  clearEntries: () => set({ entries: [] }),
}));
