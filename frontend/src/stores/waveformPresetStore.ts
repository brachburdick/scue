/**
 * waveformPresetStore — manages waveform rendering presets.
 *
 * Independent Zustand store (no imports from other stores).
 * - Fetches presets from backend on init.
 * - Holds draftParams for the tuning page (unsaved edits).
 * - Other waveform components read activePreset.params.
 */

import { create } from "zustand";
import { apiFetch } from "../api/client";
import type {
  WaveformPreset,
  WaveformRenderParams,
  WaveformPresetsResponse,
} from "../types/waveformPreset";
import { DEFAULT_RENDER_PARAMS } from "../types/waveformPreset";

interface WaveformPresetStore {
  presets: WaveformPreset[];
  activePreset: WaveformPreset | null;

  // Tuning page draft
  draftParams: WaveformRenderParams | null;
  isDirty: boolean;

  // Actions
  fetchPresets: () => Promise<void>;
  setDraftParams: (params: Partial<WaveformRenderParams>) => void;
  loadPresetIntoDraft: (preset: WaveformPreset) => void;
  resetDraft: () => void;

  /** Get the params to use for rendering — draftParams on tuning page, activePreset elsewhere. */
  getRenderParams: () => WaveformRenderParams;
}

export const useWaveformPresetStore = create<WaveformPresetStore>((set, get) => ({
  presets: [],
  activePreset: null,
  draftParams: null,
  isDirty: false,

  fetchPresets: async () => {
    try {
      const data = await apiFetch<WaveformPresetsResponse>("/waveform-presets");
      const active = data.presets.find((p) => p.id === data.activePresetId) ?? null;
      set({ presets: data.presets, activePreset: active });
    } catch {
      // Silently fail — presets are non-critical
    }
  },

  setDraftParams: (partial) => {
    const { draftParams, activePreset } = get();
    const base = draftParams ?? activePreset?.params ?? DEFAULT_RENDER_PARAMS;
    set({ draftParams: { ...base, ...partial }, isDirty: true });
  },

  loadPresetIntoDraft: (preset) => {
    set({ draftParams: { ...preset.params }, isDirty: false });
  },

  resetDraft: () => {
    set({ draftParams: null, isDirty: false });
  },

  getRenderParams: () => {
    const { draftParams, activePreset } = get();
    return draftParams ?? activePreset?.params ?? DEFAULT_RENDER_PARAMS;
  },
}));
