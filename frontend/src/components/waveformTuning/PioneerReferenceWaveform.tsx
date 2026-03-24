/**
 * PioneerReferenceWaveform — renders raw Pioneer ANLZ PWV5 data for comparison.
 *
 * Read-only. Scroll/zoom synced with the main waveform via viewStart/viewEnd props.
 */

import { useRef, useEffect, useCallback } from "react";

interface Pwv5Entry {
  r: number;  // 0-7
  g: number;  // 0-7
  b: number;  // 0-7
  height: number;  // 0-31
}

interface PioneerWaveformData {
  pwv5?: {
    entries_per_second: number;
    total_entries: number;
    data: Pwv5Entry[];
  };
  available: string[];
}

interface Props {
  data: PioneerWaveformData;
  viewStart: number;
  viewEnd: number;
  height?: number;
}

export function PioneerReferenceWaveform({ data, viewStart, viewEnd, height = 80 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const widthRef = useRef(0);
  const rafRef = useRef(0);

  const pwv5 = data.pwv5;

  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !pwv5) return;
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

    const eps = pwv5.entries_per_second;
    const entries = pwv5.data;
    const centerY = h / 2;
    const startIdx = Math.max(0, Math.floor(viewStart * eps));
    const endIdx = Math.min(entries.length, Math.ceil(viewEnd * eps));

    for (let px = 0; px < w; px++) {
      const t0 = viewStart + (px / w) * viewDuration;
      const t1 = viewStart + ((px + 1) / w) * viewDuration;
      const s0 = Math.max(startIdx, Math.floor(t0 * eps));
      const s1 = Math.min(endIdx, Math.ceil(t1 * eps));

      let maxR = 0, maxG = 0, maxB = 0, maxH = 0;
      for (let i = s0; i < s1; i++) {
        const e = entries[i];
        if (!e) continue;
        if (e.r > maxR) maxR = e.r;
        if (e.g > maxG) maxG = e.g;
        if (e.b > maxB) maxB = e.b;
        if (e.height > maxH) maxH = e.height;
      }

      if (maxH === 0) continue;

      // PWV5: r,g,b are 3-bit (0-7), height is 5-bit (0-31)
      const r = Math.round((maxR / 7) * 255);
      const g = Math.round((maxG / 7) * 255);
      const b = Math.round((maxB / 7) * 255);
      const barH = (maxH / 31) * centerY;

      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(px, centerY - barH, 1, barH * 2);
    }
  }, [pwv5, viewStart, viewEnd, height]);

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

  if (!pwv5) {
    return (
      <div className="text-xs text-slate-500 bg-slate-900 border border-slate-800 rounded p-3">
        No Pioneer ANLZ data — analyze from USB to enable comparison
      </div>
    );
  }

  return (
    <div>
      <div className="text-xs text-slate-400 mb-1">Pioneer Reference (PWV5)</div>
      <div ref={containerRef} className="w-full bg-gray-950 rounded border border-gray-800">
        <canvas
          ref={canvasRef}
          style={{ width: "100%", height, display: "block" }}
        />
      </div>
    </div>
  );
}
