import { useNavigate } from "react-router-dom";
import { useTrackAnalysis } from "../../api/tracks";
import { useWaveformPresetStore } from "../../stores/waveformPresetStore";
import { WaveformCanvas } from "../shared/WaveformCanvas";
import { formatDate, truncateFingerprint } from "../../utils/formatters";
import type { TrackSummary } from "../../types";

interface TrackPreviewRowProps {
  track: TrackSummary;
  colSpan: number;
}

function TierStatus({ label, tooltip, active }: { label: string; tooltip: string; active?: boolean }) {
  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
        active ? "bg-green-900/40 text-green-400" : "bg-gray-800 text-gray-600"
      }`}
    >
      <span className={active ? "text-green-400" : "text-gray-700"}>●</span>
      {label}
    </span>
  );
}

export function TrackPreviewRow({ track, colSpan }: TrackPreviewRowProps) {
  const navigate = useNavigate();
  const { data: analysis, isLoading } = useTrackAnalysis(track.fingerprint);
  const activeRenderParams = useWaveformPresetStore((s) => s.activePreset?.params);

  return (
    <tr>
      <td colSpan={colSpan} className="p-0">
        <div className="px-4 py-3 bg-gray-900/50 border-t border-b border-gray-800 space-y-3">
          {/* Top row: metadata */}
          <div className="flex items-start gap-6 text-sm">
            <div className="space-y-1">
              <div className="text-gray-400">
                BPM: <span className="text-gray-200">{track.bpm > 0 ? track.bpm.toFixed(1) : "—"}</span>
              </div>
              <div className="text-gray-400">
                Key: <span className="text-gray-200">{track.key_name || "—"}</span>
              </div>
              <div className="text-gray-400">
                Source: <span className="text-gray-200">{track.source || "analysis"}</span>
              </div>
            </div>
            <div className="space-y-1">
              <div className="text-gray-400">
                Imported: <span className="text-gray-200">{formatDate(track.created_at)}</span>
              </div>
              <div className="text-gray-400">
                Fingerprint: <span className="text-gray-200 font-mono text-xs">{truncateFingerprint(track.fingerprint, 12)}</span>
              </div>
              <div className="text-gray-400">
                Sections: <span className="text-gray-200">{track.section_count}</span>
              </div>
            </div>
          </div>

          {/* Mini waveform */}
          {isLoading ? (
            <div className="h-14 bg-gray-800 rounded animate-pulse" />
          ) : analysis?.waveform ? (
            <WaveformCanvas
              waveform={analysis.waveform}
              sections={analysis.sections}
              duration={analysis.duration}
              viewStart={0}
              viewEnd={analysis.duration}
              height={56}
              renderParams={activeRenderParams}
            />
          ) : (
            <div className="h-14 flex items-center justify-center bg-gray-950 rounded border border-gray-800">
              <span className="text-gray-600 text-xs">No waveform data</span>
            </div>
          )}

          {/* Tier status badges */}
          <div className="flex items-center gap-2">
            <TierStatus label="Quick" tooltip="Fast heuristic analysis (~3-7s)" active={track.has_quick} />
            <TierStatus label="Standard" tooltip="Stem separation + per-stem analysis (~1-2 min)" active={track.has_standard} />
            <TierStatus label="Deep" tooltip="Stem separation + ML models (~2-5 min)" active={track.has_deep} />
            <TierStatus label="Live" tooltip="Live: Pioneer hardware real-time data" active={track.has_live} />
            <TierStatus label="Live Offline" tooltip="Live Offline: Saved Pioneer data, no hardware needed" active={track.has_live_offline} />
            <button
              onClick={(e) => {
                e.stopPropagation();
                navigate(`/analysis?track=${track.fingerprint}`);
              }}
              className="ml-auto text-xs text-blue-400 hover:text-blue-300 transition-colors"
            >
              Open in Analysis →
            </button>
          </div>
        </div>
      </td>
    </tr>
  );
}
