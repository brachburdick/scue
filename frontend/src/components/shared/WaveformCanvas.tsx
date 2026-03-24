import { useRef, useEffect, useCallback } from "react";
import type { RGBWaveform, Section, WaveformRenderParams } from "../../types";
import { drawBeatgridLines } from "./drawBeatgridLines";

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

  /** Beatgrid data for overlay lines */
  beats?: number[];
  downbeats?: number[];

  viewStart: number;
  viewEnd: number;
  onViewChange?: (start: number, end: number) => void;

  height?: number;

  /** Optional rendering params from waveform preset system */
  renderParams?: WaveformRenderParams;
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

/** Parse a hex color string to {r, g, b} 0-255 */
function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const h = hex.replace("#", "");
  return {
    r: parseInt(h.substring(0, 2), 16) || 255,
    g: parseInt(h.substring(2, 4), 16) || 0,
    b: parseInt(h.substring(4, 6), 16) || 0,
  };
}

/** Apply amplitude scaling function */
function applyAmplitudeScale(
  value: number,
  scale: string,
  gamma: number,
  logStrength: number,
): number {
  if (value <= 0) return 0;
  switch (scale) {
    case "sqrt":
      return Math.sqrt(value);
    case "log":
      return Math.log(1 + logStrength * value) / Math.log(1 + logStrength);
    case "gamma":
      return Math.pow(value, gamma);
    default: // linear
      return value;
  }
}

