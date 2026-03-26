import { useRef, useEffect, useCallback, useMemo, useState } from "react";
import type {
  ArrangementFormula,
  StemType,
} from "../../types/strata";

// --- Constants ---

const LANE_HEIGHT = 48;
const LANE_GAP = 2;
const BLOCK_PAD_X = 4;
const BLOCK_PAD_Y = 4;
export const LABEL_WIDTH = 56;

const STEM_COLORS: Record<StemType, { activity: string; block: string; blockHover: string; text: string; border: string }> = {
  drums: {
    activity: "rgba(239, 68, 68, 0.12)",
    block: "rgba(239, 68, 68, 0.5)",
    blockHover: "rgba(239, 68, 68, 0.65)",
    text: "rgba(255, 200, 200, 0.9)",
    border: "rgba(239, 68, 68, 0.7)",
  },
  bass: {
    activity: "rgba(59, 130, 246, 0.12)",
    block: "rgba(59, 130, 246, 0.5)",
    blockHover: "rgba(59, 130, 246, 0.65)",
    text: "rgba(200, 220, 255, 0.9)",
    border: "rgba(59, 130, 246, 0.7)",
  },
  vocals: {
    activity: "rgba(168, 85, 247, 0.12)",
    block: "rgba(168, 85, 247, 0.5)",
    blockHover: "rgba(168, 85, 247, 0.65)",
    text: "rgba(230, 210, 255, 0.9)",
    border: "rgba(168, 85, 247, 0.7)",
  },
  other: {
    activity: "rgba(34, 197, 94, 0.12)",
    block: "rgba(34, 197, 94, 0.5)",
    blockHover: "rgba(34, 197, 94, 0.65)",
    text: "rgba(200, 255, 220, 0.9)",
    border: "rgba(34, 197, 94, 0.7)",
  },
};

const VARIATION_COLORS: Record<string, string> = {
  exact: "transparent",
  minor: "rgba(234, 179, 8, 0.7)",
  major: "rgba(239, 68, 68, 0.7)",
  fill: "rgba(249, 115, 22, 0.8)",
};

const TRANSITION_COLORS: Record<string, string> = {
  layer_enter: "rgba(34, 197, 94, 0.7)",
  layer_exit: "rgba(239, 68, 68, 0.6)",
  pattern_change: "rgba(234, 179, 8, 0.6)",
  fill: "rgba(249, 115, 22, 0.5)",
  energy_shift: "rgba(59, 130, 246, 0.5)",
  breakdown: "rgba(168, 85, 247, 0.6)",
  drop_impact: "rgba(239, 68, 68, 0.7)",
};

// --- Props ---

/** Event color mapping — must match types/events.ts EVENT_COLORS */
const EVENT_TICK_COLORS: Record<string, string> = {
  kick: "#ef4444",
  snare: "#f97316",
  clap: "#eab308",
  hihat: "#84cc16",
  riser: "#06b6d4",
  faller: "#8b5cf6",
  stab: "#ec4899",
};

export interface ArrangementMapProps {
  formula: ArrangementFormula;
  duration: number;
  viewStart: number;
  viewEnd: number;
  onViewChange?: (start: number, end: number) => void;
  selectedPatternId?: string | null;
  hoveredPatternId?: string | null;
  onPatternSelect?: (patternId: string | null) => void;
  onPatternHover?: (patternId: string | null) => void;
  visibleEventTypes?: Set<string>;
  showStemWaveforms?: boolean;
  showPatternBlocks?: boolean;
  /** External events (e.g. M7 track-level) to overlay when stem events are empty */
  externalEvents?: Array<{ type: string; timestamp: number; stem: string | null }>;
  /** Real-time playback cursor position in seconds (live tier). */
  playbackCursorTime?: number;
}

// --- Helpers ---

function timeToX(time: number, viewStart: number, viewEnd: number, width: number): number {
  return ((time - viewStart) / (viewEnd - viewStart)) * width;
}

function xToTime(x: number, viewStart: number, viewEnd: number, width: number): number {
  return viewStart + (x / width) * (viewEnd - viewStart);
}

