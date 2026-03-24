import { useState, useCallback } from "react";
import { useTrackAnalysis } from "../../api/tracks";
import { useWaveformView } from "../../hooks/useWaveformView";
import { WaveformCanvas } from "../shared/WaveformCanvas";
import { PlaceholderPanel } from "../shared/PlaceholderPanel";
import { SectionList } from "./SectionList";
import { TrackMetadataPanel } from "./TrackMetadataPanel";
import { useWaveformPresetStore } from "../../stores/waveformPresetStore";

interface AnalysisViewerProps {
  fingerprint: string;
}

export function AnalysisViewer({ fingerprint }: AnalysisViewerProps) {
  const { data: analysis, isLoading, error } = useTrackAnalysis(fingerprint);
  const activeRenderParams = useWaveformPresetStore((s) => s.activePreset?.params);

  const duration = analysis?.duration ?? 0;
  const { viewStart, viewEnd, setView, zoomToSection } = useWaveformView(duration);

  const [highlightedSection, setHighlightedSection] = useState<number | null>(null);
  const [selectedSection, setSelectedSection] = useState<number | null>(null);

  // Waveform -> Section list: hover
  const handleWaveformSectionHover = useCallback((index: number | null) => {
    setHighlightedSection(index);
  }, []);

  // Waveform -> Section list: click
  const handleWaveformSectionClick = useCallback((index: number) => {
    setSelectedSection(index);
  }, []);

  // Section list -> Waveform: hover
  const handleListHover = useCallback((index: number | null) => {
    setHighlightedSection(index);
  }, []);

  // Section list -> Waveform: click (zoom to section)
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
    return <p className="text-red-400 text-sm mt-4">Failed to load analysis: {(error as Error).message}</p>;
  }

  if (isLoading) {
    return (
      <div className="mt-4 h-40 bg-gray-900 rounded border border-gray-800 animate-pulse" />
    );
  }

  if (!analysis) return null;

  return (
    <div className="mt-4 space-y-4">
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
        <div className="h-40 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
          <p className="text-gray-500 text-sm">No waveform data — re-analyze with waveform enabled</p>
        </div>
      )}

      {/* Bottom grid: section list | metadata | placeholders */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div>
          <SectionList
            sections={analysis.sections}
            highlightedIndex={highlightedSection}
            selectedIndex={selectedSection}
            onHover={handleListHover}
            onSelect={handleListSelect}
          />
        </div>

        <div>
          <TrackMetadataPanel analysis={analysis} />
        </div>

        <div className="space-y-3">
          <PlaceholderPanel
            title="Musical Events"
            subtitle="Event detection coming in Milestone 7"
          />
          <PlaceholderPanel
            title="Analysis Parameters"
            subtitle="Parameter tweaking coming soon"
          />
        </div>
      </div>
    </div>
  );
}
