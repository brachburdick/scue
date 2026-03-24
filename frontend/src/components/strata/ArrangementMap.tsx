import { useRef, useEffect, useCallback, useMemo, useState } from "react";
import type {
  ArrangementFormula,
  StemType,
  Pattern,
  PatternInstance,
} from "../../types/strata";

// --- Constants ---

const LANE_HEIGHT = 48;
const LANE_GAP = 2;
const BLOCK_PAD_X = 4;
const BLOCK_PAD_Y = 4;
const LABEL_WIDTH = 56;

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

      // Stem label
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillStyle = "rgba(255, 255, 255, 0.5)";
      ctx.textBaseline = "middle";
      ctx.fillText(stemType, 4, laneY + LANE_HEIGHT / 2);

      // Lane separator
      ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(LABEL_WIDTH, laneY + LANE_HEIGHT);
      ctx.lineTo(w, laneY + LANE_HEIGHT);
      ctx.stroke();

      // Activity spans
      const stemData = formula.stems.find((s) => s.stem_type === stemType);
      if (stemData) {
        for (const span of stemData.activity) {
          const x1 = Math.max(LABEL_WIDTH, LABEL_WIDTH + timeToX(span.start, viewStart, viewEnd, drawW));
          const x2 = Math.min(w, LABEL_WIDTH + timeToX(span.end, viewStart, viewEnd, drawW));
          if (x2 <= LABEL_WIDTH || x1 >= w) continue;
          ctx.fillStyle = colors.activity;
          ctx.fillRect(x1, laneY, x2 - x1, LANE_HEIGHT);
        }
      }

      // Pattern instance blocks
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
    }

    blocksRef.current = blocks;

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
  }, [formula, lanes, viewStart, viewEnd, totalHeight, selectedPatternId, effectiveHoveredId]);

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

  const handleWheel = useCallback(
    (e: React.WheelEvent<HTMLCanvasElement>) => {
      if (!onViewChange) return;
      e.preventDefault();
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const drawW = widthRef.current - LABEL_WIDTH;
      const mouseX = e.clientX - rect.left - LABEL_WIDTH;
      const mouseTime = xToTime(mouseX, viewStart, viewEnd, drawW);
      const zoomFactor = e.deltaY > 0 ? 1.2 : 1 / 1.2;
      const viewDuration = viewEnd - viewStart;
      let newDuration = viewDuration * zoomFactor;
      newDuration = Math.max(2, Math.min(duration, newDuration));
      const mouseRatio = (mouseTime - viewStart) / viewDuration;
      let newStart = mouseTime - mouseRatio * newDuration;
      let newEnd = newStart + newDuration;
      if (newStart < 0) { newEnd -= newStart; newStart = 0; }
      if (newEnd > duration) { newStart -= newEnd - duration; newEnd = duration; }
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
        onWheel={handleWheel}
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
