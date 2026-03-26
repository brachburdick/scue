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
import { pioneerColor } from "../../utils/pioneerColor";

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

    // Draw waveform — Pioneer-style single blended bar per column
    // Color = frequency ratio (R=low, G=mid, B=high), height = amplitude
    if (waveform && waveform.low.length > 0) {
      const samplesPerSec = waveform.sample_rate;
      const centerY = h * 0.5;

      const startSample = Math.max(0, Math.floor(viewStart * samplesPerSec));
      const endSample = Math.min(waveform.low.length, Math.ceil(viewEnd * samplesPerSec));
      const sampleCount = endSample - startSample;

      if (sampleCount > 0) {
        const samplesPerPixel = sampleCount / w;

        if (samplesPerPixel <= 1) {
          // One bar per sample
          for (let i = startSample; i < endSample; i++) {
            const lo = waveform.low[i] ?? 0;
            const mid_ = waveform.mid[i] ?? 0;
            const hi = waveform.high[i] ?? 0;
            const amplitude = Math.max(lo, mid_, hi);
            if (amplitude < 0.001) continue;

            const { r, g, b } = pioneerColor(lo, mid_, hi);
            const barH = amplitude * centerY;
            const x = ((i - startSample) / sampleCount) * w;
            const barWidth = Math.max(1, w / sampleCount);

            ctx.fillStyle = `rgb(${r},${g},${b})`;
            ctx.fillRect(x, centerY - barH, barWidth, barH * 2);
          }
        } else {
          // Downsample: one bar per pixel
          for (let px = 0; px < w; px++) {
            const time0 = viewStart + (px / w) * viewDuration;
            const time1 = viewStart + ((px + 1) / w) * viewDuration;
            const s0 = Math.max(startSample, Math.floor(time0 * samplesPerSec));
            const s1 = Math.min(endSample, Math.ceil(time1 * samplesPerSec));

            let maxLow = 0, maxMid = 0, maxHigh = 0;
            for (let i = s0; i < s1; i++) {
              if ((waveform.low[i] ?? 0) > maxLow) maxLow = waveform.low[i];
              if ((waveform.mid[i] ?? 0) > maxMid) maxMid = waveform.mid[i];
              if ((waveform.high[i] ?? 0) > maxHigh) maxHigh = waveform.high[i];
            }

            const amplitude = Math.max(maxLow, maxMid, maxHigh);
            if (amplitude < 0.001) continue;

            const { r, g, b } = pioneerColor(maxLow, maxMid, maxHigh);
            const barH = amplitude * centerY;

            ctx.fillStyle = `rgb(${r},${g},${b})`;
            ctx.fillRect(px, centerY - barH, 1, barH * 2);
          }
        }
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
