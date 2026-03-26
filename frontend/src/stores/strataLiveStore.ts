/** Zustand store for live strata data streamed from Pioneer hardware.
 *
 * Receives strata_live WS messages dispatched by api/ws.ts.
 * Independent silo — does not import other stores.
 */

import { create } from "zustand";
import type { ArrangementFormula } from "../types/strata";

interface StrataLiveState {
  /** Per-player live strata formulas (keyed by player number). */
  formulas: Record<number, ArrangementFormula>;

  /** Set/update a player's live strata formula (from WS message). */
  setFormula: (playerNumber: number, formula: ArrangementFormula) => void;

  /** Clear a player's live strata (e.g. on track unload). */
  clearPlayer: (playerNumber: number) => void;

  /** Clear all live strata data. */
  clearAll: () => void;
}

export const useStrataLiveStore = create<StrataLiveState>((set) => ({
  formulas: {},

  setFormula: (playerNumber, formula) =>
    set((state) => ({
      formulas: { ...state.formulas, [playerNumber]: formula },
    })),

  clearPlayer: (playerNumber) =>
    set((state) => {
      const next = { ...state.formulas };
      delete next[playerNumber];
      return { formulas: next };
    }),

  clearAll: () => set({ formulas: {} }),
}));
