/**
 * EventStats — per-event-type counts, density, and average confidence.
 */

import type { MusicalEvent, EventType } from "../../types/events";
import { EVENT_COLORS } from "../../types/events";

interface EventStatsProps {
  events: MusicalEvent[];
  totalBars: number;
  duration: number;
}

interface TypeStats {
  count: number;
  avgIntensity: number;
  eventsPerBar: number;
}

export function EventStats({ events, totalBars, duration }: EventStatsProps) {
  // Group by type
  const byType = new Map<EventType, MusicalEvent[]>();
  for (const e of events) {
    const list = byType.get(e.type) ?? [];
    list.push(e);
    byType.set(e.type, list);
  }

  const stats: [EventType, TypeStats][] = [];
  for (const [type, typeEvents] of byType) {
    const avgIntensity =
      typeEvents.reduce((sum, e) => sum + e.intensity, 0) / typeEvents.length;
    stats.push([
      type,
      {
        count: typeEvents.length,
        avgIntensity,
        eventsPerBar: totalBars > 0 ? typeEvents.length / totalBars : 0,
      },
    ]);
  }

  // Sort by count descending
  stats.sort((a, b) => b[1].count - a[1].count);

  return (
    <div>
      <h3 className="text-sm font-medium text-slate-400 mb-2">Detection Stats</h3>
      <div className="text-xs text-slate-500 mb-3">
        {events.length} events · {totalBars} bars · {duration.toFixed(1)}s
      </div>
      <div className="space-y-1.5">
        {stats.map(([type, s]) => (
          <div
            key={type}
            className="flex items-center justify-between text-xs font-mono"
          >
            <div className="flex items-center gap-2">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: EVENT_COLORS[type] }}
              />
              <span className="text-slate-300">{type}</span>
            </div>
            <div className="flex gap-4 text-slate-500">
              <span>{s.count}</span>
              <span>{s.eventsPerBar.toFixed(1)}/bar</span>
              <span>{(s.avgIntensity * 100).toFixed(0)}%</span>
            </div>
          </div>
        ))}
        {stats.length === 0 && (
          <div className="text-slate-600 text-xs italic">No events detected</div>
        )}
      </div>
    </div>
  );
}
