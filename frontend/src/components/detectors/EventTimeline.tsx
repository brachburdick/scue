/**
 * EventTimeline — waveform canvas with event markers overlaid.
 *
 * Renders detected events on top of the track waveform:
 * - Kicks: vertical red lines
 * - Snares/claps: colored markers
 * - Risers/fallers: shaded horizontal regions
 * - Stabs: short colored bars
 * - Section labels as background color bands
 */

import { useRef, useEffect, useCallback } from "react";
import type { MusicalEvent, EventType } from "../../types/events";
import { EVENT_COLORS, SECTION_COLORS } from "../../types/events";

interface Section {
  label: string;
  start: number;
  end: number;
}

interface Waveform {
  low: number[];
  mid: number[];
  high: number[];
  sample_rate: number;
  duration: number;
}

interface EventTimelineProps {
  events: MusicalEvent[];
  sections: Section[];
  waveform: Waveform | null;
  duration: number;
  visibleTypes: Set<EventType>;
  minConfidence: number;
  /** Viewport in seconds */
  viewStart: number;
  viewEnd: number;
}

export function EventTimeline({
  events,
  sections,
  waveform,
  duration,
  visibleTypes,
  minConfidence,
  viewStart,
  viewEnd,
}: EventTimelineProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    const viewDuration = viewEnd - viewStart;

    // Helper: time → x
    const timeToX = (t: number) => ((t - viewStart) / viewDuration) * w;

    // Clear
    ctx.fillStyle = "#0f172a"; // slate-900
    ctx.fillRect(0, 0, w, h);

    // Draw section background bands
    for (const section of sections) {
      if (section.end < viewStart || section.start > viewEnd) continue;
      const x1 = Math.max(0, timeToX(section.start));
      const x2 = Math.min(w, timeToX(section.end));
      ctx.fillStyle = SECTION_COLORS[section.label] ?? "rgba(100, 100, 100, 0.1)";
      ctx.fillRect(x1, 0, x2 - x1, h);

      // Section label
      ctx.fillStyle = "rgba(255, 255, 255, 0.3)";
      ctx.font = "10px sans-serif";
      ctx.fillText(section.label, x1 + 4, 12);
    }

    // Draw waveform (simplified 3-band)
    if (waveform && waveform.low.length > 0) {
      const samplesPerSec = waveform.sample_rate;
      const midY = h * 0.5;
      const amp = h * 0.35;

      const startSample = Math.floor(viewStart * samplesPerSec);
      const endSample = Math.ceil(viewEnd * samplesPerSec);
      const pixelsPerSample = w / (endSample - startSample);

      for (let i = startSample; i < endSample && i < waveform.low.length; i++) {
        const x = (i - startSample) * pixelsPerSample;
        const lo = waveform.low[i] ?? 0;
        const mid_ = waveform.mid[i] ?? 0;
        const hi = waveform.high[i] ?? 0;

        // Bass (red channel) — bottom half
        ctx.fillStyle = `rgba(239, 68, 68, ${0.3 + lo * 0.5})`;
        ctx.fillRect(x, midY, Math.max(1, pixelsPerSample), lo * amp);

        // Mids (green) — centered
        ctx.fillStyle = `rgba(34, 197, 94, ${0.3 + mid_ * 0.4})`;
        ctx.fillRect(x, midY - mid_ * amp * 0.5, Math.max(1, pixelsPerSample), mid_ * amp);

        // Highs (blue) — top half
        ctx.fillStyle = `rgba(59, 130, 246, ${0.2 + hi * 0.4})`;
        ctx.fillRect(x, midY - hi * amp, Math.max(1, pixelsPerSample), hi * amp * 0.5);
      }
    }

    // Filter events by visibility and confidence
    const visibleEvents = events.filter(
      (e) => visibleTypes.has(e.type) && e.intensity >= minConfidence
    );

    // Draw events
    for (const event of visibleEvents) {
      if (event.timestamp > viewEnd) continue;
      const eventEnd = event.timestamp + (event.duration ?? 0);
      if (eventEnd < viewStart) continue;

      const color = EVENT_COLORS[event.type] ?? "#ffffff";
      const x = timeToX(event.timestamp);

      if (event.type === "riser" || event.type === "faller") {
        // Shaded region
        const x2 = timeToX(event.timestamp + (event.duration ?? 2));
        const alpha = 0.15 + event.intensity * 0.25;
        ctx.fillStyle = color + Math.round(alpha * 255).toString(16).padStart(2, "0");
        ctx.fillRect(x, 0, x2 - x, h);

        // Top border
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, event.type === "riser" ? h * 0.8 : h * 0.2);
        ctx.lineTo(x2, event.type === "riser" ? h * 0.2 : h * 0.8);
        ctx.stroke();
      } else if (event.type === "stab") {
        // Short colored bar
        const barWidth = Math.max(3, timeToX(event.timestamp + (event.duration ?? 0.1)) - x);
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.4 + event.intensity * 0.5;
        ctx.fillRect(x, h * 0.1, barWidth, h * 0.15);
        ctx.globalAlpha = 1;
      } else {
        // Percussion: vertical line
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.3 + event.intensity * 0.6;
        ctx.beginPath();
        ctx.moveTo(x, h * 0.3);
        ctx.lineTo(x, h * 0.9);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }
  }, [events, sections, waveform, duration, visibleTypes, minConfidence, viewStart, viewEnd]);

  useEffect(() => {
    draw();
    const handleResize = () => draw();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [draw]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-48 rounded-lg border border-slate-700"
      style={{ imageRendering: "pixelated" }}
    />
  );
}
