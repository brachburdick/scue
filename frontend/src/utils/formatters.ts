/** Display formatting helpers. */

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function formatBpm(bpm: number): string {
  return bpm > 0 ? bpm.toFixed(1) : "—";
}

export function formatDate(unixTs: number): string {
  if (!unixTs) return "—";
  return new Date(unixTs * 1000).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function truncateFingerprint(fp: string, len = 8): string {
  return fp.slice(0, len);
}
