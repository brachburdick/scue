import { useRef, useEffect, useCallback } from "react";
import type { RGBWaveform, Section } from "../../types";

// --- Color constants ---

/**
 * Pioneer-style RGB color mapping:
 *   R = low  (bass → red)
 *   G = mid  (mids → green)
 *   B = high (highs → blue)
 *
 * Color is normalized by the max channel so it represents the frequency
 * *ratio*, while bar height represents overall *amplitude*. This means
 * a quiet bass-heavy section is short but red, not short and dark.
 *
 * Result: kick = red, hi-hat = blue, vocal = green/cyan,
 *         kick+hat = magenta, full spectrum = white/pink.
 */

/** Section overlay colors by label */
const SECTION_COLORS: Record<string, string> = {
  intro: "rgba(100, 100, 100, 0.15)",
  verse: "rgba(59, 130, 246, 0.15)",
  build: "rgba(234, 179, 8, 0.15)",
  drop: "rgba(239, 68, 68, 0.2)",
  breakdown: "rgba(168, 85, 247, 0.15)",
  fakeout: "rgba(239, 68, 68, 0.1)",
  outro: "rgba(100, 100, 100, 0.15)",
};

const SECTION_HIGHLIGHT_COLORS: Record<string, string> = {
  intro: "rgba(100, 100, 100, 0.30)",
  verse: "rgba(59, 130, 246, 0.30)",
  build: "rgba(234, 179, 8, 0.30)",
  drop: "rgba(239, 68, 68, 0.40)",
  breakdown: "rgba(168, 85, 247, 0.30)",
  fakeout: "rgba(239, 68, 68, 0.20)",
  outro: "rgba(100, 100, 100, 0.30)",
};

const SECTION_BORDER_COLORS: Record<string, string> = {
  intro: "rgba(100, 100, 100, 0.5)",
  verse: "rgba(59, 130, 246, 0.5)",
  build: "rgba(234, 179, 8, 0.5)",
  drop: "rgba(239, 68, 68, 0.6)",
  breakdown: "rgba(168, 85, 247, 0.5)",
  fakeout: "rgba(239, 68, 68, 0.4)",
  outro: "rgba(100, 100, 100, 0.5)",
};

// --- Props ---

export interface WaveformCanvasProps {
  waveform: RGBWaveform;
  sections?: Section[];
  energyCurve?: number[];
  duration: number;

  highlightedSection?: number | null;
  selectedSection?: number | null;
  onSectionHover?: (index: number | null) => void;
  onSectionClick?: (index: number) => void;
  onTimeClick?: (seconds: number) => void;

  cursorPosition?: number | null;

  viewStart: number;
  viewEnd: number;
  onViewChange?: (start: number, end: number) => void;

  height?: number;
}

// --- Helpers ---

function timeToX(time: number, viewStart: number, viewEnd: number, width: number): number {
  return ((time - viewStart) / (viewEnd - viewStart)) * width;
}

function xToTime(x: number, viewStart: number, viewEnd: number, width: number): number {
  return viewStart + (x / width) * (viewEnd - viewStart);
}

function sectionIndexAtTime(sections: Section[], time: number): number | null {
  const idx = sections.findIndex((s) => time >= s.start && time < s.end);
  return idx >= 0 ? idx : null;
}

// --- Component ---

