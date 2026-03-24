/**
 * AnnotationTimeline — interactive waveform canvas for ground truth labeling.
 *
 * Renders: waveform (RGB), section bands, ground truth annotations (solid),
 * optional detector events (faded), audio cursor line.
 *
 * Interaction: click to place point events, drag to create region events,
 * click existing annotation to select, drag-to-pan, wheel-to-zoom.
 */

import { useRef, useEffect, useCallback } from "react";
import type { EventType } from "../../types/events";
import type { GroundTruthEvent, SnapResolution, PlacementMode } from "../../types/groundTruth";
import { EVENT_COLORS, SECTION_COLORS } from "../../types/events";
import type { MusicalEvent } from "../../types/events";
import { drawBeatgridLines } from "../shared/drawBeatgridLines";

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

export interface AnnotationTimelineProps {
  sections: Section[];
  waveform: Waveform | null;
  duration: number;

  /** Ground truth annotations being edited */
  annotations: GroundTruthEvent[];
  selectedIndex: number | null;

  /** Optional detector output overlay */
  detectorEvents?: MusicalEvent[];
  showDetectorOverlay: boolean;

  /** Current audio playback position (seconds), null when stopped */
  cursorPosition: number | null;

  /** Active event type for placement */
  activeType: EventType;
  placementMode: PlacementMode;
  snapResolution: SnapResolution;

  /** Beatgrid for snap */
  beats: number[];
  downbeats: number[];

  /** Event type visibility filter */
  visibleTypes: Set<EventType>;

  /** Viewport */
  viewStart: number;
  viewEnd: number;
  onViewChange: (start: number, end: number) => void;

  /** Callbacks */
  onPlaceEvent: (event: GroundTruthEvent) => void;
  onSelectEvent: (index: number | null) => void;
  onTimeClick: (seconds: number) => void;
}

// --- Snap helper ---

function snapToGrid(
  time: number,
  beats: number[],
  resolution: SnapResolution,
): number {
  if (resolution === "off" || beats.length < 2) return time;

  // Find surrounding beats
  let beatIdx = 0;
  for (let i = 0; i < beats.length - 1; i++) {
    if (beats[i + 1] > time) {
      beatIdx = i;
      break;
    }
    beatIdx = i;
  }

  const beatStart = beats[beatIdx];
  const beatEnd = beats[beatIdx + 1] ?? beatStart + 0.5;
  const beatDur = beatEnd - beatStart;

  const divisions = resolution === "16th" ? 4 : resolution === "32nd" ? 8 : 16;
  const slotDur = beatDur / divisions;
  const offset = time - beatStart;
  const slot = Math.round(offset / slotDur);
  return beatStart + slot * slotDur;
}

// --- Component ---