/** Clamp value between 0 and 1 */
function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
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
  beats,
  downbeats,
  viewStart,
  viewEnd,
  onViewChange,
  height = 160,
  renderParams,
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

      // Extract render params (or use defaults)
      const p = renderParams;
      const lowGain = p?.lowGain ?? 1.0;
      const midGain = p?.midGain ?? 1.0;
      const highGain = p?.highGain ?? 1.0;
      const normMode = p?.normalization ?? "global";
      const ampScale = p?.amplitudeScale ?? "linear";
      const gammaVal = p?.gamma ?? 1.0;
      const logStr = p?.logStrength ?? 10;
      const noiseFloor = p?.noiseFloor ?? 0.001;
      const peakNorm = p?.peakNormalize ?? true;
      const colorMode = p?.colorMode ?? "rgb_blend";
      const satMul = p?.saturation ?? 1.0;
      const briMul = p?.brightness ?? 1.0;
      const minBri = p?.minBrightness ?? 0.0;

      // Parse custom colors for three_band_overlap or custom rgb_blend
      const lowRgb = p ? hexToRgb(p.lowColor) : { r: 255, g: 0, b: 0 };
      const midRgb = p ? hexToRgb(p.midColor) : { r: 0, g: 255, b: 0 };
      const highRgb = p ? hexToRgb(p.highColor) : { r: 0, g: 0, b: 255 };

      // Pre-compute per-band peak for per_band normalization
      let lowPeak = 0, midPeak = 0, highPeak = 0;
      if (normMode === "per_band" || normMode === "weighted") {
        for (let i = startSample; i < endSample; i++) {
          const lv = (waveform.low[i] ?? 0) * lowGain;
          const mv = (waveform.mid[i] ?? 0) * midGain;
          const hv = (waveform.high[i] ?? 0) * highGain;
          if (lv > lowPeak) lowPeak = lv;
          if (mv > midPeak) midPeak = mv;
          if (hv > highPeak) highPeak = hv;
        }
        // Prevent division by zero
        if (lowPeak === 0) lowPeak = 1;
        if (midPeak === 0) midPeak = 1;
        if (highPeak === 0) highPeak = 1;
      }

      // Global peak for peak normalization
      let globalPeak = 0;
      if (peakNorm) {
        for (let i = startSample; i < endSample; i++) {
          let lv = (waveform.low[i] ?? 0) * lowGain;
          let mv = (waveform.mid[i] ?? 0) * midGain;
          let hv = (waveform.high[i] ?? 0) * highGain;
          if (normMode === "per_band" || normMode === "weighted") {
            lv /= lowPeak;
            mv /= midPeak;
            hv /= highPeak;
          }
          const amp = Math.max(lv, mv, hv);
          if (amp > globalPeak) globalPeak = amp;
        }
        if (globalPeak === 0) globalPeak = 1;
      }

      /** Process one sample/pixel's band values into draw instructions */
      function processBar(rawLow: number, rawMid: number, rawHigh: number) {
        // Step 2: apply gain
        let low = rawLow * lowGain;
        let mid = rawMid * midGain;
        let high = rawHigh * highGain;

        // Step 4: normalization
        if (normMode === "per_band" || normMode === "weighted") {
          low /= lowPeak;
          mid /= midPeak;
          high /= highPeak;
        }

        // Step 5: compute amplitude
        const amplitude = Math.max(low, mid, high);

        // Step 7: noise floor
        if (amplitude < noiseFloor) return null;

        // Peak normalization
        let normAmp = peakNorm ? amplitude / globalPeak : amplitude;

        // Step 6: amplitude scaling
        normAmp = applyAmplitudeScale(normAmp, ampScale, gammaVal, logStr);

        if (colorMode === "three_band_overlap") {
          // Each band gets independent height
          let lh = peakNorm ? low / globalPeak : low;
          let mh = peakNorm ? mid / globalPeak : mid;
          let hh = peakNorm ? high / globalPeak : high;
          lh = applyAmplitudeScale(lh, ampScale, gammaVal, logStr);
          mh = applyAmplitudeScale(mh, ampScale, gammaVal, logStr);
          hh = applyAmplitudeScale(hh, ampScale, gammaVal, logStr);

          // Apply brightness + minBrightness
          lh = clamp01(lh * briMul + minBri);
          mh = clamp01(mh * briMul + minBri);
          hh = clamp01(hh * briMul + minBri);

          return {
            mode: "overlap" as const,
            layers: [
              { h: lh, r: lowRgb.r, g: lowRgb.g, b: lowRgb.b },
              { h: mh, r: midRgb.r, g: midRgb.g, b: midRgb.b },
              { h: hh, r: highRgb.r, g: highRgb.g, b: highRgb.b },
            ],
          };
        }

        if (colorMode === "mono_blue") {
          // Brightness from spectral centroid approximation
          const total = low + mid + high;
          const centroid = total > 0 ? (mid + high * 2) / (total * 2) : 0;
          const bri = clamp01(centroid * briMul + minBri);
          const barH = clamp01(normAmp * briMul);
          return {
            mode: "single" as const,
            r: Math.round(bri * 100),
            g: Math.round(bri * 150),
            b: Math.round(100 + bri * 155),
            barH,
          };
        }

        // rgb_blend (default)
        if (amplitude < 0.001) return null;
        let r = low / amplitude;
        let g = mid / amplitude;
        let b = high / amplitude;

        // Apply saturation
        if (satMul !== 1.0) {
          const gray = 0.299 * r + 0.587 * g + 0.114 * b;
          r = clamp01(gray + satMul * (r - gray));
          g = clamp01(gray + satMul * (g - gray));
          b = clamp01(gray + satMul * (b - gray));
        }

        // Apply brightness + minBrightness
        r = clamp01(r * briMul + minBri);
        g = clamp01(g * briMul + minBri);
        b = clamp01(b * briMul + minBri);

        // Map to custom colors if not default RGB
        let fr: number, fg: number, fb: number;
        if (p) {
          fr = Math.round(r * lowRgb.r + g * midRgb.r + b * highRgb.r);
          fg = Math.round(r * lowRgb.g + g * midRgb.g + b * highRgb.g);
          fb = Math.round(r * lowRgb.b + g * midRgb.b + b * highRgb.b);
          // Clamp
          fr = Math.min(255, fr);
          fg = Math.min(255, fg);
          fb = Math.min(255, fb);
        } else {
          fr = Math.min(255, Math.round(r * 255));
          fg = Math.min(255, Math.round(g * 255));
          fb = Math.min(255, Math.round(b * 255));
        }

        const barH = clamp01(normAmp * briMul);

        return { mode: "single" as const, r: fr, g: fg, b: fb, barH };
      }

      function drawBar(
        ctx: CanvasRenderingContext2D,
        x: number,
        barWidth: number,
        result: NonNullable<ReturnType<typeof processBar>>,
      ) {
        if (result.mode === "overlap") {
          // Paint layers back to front (low, mid, high)
          for (const layer of result.layers) {
            const bh = layer.h * centerY;
            if (bh < 0.5) continue;
            ctx.fillStyle = `rgb(${layer.r},${layer.g},${layer.b})`;
            ctx.fillRect(x, centerY - bh, barWidth, bh * 2);
          }
        } else {
          const bh = result.barH * centerY;
          if (bh < 0.5) return;
          ctx.fillStyle = `rgb(${result.r},${result.g},${result.b})`;
          ctx.fillRect(x, centerY - bh, barWidth, bh * 2);
        }
      }

      if (samplesPerPixel <= 1) {
        // One bar per sample
        for (let i = startSample; i < endSample; i++) {
          const result = processBar(
            waveform.low[i] ?? 0,
            waveform.mid[i] ?? 0,
            waveform.high[i] ?? 0,
          );
          if (!result) continue;
          const x = timeToX(i / samplesPerSec, viewStart, viewEnd, w);
          const barWidth = Math.max(1, w / sampleCount);
          drawBar(ctx, x, barWidth, result);
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

          const result = processBar(maxLow, maxMid, maxHigh);
          if (!result) continue;
          drawBar(ctx, px, 1, result);
        }
      }
    }

    // --- Beatgrid lines (on top of waveform, below overlays) ---
    if (beats?.length || downbeats?.length) {
      drawBeatgridLines(ctx, beats ?? [], downbeats ?? [], viewStart, viewEnd, w, h);
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
  }, [waveform, sections, energyCurve, duration, highlightedSection, selectedSection, cursorPosition, beats, downbeats, viewStart, viewEnd, height, renderParams]);

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
