import type { EventType } from "../../types/events";
import { EVENT_COLORS } from "../../types/events";

const ALL_EVENT_TYPES: EventType[] = ["kick", "snare", "clap", "hihat", "riser", "faller", "stab"];

interface EventTypeTogglesProps {
  visibleTypes: Set<string>;
  onToggle: (type: EventType) => void;
  compact?: boolean;
}

export function EventTypeToggles({ visibleTypes, onToggle, compact }: EventTypeTogglesProps) {
  return (
    <div className={`flex items-center gap-1.5 ${compact ? "" : "flex-wrap"}`}>
      <span className="text-xs text-gray-500 mr-1">Events:</span>
      {ALL_EVENT_TYPES.map((type) => {
        const isVisible = visibleTypes.has(type);
        const color = EVENT_COLORS[type];
        return (
          <button
            key={type}
            onClick={() => onToggle(type)}
            className={`px-1.5 py-0.5 text-xs rounded transition-colors border ${
              isVisible
                ? "border-current"
                : "border-gray-700 text-gray-600 line-through"
            }`}
            style={isVisible ? { color, borderColor: color } : undefined}
            title={`${isVisible ? "Hide" : "Show"} ${type} events`}
          >
            {type}
          </button>
        );
      })}
    </div>
  );
}
