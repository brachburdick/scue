import type { Pattern, PatternInstance } from "../../types/strata";

interface PatternDetailPanelProps {
  pattern: Pattern;
}

/** Show details of a selected pattern: name, metadata, drum grid, instance list. */
export function PatternDetailPanel({ pattern }: PatternDetailPanelProps) {
  return (
    <div className="px-4 py-3 bg-gray-950 rounded border border-gray-800">
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <span className="text-sm font-semibold text-gray-200 font-mono">
          {pattern.name}
        </span>
        <span className="text-xs px-1.5 py-0.5 bg-gray-800 text-gray-400 rounded">
          {pattern.pattern_type.replace("_", " ")}
        </span>
        {pattern.stem && (
          <span className="text-xs px-1.5 py-0.5 bg-gray-800 text-gray-400 rounded">
            {pattern.stem}
          </span>
        )}
        <span className="text-xs text-gray-500">
          {pattern.template.duration_bars} bar{pattern.template.duration_bars !== 1 ? "s" : ""}
          {" / "}
          {pattern.template.duration_seconds.toFixed(1)}s
        </span>
        {pattern.tags.length > 0 && (
          <div className="flex gap-1 ml-auto">
            {pattern.tags.map((tag) => (
              <span key={tag} className="text-xs px-1.5 py-0.5 bg-gray-900 text-gray-500 rounded">
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Template visualization */}
        <div>
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            Template
          </span>
          {pattern.pattern_type === "drum_groove" || pattern.pattern_type === "perc_fill" ? (
            <DrumGrid pattern={pattern} />
          ) : (
            <EventList pattern={pattern} />
          )}
        </div>

        {/* Instance list */}
        <div>
          <span className="text-xs text-gray-500 uppercase tracking-wider">
            Instances ({pattern.instances.length})
          </span>
          <div className="mt-2 flex flex-col gap-1 max-h-40 overflow-y-auto">
            {pattern.instances.map((inst, i) => (
              <InstanceRow key={i} instance={inst} index={i} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Drum Grid ---

/** Instrument rows to show in the drum grid, derived from template events. */
const DRUM_INSTRUMENTS = ["kick", "snare", "clap", "hihat"] as const;
const DRUM_ROW_LABELS: Record<string, string> = {
  kick: "K",
  snare: "S",
  clap: "C",
  hihat: "H",
};

function DrumGrid({ pattern }: { pattern: Pattern }) {
  const slots = pattern.template.duration_bars * 16; // 16th-note resolution
  const templateDuration = pattern.template.duration_seconds;

  // Build a grid: rows × slots
  const grid = new Map<string, boolean[]>();
  for (const inst of DRUM_INSTRUMENTS) {
    grid.set(inst, new Array(slots).fill(false));
  }

  // Place events into slots
  for (const event of pattern.template.events) {
    const row = grid.get(event.type);
    if (!row) continue;
    // Map timestamp to slot index
    const slot = Math.round((event.timestamp / templateDuration) * slots) % slots;
    if (slot >= 0 && slot < slots) {
      row[slot] = true;
    }
  }

  // Only show instruments that have at least one hit
  const activeInstruments = DRUM_INSTRUMENTS.filter((inst) => {
    const row = grid.get(inst);
    return row?.some(Boolean);
  });

  if (activeInstruments.length === 0) {
    return <p className="mt-2 text-xs text-gray-600">No drum events in template.</p>;
  }

  // Determine visible columns (cap at 32 for readability)
  const visibleSlots = Math.min(slots, 32);

  return (
    <div className="mt-2 font-mono text-xs">
      {activeInstruments.map((inst) => {
        const row = grid.get(inst)!;
        return (
          <div key={inst} className="flex items-center gap-0.5 mb-0.5">
            <span className="w-4 text-gray-500 text-right mr-1">
              {DRUM_ROW_LABELS[inst]}
            </span>
            {Array.from({ length: visibleSlots }, (_, i) => {
              const isHit = row[i];
              const isDownbeat = i % 16 === 0;
              const isBeat = i % 4 === 0;
              return (
                <div
                  key={i}
                  className={`w-3 h-3 rounded-sm ${
                    isHit
                      ? "bg-white/80"
                      : isDownbeat
                        ? "bg-gray-700"
                        : isBeat
                          ? "bg-gray-800"
                          : "bg-gray-900"
                  }`}
                />
              );
            })}
          </div>
        );
      })}
      {/* Beat markers */}
      <div className="flex items-center gap-0.5 mt-0.5">
        <span className="w-4 mr-1" />
        {Array.from({ length: visibleSlots }, (_, i) => (
          <div key={i} className="w-3 text-center">
            {i % 4 === 0 ? (
              <span className="text-gray-600" style={{ fontSize: "7px" }}>
                {Math.floor(i / 4) + 1}
              </span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Event List (for non-drum patterns) ---

function EventList({ pattern }: { pattern: Pattern }) {
  const events = pattern.template.events;
  if (events.length === 0) {
    return <p className="mt-2 text-xs text-gray-600">No events in template.</p>;
  }

  return (
    <div className="mt-2 flex flex-col gap-0.5 max-h-32 overflow-y-auto">
      {events.slice(0, 20).map((e, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <span className="text-gray-600 font-mono w-10 text-right">
            {e.timestamp.toFixed(2)}s
          </span>
          <span className="text-gray-400">{e.type}</span>
          {e.pitch && <span className="text-gray-500">{e.pitch}</span>}
          <span className="text-gray-600">
            i={e.intensity.toFixed(2)}
          </span>
        </div>
      ))}
      {events.length > 20 && (
        <span className="text-xs text-gray-600">
          +{events.length - 20} more events
        </span>
      )}
    </div>
  );
}

// --- Instance Row ---

const VARIATION_BADGE: Record<string, { label: string; cls: string }> = {
  exact: { label: "exact", cls: "text-gray-500 bg-gray-900" },
  minor: { label: "minor", cls: "text-yellow-400 bg-yellow-950" },
  major: { label: "major", cls: "text-red-400 bg-red-950" },
  fill: { label: "fill", cls: "text-orange-400 bg-orange-950" },
};

function InstanceRow({ instance, index }: { instance: PatternInstance; index: number }) {
  const badge = VARIATION_BADGE[instance.variation] ?? VARIATION_BADGE.exact;
  return (
    <div className="flex items-center gap-2 text-xs py-0.5">
      <span className="text-gray-600 w-4 text-right">{index + 1}</span>
      <span className="text-gray-400 font-mono">
        bar {instance.bar_start}–{instance.bar_end}
      </span>
      <span className="text-gray-500 font-mono">
        {instance.start.toFixed(1)}s–{instance.end.toFixed(1)}s
      </span>
      <span className={`px-1 py-0.5 rounded text-xs ${badge.cls}`}>
        {badge.label}
      </span>
      {instance.variation_description && (
        <span className="text-gray-600 truncate">{instance.variation_description}</span>
      )}
    </div>
  );
}
