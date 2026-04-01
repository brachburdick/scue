import { useState, useCallback } from "react";
import { useTrackAnalysis } from "../../api/tracks";
import { useWaveformView } from "../../hooks/useWaveformView";
import { useWaveformPresetStore } from "../../stores/waveformPresetStore";
import { WaveformCanvas } from "../shared/WaveformCanvas";
import { SectionList } from "./SectionList";
import { TrackMetadataPanel } from "./TrackMetadataPanel";

interface WaveformPanelProps {
  fingerprint: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function WaveformPanel({ fingerprint, collapsed, onToggleCollapse }: WaveformPanelProps) {
  const { data: analysis, isLoading, error } = useTrackAnalysis(fingerprint);
  const activeRenderParams = useWaveformPresetStore((s) => s.activePreset?.params);

  const duration = analysis?.duration ?? 0;
  const { viewStart, viewEnd, setView, zoomToSection } = useWaveformView(duration);

  const [highlightedSection, setHighlightedSection] = useState<number | null>(null);
  const [selectedSection, setSelectedSection] = useState<number | null>(null);

  const handleWaveformSectionHover = useCallback((index: number | null) => {
    setHighlightedSection(index);
  }, []);

  const handleWaveformSectionClick = useCallback((index: number) => {
    setSelectedSection(index);
  }, []);

  const handleListHover = useCallback((index: number | null) => {
    setHighlightedSection(index);
  }, []);

  const handleListSelect = useCallback(
    (index: number) => {
      setSelectedSection(index);
      if (analysis) {
        const sec = analysis.sections[index];
        if (sec) zoomToSection(sec.start, sec.end);
      }
    },
    [analysis, zoomToSection],
  );

  if (error) {
    return (
      <div className="px-4 py-2 bg-red-950 border border-red-800 rounded text-sm text-red-300">
        Failed to load analysis: {(error as Error).message}
      </div>
    );
  }

  return (
    <div className="bg-gray-950 rounded border border-gray-800">
      {/* Header with collapse toggle */}
      <button
        onClick={onToggleCollapse}
        className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
      >
        <span className={`text-[10px] transition-transform ${collapsed ? "" : "rotate-90"}`}>
          &#9654;
        </span>
        <span>Waveform &amp; Metadata</span>
        {isLoading && <span className="text-gray-600 text-xs ml-auto">Loading...</span>}
      </button>

      {!collapsed && analysis && (
        <div className="px-4 pb-4 space-y-4">
          {/* Waveform */}
          {analysis.waveform ? (
            <WaveformCanvas
              waveform={analysis.waveform}
              sections={analysis.sections}
              energyCurve={analysis.features.energy_curve}
              duration={analysis.duration}
              beats={analysis.beats}
              downbeats={analysis.downbeats}
              highlightedSection={highlightedSection}
              selectedSection={selectedSection}
              onSectionHover={handleWaveformSectionHover}
              onSectionClick={handleWaveformSectionClick}
              viewStart={viewStart}
              viewEnd={viewEnd}
              onViewChange={setView}
              renderParams={activeRenderParams}
            />
          ) : (
            <div className="h-40 flex items-center justify-center bg-gray-900 rounded border border-gray-800">
              <p className="text-gray-500 text-sm">No waveform data &mdash; re-analyze with waveform enabled</p>
            </div>
          )}

          {/* Bottom grid: section list | metadata */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <SectionList
              sections={analysis.sections}
              highlightedIndex={highlightedSection}
              selectedIndex={selectedSection}
              onHover={handleListHover}
              onSelect={handleListSelect}
            />
            <TrackMetadataPanel analysis={analysis} />
          </div>
        </div>
      )}

      {!collapsed && !analysis && !isLoading && (
        <div className="px-4 pb-4">
          <p className="text-gray-600 text-sm">No analysis data available for this track.</p>
        </div>
      )}
    </div>
  );
}
