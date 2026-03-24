/**
 * WaveformTuningPage — dev-only page for real-time waveform rendering parameter tuning.
 *
 * Route: /dev/waveforms
 * Select a track, adjust rendering parameters with live preview,
 * save named presets, compare against Pioneer reference waveform.
 */

import { useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrackPicker } from "../components/analysis/TrackPicker.tsx";
import { WaveformCanvas } from "../components/shared/WaveformCanvas.tsx";
import { ParameterControls } from "../components/waveformTuning/ParameterControls.tsx";
import { PresetBar } from "../components/waveformTuning/PresetBar.tsx";
import { PioneerReferenceWaveform } from "../components/waveformTuning/PioneerReferenceWaveform.tsx";
import { useWaveformPresetStore } from "../stores/waveformPresetStore.ts";
import {
  useWaveformPresets,
  useUpdatePreset,
  useCreatePreset,
  useActivatePreset,
  useDeletePreset,
} from "../api/waveformPresets.ts";
import type { WaveformRenderParams } from "../types/waveformPreset.ts";

const API_BASE = "/api/tracks";

export function WaveformTuningPage() {
  const [fingerprint, setFingerprint] = useState<string | null>(null);
  const [viewStart, setViewStart] = useState(0);
  const [viewEnd, setViewEnd] = useState(0);
  const [currentPresetId, setCurrentPresetId] = useState<string | null>(null);

  // Store
  const {
    draftParams,
    isDirty,
    activePreset,
    setDraftParams,
    loadPresetIntoDraft,
    resetDraft,
    fetchPresets: storeRefetch,
    getRenderParams,
  } = useWaveformPresetStore();

  // API queries
  const { data: presetsData } = useWaveformPresets();
  const updateMutation = useUpdatePreset();
  const createMutation = useCreatePreset();
  const activateMutation = useActivatePreset();
  const deleteMutation = useDeletePreset();

  // Sync presets from API to store
  useEffect(() => {
    storeRefetch();
  }, [storeRefetch]);

  // Set initial preset ID when presets load
  useEffect(() => {
    if (presetsData && !currentPresetId) {
      setCurrentPresetId(presetsData.activePresetId);
      const active = presetsData.presets.find((p) => p.id === presetsData.activePresetId);
      if (active) {
        loadPresetIntoDraft(active);
      }
    }
  }, [presetsData, currentPresetId, loadPresetIntoDraft]);

  // Fetch track analysis
  const { data: analysis, isLoading: analysisLoading } = useQuery({
    queryKey: ["track", fingerprint],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/${fingerprint}`);
      if (!res.ok) throw new Error("Track not found");
      return res.json();
    },
    enabled: !!fingerprint,
  });

  // Fetch pioneer waveform
  const { data: pioneerData } = useQuery({
    queryKey: ["pioneer-waveform-tuning", fingerprint],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/${fingerprint}/pioneer-waveform`);
      if (!res.ok) return null;
      return res.json();
    },
    enabled: !!fingerprint,
  });

  // Set view range when track loads
  useEffect(() => {
    if (analysis?.duration) {
      setViewStart(0);
      setViewEnd(analysis.duration);
    }
  }, [analysis]);

  const handleViewChange = useCallback((start: number, end: number) => {
    setViewStart(start);
    setViewEnd(end);
  }, []);

  const handleParamChange = useCallback(
    (partial: Partial<WaveformRenderParams>) => {
      setDraftParams(partial);
    },
    [setDraftParams],
  );

  const handleSave = useCallback(
    (id: string, params: WaveformRenderParams) => {
      updateMutation.mutate(
        { id, params },
        {
          onSuccess: () => {
            resetDraft();
            storeRefetch();
          },
        },
      );
    },
    [updateMutation, resetDraft, storeRefetch],
  );

  const handleSaveAs = useCallback(
    (name: string, params: WaveformRenderParams) => {
      createMutation.mutate(
        { name, params },
        {
          onSuccess: (newPreset) => {
            setCurrentPresetId(newPreset.id);
            // Activate the new preset
            activateMutation.mutate(newPreset.id, {
              onSuccess: () => {
                resetDraft();
                storeRefetch();
              },
            });
          },
        },
      );
    },
    [createMutation, activateMutation, resetDraft, storeRefetch],
  );

  const handleLoadPreset = useCallback(
    (preset: { id: string; name: string; params: WaveformRenderParams; isActive: boolean; createdAt: string; updatedAt: string }) => {
      setCurrentPresetId(preset.id);
      loadPresetIntoDraft(preset);
    },
    [loadPresetIntoDraft],
  );

  const handleActivate = useCallback(
    (id: string) => {
      activateMutation.mutate(id, {
        onSuccess: () => storeRefetch(),
      });
    },
    [activateMutation, storeRefetch],
  );

  const handleDelete = useCallback(
    (id: string) => {
      if (!confirm("Delete this preset?")) return;
      deleteMutation.mutate(id, {
        onSuccess: () => storeRefetch(),
      });
    },
    [deleteMutation, storeRefetch],
  );

  const duration = analysis?.duration ?? 0;
  const currentParams = getRenderParams();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-white">Waveform Tuning</h1>
        <p className="text-sm text-slate-400 mt-1">
          Tune waveform rendering parameters with live preview. Compare against Pioneer reference.
        </p>
      </div>

      {/* Track picker */}
      <TrackPicker selectedFingerprint={fingerprint} onSelect={setFingerprint} />

      {analysisLoading && (
        <div className="text-slate-400 text-sm animate-pulse">Loading track data...</div>
      )}

      {analysis && !analysisLoading && (
        <>
          {/* Track info */}
          <div className="flex items-center gap-4 text-sm text-slate-400 bg-slate-800/50 rounded-lg px-4 py-2">
            <span className="text-white font-medium">{analysis.title}</span>
            <span>{analysis.bpm?.toFixed(1)} BPM</span>
            <span>{duration.toFixed(1)}s</span>
            <span>{analysis.sections?.length ?? 0} sections</span>
          </div>

          {/* Preset bar */}
          <PresetBar
            presets={presetsData?.presets ?? []}
            activePreset={activePreset}
            currentPresetId={currentPresetId}
            isDirty={isDirty}
            onSave={handleSave}
            onSaveAs={handleSaveAs}
            onLoadPreset={handleLoadPreset}
            onActivate={handleActivate}
            onDelete={handleDelete}
            currentParams={currentParams}
          />

          {/* Main waveform */}
          {analysis.waveform && (
            <WaveformCanvas
              waveform={analysis.waveform}
              sections={analysis.sections}
              duration={duration}
              viewStart={viewStart}
              viewEnd={viewEnd}
              onViewChange={handleViewChange}
              height={180}
              renderParams={draftParams ?? activePreset?.params ?? undefined}
            />
          )}

          {/* Pioneer reference waveform */}
          {pioneerData && (
            <PioneerReferenceWaveform
              data={pioneerData}
              viewStart={viewStart}
              viewEnd={viewEnd}
              height={90}
            />
          )}
          {!pioneerData && fingerprint && (
            <div className="text-xs text-slate-500 bg-slate-900 border border-slate-800 rounded p-3">
              No Pioneer ANLZ data — analyze from USB to enable comparison
            </div>
          )}

          {/* Parameter controls */}
          <ParameterControls
            params={currentParams}
            onParamChange={handleParamChange}
          />
        </>
      )}
    </div>
  );
}