export function AnnotationTimeline({
  sections,
  waveform,
  duration,
  annotations,
  selectedIndex,
  detectorEvents,
  showDetectorOverlay,
  cursorPosition,
  activeType,
  placementMode,
  snapResolution,
  beats,
  downbeats,
  visibleTypes,
  viewStart,
  viewEnd,
  onViewChange,
  onPlaceEvent,
  onSelectEvent,
  onTimeClick,
}: AnnotationTimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const widthRef = useRef(0);
  const rafRef = useRef(0);

  // Drag state
  const isDragging = useRef(false);
  const isPanning = useRef(false);
  const dragStartX = useRef(0);
  const dragStartTime = useRef(0);
  const dragStartViewStart = useRef(0);
  const dragStartViewEnd = useRef(0);
  const regionStartTime = useRef<number | null>(null);

  // --- Helpers ---
  const timeToX = useCallback(
    (t: number) => ((t - viewStart) / (viewEnd - viewStart)) * widthRef.current,
    [viewStart, viewEnd],
  );

  const xToTime = useCallback(
    (x: number) => viewStart + (x / widthRef.current) * (viewEnd - viewStart),
    [viewStart, viewEnd],
  );

  // --- Find annotation near click ---
  const findAnnotationAt = useCallback(
    (time: number): number | null => {
      const tolerance = (viewEnd - viewStart) / widthRef.current * 6; // ~6px
      for (let i = 0; i < annotations.length; i++) {
        const a = annotations[i];
        if (a.duration) {
          if (time >= a.timestamp - tolerance && time <= a.timestamp + a.duration + tolerance) {
            return i;
          }
        } else {
          if (Math.abs(time - a.timestamp) <= tolerance) return i;
        }
      }
      return null;
    },
    [annotations, viewStart, viewEnd],
  );

  // --- Draw ---
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = widthRef.current;
    const h = 192;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.scale(dpr, dpr);

    const viewDuration = viewEnd - viewStart;
    if (viewDuration <= 0 || w <= 0) return;

    const tToX = (t: number) => ((t - viewStart) / viewDuration) * w;

    // Clear
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, 0, w, h);

    // Section bands
    for (const sec of sections) {
      if (sec.end < viewStart || sec.start > viewEnd) continue;
      const x1 = Math.max(0, tToX(sec.start));
      const x2 = Math.min(w, tToX(sec.end));
      ctx.fillStyle = SECTION_COLORS[sec.label] ?? "rgba(100,100,100,0.1)";
      ctx.fillRect(x1, 0, x2 - x1, h);
      if (x2 - x1 > 30) {
        ctx.fillStyle = "rgba(255,255,255,0.3)";
        ctx.font = "10px sans-serif";
        ctx.fillText(sec.label, x1 + 4, 12);
      }
    }

    // Waveform
    if (waveform && waveform.low.length > 0) {
      const sps = waveform.sample_rate;
      const centerY = h * 0.5;
      const s0 = Math.max(0, Math.floor(viewStart * sps));
      const s1 = Math.min(waveform.low.length, Math.ceil(viewEnd * sps));
      const count = s1 - s0;

      if (count > 0) {
        const spp = count / w;
        if (spp <= 1) {
          for (let i = s0; i < s1; i++) {
            const lo = waveform.low[i] ?? 0;
            const mid = waveform.mid[i] ?? 0;
            const hi = waveform.high[i] ?? 0;
            const amp = Math.max(lo, mid, hi);
            if (amp < 0.001) continue;
            const r = Math.min(255, Math.round((lo / amp) * 255));
            const g = Math.min(255, Math.round((mid / amp) * 255));
            const b = Math.min(255, Math.round((hi / amp) * 255));
            const barH = amp * centerY;
            const x = ((i - s0) / count) * w;
            ctx.fillStyle = `rgb(${r},${g},${b})`;
            ctx.fillRect(x, centerY - barH, Math.max(1, w / count), barH * 2);
          }
        } else {
          for (let px = 0; px < w; px++) {
            const t0 = viewStart + (px / w) * viewDuration;
            const t1 = viewStart + ((px + 1) / w) * viewDuration;
            const i0 = Math.max(s0, Math.floor(t0 * sps));
            const i1 = Math.min(s1, Math.ceil(t1 * sps));
            let maxL = 0, maxM = 0, maxH = 0;
            for (let i = i0; i < i1; i++) {
              if ((waveform.low[i] ?? 0) > maxL) maxL = waveform.low[i];
              if ((waveform.mid[i] ?? 0) > maxM) maxM = waveform.mid[i];
              if ((waveform.high[i] ?? 0) > maxH) maxH = waveform.high[i];
            }
            const amp = Math.max(maxL, maxM, maxH);
            if (amp < 0.001) continue;
            const r = Math.min(255, Math.round((maxL / amp) * 255));
            const g = Math.min(255, Math.round((maxM / amp) * 255));
            const b = Math.min(255, Math.round((maxH / amp) * 255));
            ctx.fillStyle = `rgb(${r},${g},${b})`;
            ctx.fillRect(px, centerY - amp * centerY, 1, amp * centerY * 2);
          }
        }
      }
    }

    // --- Beatgrid lines (on top of waveform, below annotations) ---
    if (beats.length > 0 || downbeats.length > 0) {
      drawBeatgridLines(ctx, beats, downbeats, viewStart, viewEnd, w, h);
    }

    // --- Detector overlay (faded) ---
    if (showDetectorOverlay && detectorEvents) {
      ctx.globalAlpha = 0.25;
      for (const event of detectorEvents) {
        if (!visibleTypes.has(event.type)) continue;
        if (event.timestamp > viewEnd) continue;
        const eEnd = event.timestamp + (event.duration ?? 0);
        if (eEnd < viewStart) continue;
        const color = EVENT_COLORS[event.type] ?? "#ffffff";
        const x = tToX(event.timestamp);

        if (event.type === "riser" || event.type === "faller") {
          const x2 = tToX(event.timestamp + (event.duration ?? 2));
          ctx.fillStyle = color + "40";
          ctx.fillRect(x, 0, x2 - x, h);
          ctx.setLineDash([4, 4]);
          ctx.strokeStyle = color;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x, event.type === "riser" ? h * 0.8 : h * 0.2);
          ctx.lineTo(x2, event.type === "riser" ? h * 0.2 : h * 0.8);
          ctx.stroke();
          ctx.setLineDash([]);
        } else if (event.type === "stab") {
          ctx.fillStyle = color;
          ctx.fillRect(x, h * 0.05, Math.max(3, tToX(event.timestamp + (event.duration ?? 0.1)) - x), h * 0.1);
        } else {
          ctx.strokeStyle = color;
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 3]);
          ctx.beginPath();
          ctx.moveTo(x, h * 0.3);
          ctx.lineTo(x, h * 0.9);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }
      ctx.globalAlpha = 1;
    }

    // --- Ground truth annotations (solid, bright) ---
    for (let i = 0; i < annotations.length; i++) {
      const a = annotations[i];
      if (!visibleTypes.has(a.type)) continue;
      if (a.timestamp > viewEnd) continue;
      const aEnd = a.timestamp + (a.duration ?? 0);
      if (aEnd < viewStart) continue;

      const color = EVENT_COLORS[a.type] ?? "#ffffff";
      const x = tToX(a.timestamp);
      const isSelected = selectedIndex === i;

      if (a.duration) {
        // Region event
        const x2 = tToX(a.timestamp + a.duration);
        ctx.fillStyle = color + (isSelected ? "60" : "40");
        ctx.fillRect(x, 0, x2 - x, h);
        ctx.strokeStyle = color;
        ctx.lineWidth = isSelected ? 3 : 2;
        ctx.strokeRect(x, 0, x2 - x, h);
      } else {
        // Point event — thick vertical line
        ctx.strokeStyle = color;
        ctx.lineWidth = isSelected ? 3 : 2;
        ctx.beginPath();
        ctx.moveTo(x, h * 0.1);
        ctx.lineTo(x, h * 0.9);
        ctx.stroke();

        // Selection glow
        if (isSelected) {
          ctx.strokeStyle = color + "60";
          ctx.lineWidth = 8;
          ctx.beginPath();
          ctx.moveTo(x, h * 0.1);
          ctx.lineTo(x, h * 0.9);
          ctx.stroke();
        }
      }

      // Type label at top
      ctx.fillStyle = isSelected ? "#ffffff" : "rgba(255,255,255,0.7)";
      ctx.font = isSelected ? "bold 10px sans-serif" : "10px sans-serif";
      ctx.fillText(a.type, x + 3, h - 4);
    }

    // --- In-progress region drag preview ---
    if (regionStartTime.current !== null) {
      const color = EVENT_COLORS[activeType] ?? "#ffffff";
      const x1 = tToX(regionStartTime.current);
      ctx.fillStyle = color + "30";
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      // We'll draw from start to current cursor — but since we don't have
      // the current cursor in render, we rely on the next mouseMove re-render
      ctx.setLineDash([]);
    }

    // --- Audio cursor ---
    if (cursorPosition != null && cursorPosition >= viewStart && cursorPosition <= viewEnd) {
      const cx = tToX(cursorPosition);
      ctx.strokeStyle = "rgba(255,255,255,0.3)";
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, h);
      ctx.stroke();
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, h);
      ctx.stroke();
    }
  }, [
    sections, waveform, duration, annotations, selectedIndex,
    detectorEvents, showDetectorOverlay, cursorPosition,
    activeType, beats, downbeats, visibleTypes, viewStart, viewEnd,
  ]);

  // Resize observer
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

  // Re-render on data change
  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(render);
  }, [render]);

  // --- Mouse handlers ---

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = e.clientX - rect.left;
      const time = xToTime(x);

      // Right-click or middle-click: start pan
      if (e.button === 1 || e.altKey) {
        isPanning.current = true;
        dragStartX.current = e.clientX;
        dragStartViewStart.current = viewStart;
        dragStartViewEnd.current = viewEnd;
        return;
      }

      dragStartX.current = e.clientX;
      dragStartTime.current = time;
      isDragging.current = true;

      // Check if clicking an existing annotation
      const hitIdx = findAnnotationAt(time);
      if (hitIdx !== null) {
        onSelectEvent(hitIdx);
        isDragging.current = false;
        return;
      }

      // Start region drag for tonal events
      if (placementMode === "region") {
        const snapped = snapToGrid(time, beats, snapResolution);
        regionStartTime.current = snapped;
      }
    },
    [xToTime, viewStart, viewEnd, findAnnotationAt, onSelectEvent, placementMode, beats, snapResolution],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (isPanning.current) {
        const dx = e.clientX - dragStartX.current;
        const pps = widthRef.current / (dragStartViewEnd.current - dragStartViewStart.current);
        const dt = -dx / pps;
        let ns = dragStartViewStart.current + dt;
        let ne = dragStartViewEnd.current + dt;
        if (ns < 0) { ne -= ns; ns = 0; }
        if (ne > duration) { ns -= ne - duration; ne = duration; }
        onViewChange(Math.max(0, ns), Math.min(duration, ne));
      }
    },
    [duration, onViewChange],
  );

  const handleMouseUp = useCallback(
    (e: React.MouseEvent) => {
      if (isPanning.current) {
        isPanning.current = false;
        return;
      }

      const wasDrag = Math.abs(e.clientX - dragStartX.current) > 5;

      if (isDragging.current) {
        isDragging.current = false;

        if (placementMode === "region" && regionStartTime.current !== null && wasDrag) {
          const rect = canvasRef.current?.getBoundingClientRect();
          if (rect) {
            const x = e.clientX - rect.left;
            const endTime = snapToGrid(xToTime(x), beats, snapResolution);
            const start = Math.min(regionStartTime.current, endTime);
            const end = Math.max(regionStartTime.current, endTime);
            if (end - start > 0.05) {
              onPlaceEvent({ type: activeType, timestamp: start, duration: end - start });
            }
          }
          regionStartTime.current = null;
          return;
        }

        regionStartTime.current = null;

        if (!wasDrag) {
          // Click — place point event or seek audio
          const rect = canvasRef.current?.getBoundingClientRect();
          if (rect) {
            const x = e.clientX - rect.left;
            const time = xToTime(x);

            if (placementMode === "point") {
              const snapped = snapToGrid(time, beats, snapResolution);
              onPlaceEvent({ type: activeType, timestamp: snapped });
              onSelectEvent(null);
            } else {
              // In region mode, a click (not drag) deselects and seeks
              onSelectEvent(null);
              onTimeClick(time);
            }
          }
        }
      }
    },
    [placementMode, activeType, beats, snapResolution, xToTime, onPlaceEvent, onSelectEvent, onTimeClick],
  );

  const handleMouseLeave = useCallback(() => {
    isPanning.current = false;
    isDragging.current = false;
    regionStartTime.current = null;
  }, []);

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;

      const mouseX = e.clientX - rect.left;
      const mouseTime = xToTime(mouseX);
      const zoomFactor = e.deltaY > 0 ? 1.2 : 1 / 1.2;
      const viewDuration = viewEnd - viewStart;
      let newDuration = Math.max(2, Math.min(duration, viewDuration * zoomFactor));

      const mouseRatio = (mouseTime - viewStart) / viewDuration;
      let ns = mouseTime - mouseRatio * newDuration;
      let ne = ns + newDuration;
      if (ns < 0) { ne -= ns; ns = 0; }
      if (ne > duration) { ns -= ne - duration; ne = duration; }

      onViewChange(Math.max(0, ns), Math.min(duration, ne));
    },
    [viewStart, viewEnd, duration, xToTime, onViewChange],
  );

  const handleDoubleClick = useCallback(() => {
    onViewChange(0, duration);
  }, [duration, onViewChange]);

  return (
    <div ref={containerRef} className="w-full bg-gray-950 rounded-lg border border-slate-700">
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height: 192, display: "block", cursor: "crosshair" }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onWheel={handleWheel}
        onDoubleClick={handleDoubleClick}
      />
    </div>
  );
}