export function WaveformCanvas({
  waveform,
  sections,
  energyCurve,
  duration,
  highlightedSection,
  selectedSection,
  onSectionHover,
  onSectionClick,
  onTimeClick,
  cursorPosition,
  viewStart,
  viewEnd,
  onViewChange,
  height = 160,
}: WaveformCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const widthRef = useRef(0);
  const rafRef = useRef(0);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartViewStart = useRef(0);
  const dragStartViewEnd = useRef(0);

  // Render function
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = widthRef.current;
    const h = height;

    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, w, h);

    const viewDuration = viewEnd - viewStart;
    if (viewDuration <= 0 || w <= 0) return;

    // --- Section overlays (behind waveform) ---
    if (sections) {
      for (let i = 0; i < sections.length; i++) {
        const sec = sections[i];
        const x1 = Math.max(0, timeToX(sec.start, viewStart, viewEnd, w));
        const x2 = Math.min(w, timeToX(sec.end, viewStart, viewEnd, w));
        if (x2 <= 0 || x1 >= w) continue;

        const isHighlighted = highlightedSection === i || selectedSection === i;
        const fill = isHighlighted
          ? (SECTION_HIGHLIGHT_COLORS[sec.label] ?? "rgba(100,100,100,0.30)")
          : (SECTION_COLORS[sec.label] ?? "rgba(100,100,100,0.15)");

        ctx.fillStyle = fill;
        ctx.fillRect(x1, 0, x2 - x1, h);

        // Boundary line
        const borderColor = SECTION_BORDER_COLORS[sec.label] ?? "rgba(100,100,100,0.5)";
        ctx.strokeStyle = borderColor;
        ctx.lineWidth = isHighlighted ? 2 : 1;
        if (sec.label === "fakeout" && !isHighlighted) {
          ctx.setLineDash([4, 4]);
        }
        ctx.beginPath();
        ctx.moveTo(x1, 0);
        ctx.lineTo(x1, h);
        ctx.stroke();
        ctx.setLineDash([]);

        // Low confidence: dashed border on right
        if (sec.confidence < 0.3) {
          ctx.setLineDash([3, 3]);
          ctx.strokeStyle = "rgba(255,255,255,0.15)";
          ctx.strokeRect(x1, 0, x2 - x1, h);
          ctx.setLineDash([]);
        }

        // Section label
        if (x2 - x1 > 30) {
          ctx.font = "10px sans-serif";
          ctx.fillStyle = "rgba(255,255,255,0.5)";
          ctx.fillText(sec.label, x1 + 4, 12);
        }

        // Highlight border
        if (isHighlighted) {
          ctx.strokeStyle = borderColor;
          ctx.lineWidth = 2;
          ctx.strokeRect(x1, 0, x2 - x1, h);
        }
      }
    }

    // --- Waveform bars ---
    const samplesPerSec = waveform.sample_rate || 60;
    const startSample = Math.max(0, Math.floor(viewStart * samplesPerSec));
    const endSample = Math.min(waveform.low.length, Math.ceil(viewEnd * samplesPerSec));
    const sampleCount = endSample - startSample;

    if (sampleCount > 0) {
      const samplesPerPixel = sampleCount / w;
      const centerY = h / 2;

      // Pioneer-style: color = frequency ratio, height = amplitude.
      // Normalize color channels by the max so the blend always shows
      // which bands dominate, regardless of overall loudness.
      function blendColor(low: number, mid: number, high: number) {
        const amplitude = Math.max(low, mid, high);
        if (amplitude < 0.001) return null;
        // R=low (bass), G=mid, B=high — matches Pioneer CDJ color mapping
        const r = Math.min(255, Math.round((low / amplitude) * 255));
        const g = Math.min(255, Math.round((mid / amplitude) * 255));
        const b = Math.min(255, Math.round((high / amplitude) * 255));
        return { r, g, b, amplitude };
      }

      if (samplesPerPixel <= 1) {
        // One bar per sample
        for (let i = startSample; i < endSample; i++) {
          const result = blendColor(
            waveform.low[i] ?? 0,
            waveform.mid[i] ?? 0,
            waveform.high[i] ?? 0,
          );
          if (!result) continue;
          const barH = result.amplitude * centerY;
          const x = timeToX(i / samplesPerSec, viewStart, viewEnd, w);
          const barWidth = Math.max(1, w / sampleCount);

          ctx.fillStyle = `rgb(${result.r},${result.g},${result.b})`;
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

          const result = blendColor(maxLow, maxMid, maxHigh);
          if (!result) continue;
          const barH = result.amplitude * centerY;

          ctx.fillStyle = `rgb(${result.r},${result.g},${result.b})`;
          ctx.fillRect(px, centerY - barH, 1, barH * 2);
        }
      }
    }

    // --- Energy curve overlay ---
    if (energyCurve && energyCurve.length > 1) {
      const energySamplesPerSec = energyCurve.length / duration;
      ctx.beginPath();
      ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
      ctx.lineWidth = 1.5;

      let first = true;
      for (let px = 0; px < w; px++) {
        const time = viewStart + (px / w) * viewDuration;
        const energyIdx = time * energySamplesPerSec;
        const i0 = Math.floor(energyIdx);
        const i1 = Math.min(i0 + 1, energyCurve.length - 1);
        const frac = energyIdx - i0;
        const val = (energyCurve[i0] ?? 0) * (1 - frac) + (energyCurve[i1] ?? 0) * frac;
        const y = h - val * h;

        if (first) {
          ctx.moveTo(px, y);
          first = false;
        } else {
          ctx.lineTo(px, y);
        }
      }
      ctx.stroke();
    }

    // --- Cursor line ---
    if (cursorPosition != null && cursorPosition >= viewStart && cursorPosition <= viewEnd) {
      const cx = timeToX(cursorPosition, viewStart, viewEnd, w);

      // Glow
      ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, h);
      ctx.stroke();

      // Main line
      ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, h);
      ctx.stroke();
    }
  }, [waveform, sections, energyCurve, duration, highlightedSection, selectedSection, cursorPosition, viewStart, viewEnd, height]);

  // Observe resize
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        widthRef.current = entry.contentRect.width;
        cancelAnimationFrame(rafRef.current);
        rafRef.current = requestAnimationFrame(render);
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, [render]);

  // Re-render on data changes
  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(render);
  }, [render]);

  // --- Mouse interaction ---

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (isDragging.current && onViewChange) {
        const dx = e.clientX - dragStartX.current;
        const pixelsPerSec = widthRef.current / (dragStartViewEnd.current - dragStartViewStart.current);
        const dt = -dx / pixelsPerSec;
        let newStart = dragStartViewStart.current + dt;
        let newEnd = dragStartViewEnd.current + dt;

        // Clamp to bounds
        if (newStart < 0) {
          newEnd -= newStart;
          newStart = 0;
        }
        if (newEnd > duration) {
          newStart -= newEnd - duration;
          newEnd = duration;
        }
        newStart = Math.max(0, newStart);

        onViewChange(newStart, newEnd);
        return;
      }

      if (!sections || !onSectionHover) return;
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = e.clientX - rect.left;
      const time = xToTime(x, viewStart, viewEnd, widthRef.current);
      onSectionHover(sectionIndexAtTime(sections, time));
    },
    [sections, onSectionHover, viewStart, viewEnd, duration, onViewChange],
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      isDragging.current = true;
      dragStartX.current = e.clientX;
      dragStartViewStart.current = viewStart;
      dragStartViewEnd.current = viewEnd;
    },
    [viewStart, viewEnd],
  );

  const handleMouseUp = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const wasDrag = Math.abs(e.clientX - dragStartX.current) > 3;
      isDragging.current = false;

      if (wasDrag) return;

      // Click (not drag)
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = e.clientX - rect.left;
      const time = xToTime(x, viewStart, viewEnd, widthRef.current);

      if (sections && onSectionClick) {
        const idx = sectionIndexAtTime(sections, time);
        if (idx !== null) {
          onSectionClick(idx);
          return;
        }
      }

      onTimeClick?.(time);
    },
    [sections, onSectionClick, onTimeClick, viewStart, viewEnd],
  );

  const handleMouseLeave = useCallback(() => {
    isDragging.current = false;
    onSectionHover?.(null);
  }, [onSectionHover]);

  const handleWheel = useCallback(
    (e: React.WheelEvent<HTMLCanvasElement>) => {
      if (!onViewChange) return;
      e.preventDefault();

      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;

      const mouseX = e.clientX - rect.left;
      const mouseTime = xToTime(mouseX, viewStart, viewEnd, widthRef.current);

      const zoomFactor = e.deltaY > 0 ? 1.2 : 1 / 1.2;
      const viewDuration = viewEnd - viewStart;
      let newDuration = viewDuration * zoomFactor;

      // Clamp zoom range
      const MIN_VIEW = 2;
      newDuration = Math.max(MIN_VIEW, Math.min(duration, newDuration));

      // Keep mouse position anchored
      const mouseRatio = (mouseTime - viewStart) / viewDuration;
      let newStart = mouseTime - mouseRatio * newDuration;
      let newEnd = newStart + newDuration;

      // Clamp to bounds
      if (newStart < 0) {
        newEnd -= newStart;
        newStart = 0;
      }
      if (newEnd > duration) {
        newStart -= newEnd - duration;
        newEnd = duration;
      }
      newStart = Math.max(0, newStart);
      newEnd = Math.min(duration, newEnd);

      onViewChange(newStart, newEnd);
    },
    [viewStart, viewEnd, duration, onViewChange],
  );

  const handleDoubleClick = useCallback(() => {
    onViewChange?.(0, duration);
  }, [duration, onViewChange]);

  return (
    <div ref={containerRef} className="w-full bg-gray-950 rounded border border-gray-800">
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height, display: "block", cursor: isDragging.current ? "grabbing" : "grab" }}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onWheel={handleWheel}
        onDoubleClick={handleDoubleClick}
      />
    </div>
  );
}
