import type { Clip } from "./types";

export const fileName = (n: number) => `urdu_${String(n).padStart(6, "0")}`;

/** How many clips the dataset can hold, or null when there is no last file number. */
export const capacityOf = (s: { start_index: number; end_index: number | null }): number | null =>
  s.end_index === null ? null : s.end_index - s.start_index + 1;

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

/** 95 -> "1 min 35 s", 7500 -> "2 h 5 min". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.round(s / 60);
  if (m < 60) return s < 600 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${m} min`;
  const h = Math.floor(m / 60);
  return `${h} h ${m % 60} min`;
}

export function formatUsd(n: number): string {
  if (n <= 0) return "$0.00";
  if (n < 0.01) return "under $0.01";
  return `$${n.toFixed(2)}`;
}

export const isGood =(c: Clip) => c.keep && c.status === "processed";
export const needsLook = (c: Clip) => c.keep && (c.flags.length > 0 || !c.urdu.trim());
export const lacksRoman = (c: Clip) => isGood(c) && !c.roman.trim();