function getStemLanes(formula: ArrangementFormula): StemType[] {
  const present = new Set<StemType>();
  for (const stem of formula.stems) {
    if (stem.activity.length > 0 || stem.patterns.length > 0) {
      present.add(stem.stem_type);
    }
  }
  for (const p of formula.patterns) {
    if (p.stem) present.add(p.stem);
  }
  const order: StemType[] = ["drums", "bass", "other", "vocals"];
  return order.filter((s) => present.has(s));
}

// --- Hit-test block data ---

interface PatternBlock {
  patternId: string;
  patternName: string;
  stem: StemType | null;
  barStart: number;
  barEnd: number;
  variation: string;
  variationDesc: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Tooltip info for display. */
interface TooltipInfo {
  x: number;
  y: number;
  patternName: string;
  stem: string;
  bars: string;
  variation: string;
  variationDesc: string;
}

// --- Component ---

export function ArrangementMap({
  formula,
  duration,
  viewStart,
  viewEnd,
  onViewChange,
  selectedPatternId,
  hoveredPatternId,
  onPatternSelect,
  onPatternHover,
  visibleEventTypes,
  showStemWaveforms,
  showPatternBlocks = true,
  externalEvents,
  playbackCursorTime,
}: ArrangementMapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const widthRef = useRef(0);
  const rafRef = useRef(0);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartViewStart = useRef(0);
  const dragStartViewEnd = useRef(0);
  const blocksRef = useRef<PatternBlock[]>([]);
  /** Currently hovered block (internal, for canvas highlight). */
  const hoveredBlockRef = useRef<string | null>(null);
  // Refs for native wheel handler (avoids stale closures)
  const viewStartRef = useRef(viewStart);
  const viewEndRef = useRef(viewEnd);
  const durationRef = useRef(duration);
  const onViewChangeRef = useRef(onViewChange);
  viewStartRef.current = viewStart;
  viewEndRef.current = viewEnd;
  durationRef.current = duration;
  onViewChangeRef.current = onViewChange;

  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  const lanes = useMemo(() => getStemLanes(formula), [formula]);

  const totalHeight = lanes.length * (LANE_HEIGHT + LANE_GAP) + LANE_GAP;

  // Combined highlight: either hovered from list or hovered on canvas
  const effectiveHoveredId = hoveredPatternId ?? hoveredBlockRef.current;

  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = widthRef.current;
    const h = totalHeight;
    const drawW = w - LABEL_WIDTH;

    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const viewDuration = viewEnd - viewStart;
    if (viewDuration <= 0 || drawW <= 0) return;

    const blocks: PatternBlock[] = [];

    for (let laneIdx = 0; laneIdx < lanes.length; laneIdx++) {
      const stemType = lanes[laneIdx];
      const colors = STEM_COLORS[stemType] ?? STEM_COLORS.other;
      const laneY = LANE_GAP + laneIdx * (LANE_HEIGHT + LANE_GAP);

      // Lane background
      ctx.fillStyle = "rgba(0, 0, 0, 0.3)";
      ctx.fillRect(LABEL_WIDTH, laneY, drawW, LANE_HEIGHT);

      // Stem label (rename "other" for clarity)
      const STEM_LABELS: Record<string, string> = {
        drums: "drums",
        bass: "bass",
        vocals: "vocals",
        other: "synth/fx",
      };
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillStyle = "rgba(255, 255, 255, 0.5)";
      ctx.textBaseline = "middle";
      ctx.fillText(STEM_LABELS[stemType] ?? stemType, 4, laneY + LANE_HEIGHT / 2);

      // Lane separator
      ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(LABEL_WIDTH, laneY + LANE_HEIGHT);
      ctx.lineTo(w, laneY + LANE_HEIGHT);
      ctx.stroke();

      // Activity spans + optional stem waveform
      const stemData = formula.stems.find((s) => s.stem_type === stemType);
      if (stemData) {
        // Stem waveform (drawn behind activity + pattern blocks)
        if (showStemWaveforms && stemData.waveform && stemData.waveform.low.length > 0) {
          const wf = stemData.waveform;
          const sampleRate = wf.sample_rate || 150;
          const centerY = laneY + LANE_HEIGHT / 2;
          const halfH = (LANE_HEIGHT - 2) / 2;
          const viewDuration = viewEnd - viewStart;

          for (let px = 0; px < drawW; px++) {
            const time0 = viewStart + (px / drawW) * viewDuration;
            const time1 = viewStart + ((px + 1) / drawW) * viewDuration;
            const s0 = Math.max(0, Math.floor(time0 * sampleRate));
            const s1 = Math.min(wf.low.length, Math.ceil(time1 * sampleRate));

            let maxLow = 0, maxMid = 0, maxHigh = 0;
            for (let i = s0; i < s1; i++) {
              if ((wf.low[i] ?? 0) > maxLow) maxLow = wf.low[i];
              if ((wf.mid[i] ?? 0) > maxMid) maxMid = wf.mid[i];
              if ((wf.high[i] ?? 0) > maxHigh) maxHigh = wf.high[i];
            }

            const amp = Math.max(maxLow, maxMid, maxHigh);
            if (amp < 0.01) continue;

            // Color from frequency ratio
            const r = Math.round((maxLow / amp) * 255);
            const g = Math.round((maxMid / amp) * 255);
            const b = Math.round((maxHigh / amp) * 255);
            const barH = Math.sqrt(amp) * halfH;

            ctx.fillStyle = `rgba(${r},${g},${b},0.6)`;
            ctx.fillRect(LABEL_WIDTH + px, centerY - barH, 1, barH * 2);
          }
        }

        for (const span of stemData.activity) {
          const x1 = Math.max(LABEL_WIDTH, LABEL_WIDTH + timeToX(span.start, viewStart, viewEnd, drawW));
          const x2 = Math.min(w, LABEL_WIDTH + timeToX(span.end, viewStart, viewEnd, drawW));
          if (x2 <= LABEL_WIDTH || x1 >= w) continue;
          // Only show activity spans when waveforms are hidden
          if (!showStemWaveforms) {
            ctx.fillStyle = colors.activity;
            ctx.fillRect(x1, laneY, x2 - x1, LANE_HEIGHT);
          }
        }
      }

      // Pattern instance blocks
      if (showPatternBlocks) {
      const stemPatterns = formula.patterns.filter((p) => p.stem === stemType);
      for (const pattern of stemPatterns) {
        for (const inst of pattern.instances) {
          const x1 = Math.max(LABEL_WIDTH, LABEL_WIDTH + timeToX(inst.start, viewStart, viewEnd, drawW));
          const x2 = Math.min(w, LABEL_WIDTH + timeToX(inst.end, viewStart, viewEnd, drawW));
          if (x2 <= LABEL_WIDTH || x1 >= w) continue;
          const blockW = x2 - x1;

          const isSelected = pattern.id === selectedPatternId;
          const isHovered = pattern.id === effectiveHoveredId && !isSelected;

          // Block fill
          ctx.fillStyle = isSelected
            ? colors.border
            : isHovered
              ? colors.blockHover
              : colors.block;
          ctx.fillRect(x1, laneY + BLOCK_PAD_Y, blockW, LANE_HEIGHT - BLOCK_PAD_Y * 2);

          // Block border
          ctx.strokeStyle = isSelected
            ? "rgba(255, 255, 255, 0.8)"
            : isHovered
              ? "rgba(255, 255, 255, 0.5)"
              : colors.border;
          ctx.lineWidth = isSelected ? 2 : isHovered ? 1.5 : 1;
          ctx.strokeRect(x1, laneY + BLOCK_PAD_Y, blockW, LANE_HEIGHT - BLOCK_PAD_Y * 2);

          // Pattern name label
          if (blockW > 30) {
            ctx.save();
            ctx.beginPath();
            ctx.rect(x1 + 2, laneY + BLOCK_PAD_Y, blockW - 4, LANE_HEIGHT - BLOCK_PAD_Y * 2);
            ctx.clip();
            ctx.font = "9px ui-monospace, monospace";
            ctx.fillStyle = colors.text;
            ctx.textBaseline = "middle";
            ctx.fillText(pattern.name, x1 + BLOCK_PAD_X, laneY + LANE_HEIGHT / 2);
            ctx.restore();
          }

          // Variation accent marker
          if (inst.variation !== "exact") {
            const accentColor = VARIATION_COLORS[inst.variation] ?? VARIATION_COLORS.minor;
            ctx.fillStyle = accentColor;
            ctx.fillRect(x1, laneY + BLOCK_PAD_Y, blockW, 3);
          }

          blocks.push({
            patternId: pattern.id,
            patternName: pattern.name,
            stem: pattern.stem,
            barStart: inst.bar_start,
            barEnd: inst.bar_end,
            variation: inst.variation,
            variationDesc: inst.variation_description,
            x: x1,
            y: laneY + BLOCK_PAD_Y,
            w: blockW,
            h: LANE_HEIGHT - BLOCK_PAD_Y * 2,
          });
        }
      }
      } // showPatternBlocks
    }

    blocksRef.current = blocks;

    // Event ticks on stem lanes (from per-stem events or external M7 fallback)
    if (visibleEventTypes && visibleEventTypes.size > 0) {
      // Check if any stem has events; if not, use external events
      const hasStemEvents = formula.stems.some((s) => s.events.length > 0);

      if (hasStemEvents) {
        // Per-stem events: draw on their respective lanes
        for (let laneIdx = 0; laneIdx < lanes.length; laneIdx++) {
          const stemType = lanes[laneIdx];
          const laneY = LANE_GAP + laneIdx * (LANE_HEIGHT + LANE_GAP);
          const stemData = formula.stems.find((s) => s.stem_type === stemType);
          if (!stemData) continue;

          for (const evt of stemData.events) {
            if (!visibleEventTypes.has(evt.type)) continue;
            const x = LABEL_WIDTH + timeToX(evt.timestamp, viewStart, viewEnd, drawW);
            if (x < LABEL_WIDTH || x > w) continue;

            const color = EVENT_TICK_COLORS[evt.type] ?? "rgba(255,255,255,0.5)";
            ctx.fillStyle = color;
            ctx.fillRect(x - 0.5, laneY + 1, 1.5, LANE_HEIGHT - 2);
          }
        }
      } else if (externalEvents && externalEvents.length > 0) {
        // External (M7) events: draw across all lanes (no stem attribution)
        for (const evt of externalEvents) {
          if (!visibleEventTypes.has(evt.type)) continue;
          const x = LABEL_WIDTH + timeToX(evt.timestamp, viewStart, viewEnd, drawW);
          if (x < LABEL_WIDTH || x > w) continue;

          const color = EVENT_TICK_COLORS[evt.type] ?? "rgba(255,255,255,0.5)";
          // Draw on first lane only (avoid visual clutter from duplicating across all)
          const laneY = LANE_GAP;
          ctx.fillStyle = color;
          ctx.globalAlpha = 0.7;
          ctx.fillRect(x - 0.5, laneY + 1, 1.5, totalHeight - LANE_GAP * 2);
          ctx.globalAlpha = 1.0;
        }
      }
    }

    // Pattern sub-events: when a pattern is selected, draw its template events across all instances
    if (selectedPatternId) {
      const selectedPattern = formula.patterns.find((p) => p.id === selectedPatternId);
      if (selectedPattern && selectedPattern.template.events.length > 0) {
        const stemType = selectedPattern.stem;
        const laneIdx = stemType ? lanes.indexOf(stemType) : -1;

        for (const inst of selectedPattern.instances) {
          for (const evt of selectedPattern.template.events) {
            // Compute absolute timestamp: instance start + event relative position
            const relativeTime = evt.timestamp;
            const absTime = inst.start + relativeTime;

            const x = LABEL_WIDTH + timeToX(absTime, viewStart, viewEnd, drawW);
            if (x < LABEL_WIDTH || x > w) continue;

            // Draw on the pattern's stem lane, or all lanes if no stem
            const drawLanes = laneIdx >= 0 ? [laneIdx] : lanes.map((_, i) => i);
            for (const li of drawLanes) {
              const ly = LANE_GAP + li * (LANE_HEIGHT + LANE_GAP);
              const color = EVENT_TICK_COLORS[evt.type] ?? "rgba(255,255,255,0.7)";

              // Diamond marker — larger, with white outline for visibility
              const cy = ly + LANE_HEIGHT / 2;
              const sz = 6;
              ctx.beginPath();
              ctx.moveTo(x, cy - sz);
              ctx.lineTo(x + sz * 0.6, cy);
              ctx.lineTo(x, cy + sz);
              ctx.lineTo(x - sz * 0.6, cy);
              ctx.closePath();
              // White outline for contrast against same-color blocks
              ctx.strokeStyle = "rgba(255,255,255,0.9)";
              ctx.lineWidth = 1.5;
              ctx.stroke();
              ctx.fillStyle = color;
              ctx.fill();
            }
          }
        }
      }
    }

    // Transition markers
    for (const t of formula.transitions) {
      const x = LABEL_WIDTH + timeToX(t.timestamp, viewStart, viewEnd, drawW);
      if (x < LABEL_WIDTH || x > w) continue;

      const color = TRANSITION_COLORS[t.type] ?? "rgba(255,255,255,0.3)";
      ctx.strokeStyle = color;
      ctx.lineWidth = t.type === "drop_impact" || t.type === "breakdown" ? 2 : 1;

      if (t.type === "fill" || t.type === "energy_shift") {
        ctx.setLineDash([4, 3]);
      }

      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, totalHeight);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.font = "8px sans-serif";
      ctx.fillStyle = color;
      ctx.textBaseline = "top";
      const label = t.type === "layer_enter" ? "+" + (t.layers_affected[0] ?? "")
        : t.type === "layer_exit" ? "-" + (t.layers_affected[0] ?? "")
        : t.type.replace("_", " ");
      ctx.fillText(label, x + 2, 2);
    }

