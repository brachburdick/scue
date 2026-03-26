/**
 * Shared beatgrid line renderer for all waveform canvas components.
 *
 * Draws three hierarchy levels with zoom-adaptive visibility:
 * - 4-measure groups (every 4th downbeat) — thickest, brightest
 * - Measures (every downbeat) — medium
 * - Quarter-notes (every beat) — thinnest, subtlest
 *
 * Lines are hidden when they would be too dense to be useful (< MIN_GAP_PX apart).
 */

const MIN_GAP_PX = 20;

interface GridLevel {
  times: number[];
  lineWidth: number;
  color: string;
}

/**
 * Draw beatgrid lines on a canvas context.
 * Call after section overlays, before waveform bars.
 */
export function drawBeatgridLines(
  ctx: CanvasRenderingContext2D,
  beats: number[],
  downbeats: number[],
  viewStart: number,
  viewEnd: number,
  width: number,
  height: number,
  leftPadding: number = 0,
): void {
  if (beats.length < 2 && downbeats.length < 2) return;

  const viewDuration = viewEnd - viewStart;
  if (viewDuration <= 0 || width <= 0) return;

  const pixelsPerSec = width / viewDuration;

  // Build 4-measure group timestamps (every 4th downbeat)
  const fourMeasures: number[] = [];
  for (let i = 0; i < downbeats.length; i += 4) {
    fourMeasures.push(downbeats[i]);
  }

  // Define levels from coarsest to finest
  const levels: GridLevel[] = [
    { times: fourMeasures, lineWidth: 1.5, color: "rgba(255,255,255,0.45)" },
    { times: downbeats, lineWidth: 1, color: "rgba(255,255,255,0.25)" },
    { times: beats, lineWidth: 0.5, color: "rgba(255,255,255,0.12)" },
  ];

  // Track which timestamps have already been drawn at a coarser level
  // so we don't double-draw (e.g., a downbeat that's also a 4-measure mark)
  const drawn = new Set<number>();

  for (const level of levels) {
    if (level.times.length < 2) continue;

    // Estimate average gap for this level within the viewport
    const inView = level.times.filter((t) => t >= viewStart && t <= viewEnd);
    if (inView.length < 2) {
      // Fewer than 2 in view — still draw them if they exist
      if (inView.length === 0) continue;
    } else {
      const avgGap = ((inView[inView.length - 1] - inView[0]) / (inView.length - 1)) * pixelsPerSec;
      if (avgGap < MIN_GAP_PX) continue;
    }

    ctx.strokeStyle = level.color;
    ctx.lineWidth = level.lineWidth;
    ctx.beginPath();

    for (const t of level.times) {
      if (t < viewStart || t > viewEnd) continue;
      if (drawn.has(t)) continue;
      drawn.add(t);

      const x = leftPadding + ((t - viewStart) / viewDuration) * width;
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
    }

    ctx.stroke();
  }
}
