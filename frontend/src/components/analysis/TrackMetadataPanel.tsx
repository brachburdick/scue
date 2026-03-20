import type { TrackAnalysis } from "../../types";
import { formatDuration, truncateFingerprint } from "../../utils/formatters";

interface TrackMetadataPanelProps {
  analysis: TrackAnalysis;
}

function confidenceColor(c: number): string {
  if (c < 0.5) return "text-red-400";
  if (c < 0.7) return "text-yellow-400";
  return "text-green-400";
}

const MOOD_COLORS: Record<string, string> = {
  dark: "bg-purple-900/50 text-purple-300",
  euphoric: "bg-amber-900/50 text-amber-300",
  melancholic: "bg-blue-900/50 text-blue-300",
  aggressive: "bg-red-900/50 text-red-300",
  neutral: "bg-gray-800 text-gray-400",
};

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).catch(() => {});
}

export function TrackMetadataPanel({ analysis }: TrackMetadataPanelProps) {
  const f = analysis.features;

  return (
    <div className="space-y-3 text-sm">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Track Info</h3>

      <div className="space-y-1.5">
        <Row label="Title" value={analysis.title || "Untitled"} />
        <Row label="Artist" value={analysis.artist || "Unknown"} />
        <Row label="BPM" value={analysis.bpm.toFixed(2)} />
        {analysis.pioneer_bpm != null && (
          <Row label="Pioneer BPM" value={analysis.pioneer_bpm.toFixed(2)} muted />
        )}
        <Row label="Key" value={f.key || "—"}>
          <span className={`ml-2 ${confidenceColor(f.key_confidence)}`}>
            ({f.key_confidence.toFixed(2)})
          </span>
        </Row>
        {analysis.pioneer_key != null && (
          <Row label="Pioneer Key" value={analysis.pioneer_key} muted />
        )}
        <Row label="Mood">
          <span className={`px-2 py-0.5 rounded text-xs ${MOOD_COLORS[f.mood] ?? MOOD_COLORS.neutral}`}>
            {f.mood}
          </span>
        </Row>
        <Row label="Danceability" value={f.danceability.toFixed(2)} />
        <Row label="Duration" value={formatDuration(analysis.duration)} />
        <Row label="Sections" value={String(analysis.sections.length)} />
        <Row label="Source">
          <SourceBadge source={analysis.source} />
        </Row>
        <Row label="Beatgrid">
          <SourceBadge source={analysis.beatgrid_source} />
        </Row>
        <Row label="Version" value={String(analysis.version)} />
        <Row label="Fingerprint">
          <button
            className="font-mono text-gray-500 hover:text-gray-300 transition-colors"
            title={`Click to copy: ${analysis.fingerprint}`}
            onClick={() => copyToClipboard(analysis.fingerprint)}
          >
            {truncateFingerprint(analysis.fingerprint, 12)}
          </button>
        </Row>
        {analysis.rekordbox_id != null && (
          <Row label="rekordbox ID" value={String(analysis.rekordbox_id)} muted />
        )}
        <Row label="Created" value={new Date(analysis.created_at * 1000).toLocaleString()} />
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  muted,
  children,
}: {
  label: string;
  value?: string;
  muted?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-gray-500 text-xs w-24 shrink-0">{label}</span>
      {value && <span className={muted ? "text-gray-500" : "text-gray-300"}>{value}</span>}
      {children}
    </div>
  );
}

function SourceBadge({ source }: { source: string }) {
  const isEnriched = source === "pioneer_enriched";
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-xs ${
        isEnriched ? "bg-green-900/50 text-green-300" : "bg-gray-800 text-gray-500"
      }`}
    >
      {isEnriched ? "enriched" : "analysis"}
    </span>
  );
}