    // --- Playback cursor (live tier) ---
    if (playbackCursorTime != null && playbackCursorTime >= viewStart && playbackCursorTime <= viewEnd) {
      const cursorX = LABEL_WIDTH + timeToX(playbackCursorTime, viewStart, viewEnd, drawW);

      // Progressive opacity: dim past, bright current/future
      // Draw a semi-transparent overlay on the "past" portion
      ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
      ctx.fillRect(LABEL_WIDTH, 0, cursorX - LABEL_WIDTH, totalHeight);

      // Cursor line — bright green
      ctx.strokeStyle = "#22c55e";
      ctx.lineWidth = 2;
      ctx.shadowColor = "#22c55e";
      ctx.shadowBlur = 6;
      ctx.beginPath();
      ctx.moveTo(cursorX, 0);
      ctx.lineTo(cursorX, totalHeight);
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Small time label at top
      ctx.font = "bold 9px monospace";
      ctx.fillStyle = "#22c55e";
      ctx.textBaseline = "top";
      const mins = Math.floor(playbackCursorTime / 60);
      const secs = Math.floor(playbackCursorTime % 60);
      ctx.fillText(`${mins}:${secs.toString().padStart(2, "0")}`, cursorX + 3, 2);
    }
  }, [formula, lanes, viewStart, viewEnd, totalHeight, selectedPatternId, effectiveHoveredId, visibleEventTypes, showStemWaveforms, showPatternBlocks, externalEvents, playbackCursorTime]);

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

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(render);
  }, [render]);

  // --- Hit-test helper ---
  const hitTest = useCallback((mx: number, my: number): PatternBlock | null => {
    for (const block of blocksRef.current) {
      if (mx >= block.x && mx <= block.x + block.w && my >= block.y && my <= block.y + block.h) {
        return block;
      }
    }
    return null;
  }, []);

  // --- Mouse interaction ---

  const handleMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      isDragging.current = true;
      dragStartX.current = e.clientX;
      dragStartViewStart.current = viewStart;
      dragStartViewEnd.current = viewEnd;
    },
    [viewStart, viewEnd],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (isDragging.current && onViewChange) {
        // Dragging — pan view
        const dx = e.clientX - dragStartX.current;
        const drawW = widthRef.current - LABEL_WIDTH;
        const pixelsPerSec = drawW / (dragStartViewEnd.current - dragStartViewStart.current);
        const dt = -dx / pixelsPerSec;
        let newStart = dragStartViewStart.current + dt;
        let newEnd = dragStartViewEnd.current + dt;
        if (newStart < 0) { newEnd -= newStart; newStart = 0; }
        if (newEnd > duration) { newStart -= newEnd - duration; newEnd = duration; }
        newStart = Math.max(0, newStart);
        onViewChange(newStart, newEnd);
        setTooltip(null);
        return;
      }

      // Hover — hit-test for tooltip + highlight
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const block = hitTest(mx, my);

      if (block) {
        const prevHovered = hoveredBlockRef.current;
        hoveredBlockRef.current = block.patternId;
        onPatternHover?.(block.patternId);

        // Show tooltip near mouse
        setTooltip({
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
          patternName: block.patternName,
          stem: block.stem ?? "",
          bars: `bar ${block.barStart}–${block.barEnd}`,
          variation: block.variation,
          variationDesc: block.variationDesc,
        });

        // Re-render if hover changed
        if (prevHovered !== block.patternId) {
          cancelAnimationFrame(rafRef.current);
          rafRef.current = requestAnimationFrame(render);
        }
      } else {
        if (hoveredBlockRef.current !== null) {
          hoveredBlockRef.current = null;
          onPatternHover?.(null);
          setTooltip(null);
          cancelAnimationFrame(rafRef.current);
          rafRef.current = requestAnimationFrame(render);
        }
      }
    },
    [duration, onViewChange, hitTest, onPatternHover, render],
  );

  const handleMouseUp = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const wasDrag = Math.abs(e.clientX - dragStartX.current) > 3;
      isDragging.current = false;
      if (wasDrag) return;

      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const block = hitTest(mx, my);

      if (block) {
        onPatternSelect?.(block.patternId);
      } else {
        onPatternSelect?.(null);
      }
    },
    [onPatternSelect, hitTest],
  );

  const handleMouseLeave = useCallback(() => {
    isDragging.current = false;
    if (hoveredBlockRef.current !== null) {
      hoveredBlockRef.current = null;
      onPatternHover?.(null);
      setTooltip(null);
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(render);
    }
  }, [onPatternHover, render]);

  // Native wheel handler (passive: false) to prevent page scroll while zooming
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !onViewChange) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const drawW = widthRef.current - LABEL_WIDTH;
      const mouseX = e.clientX - rect.left - LABEL_WIDTH;
      const mouseTime = xToTime(mouseX, viewStartRef.current, viewEndRef.current, drawW);
      const zoomFactor = e.deltaY > 0 ? 1.2 : 1 / 1.2;
      const viewDuration = viewEndRef.current - viewStartRef.current;
      let newDuration = viewDuration * zoomFactor;
      newDuration = Math.max(2, Math.min(durationRef.current, newDuration));
      const mouseRatio = (mouseTime - viewStartRef.current) / viewDuration;
      let newStart = mouseTime - mouseRatio * newDuration;
      let newEnd = newStart + newDuration;
      if (newStart < 0) { newEnd -= newStart; newStart = 0; }
      if (newEnd > durationRef.current) { newStart -= newEnd - durationRef.current; newEnd = durationRef.current; }
      newStart = Math.max(0, newStart);
      newEnd = Math.min(durationRef.current, newEnd);
      onViewChangeRef.current?.(newStart, newEnd);
    };
    canvas.addEventListener("wheel", handler, { passive: false });
    return () => canvas.removeEventListener("wheel", handler);
  }, []);

  const handleDoubleClick = useCallback(() => {
    onViewChange?.(0, duration);
  }, [duration, onViewChange]);

  return (
    <div ref={containerRef} className="w-full bg-gray-950 rounded border border-gray-800 relative">
      <canvas
        ref={canvasRef}
        style={{
          width: "100%",
          height: totalHeight,
          display: "block",
          cursor: isDragging.current ? "grabbing" : hoveredBlockRef.current ? "pointer" : "grab",
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onDoubleClick={handleDoubleClick}
      />
      {/* Tooltip overlay */}
      {tooltip && (
        <div
          className="absolute pointer-events-none z-10 px-2 py-1.5 bg-gray-900 border border-gray-700 rounded shadow-lg text-xs"
          style={{
            left: Math.min(tooltip.x + 12, (widthRef.current || 800) - 180),
            top: Math.max(0, tooltip.y - 50),
          }}
        >
          <div className="flex items-center gap-1.5">
            <span className="text-gray-200 font-mono font-semibold">{tooltip.patternName}</span>
            {tooltip.stem && (
              <span className="text-gray-500">{tooltip.stem}</span>
            )}
          </div>
          <div className="text-gray-400 mt-0.5">{tooltip.bars}</div>
          {tooltip.variation !== "exact" && (
            <div className="text-yellow-400 mt-0.5">
              {tooltip.variation}{tooltip.variationDesc ? `: ${tooltip.variationDesc}` : ""}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
