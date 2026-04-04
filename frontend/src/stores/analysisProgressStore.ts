/** Zustand store for global analysis progress (header badge).
 *
 * Receives analysis_progress WS messages dispatched by api/ws.ts.
 * Independent silo — does not import other stores.
 */

import { create } from "zustand";
import type { WSAnalysisProgress } from "../types/ws";

type AnalysisProgressPayload = WSAnalysisProgress["payload"];

interface AnalysisProgressState {
  /** Currently active batch/single analysis, or null when idle. */
  activeBatch: AnalysisProgressPayload | null;

  /** Brief completion message shown after analysis finishes, auto-clears after 10s. */
  completionMessage: string | null;

  /** Status of the last completion (for coloring). */
  completionStatus: "complete" | "failed" | "cancelled" | null;

  /** Update from WS message. */
  setProgress: (payload: AnalysisProgressPayload) => void;

  /** Dismiss the completion message. */
  dismiss: () => void;
}

let completionTimer: ReturnType<typeof setTimeout> | null = null;

export const useAnalysisProgressStore = create<AnalysisProgressState>(
  (set) => ({
    activeBatch: null,
    completionMessage: null,
    completionStatus: null,

    setProgress: (payload) => {
      // Clear any existing completion timer
      if (completionTimer) {
        clearTimeout(completionTimer);
        completionTimer = null;
      }

      if (payload.status === "running") {
        set({ activeBatch: payload, completionMessage: null, completionStatus: null });
      } else if (payload.status === "complete") {
        const msg = `Complete: ${payload.completed} track${payload.completed !== 1 ? "s" : ""}`;
        set({ activeBatch: null, completionMessage: msg, completionStatus: "complete" });
        completionTimer = setTimeout(() => {
          completionTimer = null;
          set({ completionMessage: null, completionStatus: null });
        }, 10_000);
      } else if (payload.status === "failed" || payload.status === "cancelled") {
        const label = payload.status === "cancelled" ? "Cancelled" : "Failed";
        const msg = `${label}: ${payload.completed}/${payload.total}`;
        set({ activeBatch: null, completionMessage: msg, completionStatus: payload.status });
      }
    },

    dismiss: () => {
      if (completionTimer) {
        clearTimeout(completionTimer);
        completionTimer = null;
      }
      set({ completionMessage: null, completionStatus: null });
    },
  }),
);
