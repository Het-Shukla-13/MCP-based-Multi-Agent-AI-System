const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
const full = new Intl.NumberFormat();

/** Full under 10,000, compact above (12K, 1.4M) - one style per context. */
export const formatCount = (n) => (n == null ? "-" : Math.abs(n) >= 10000 ? compact.format(n) : full.format(n));

export function formatMs(ms) {
  if (ms == null) return "-";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
}

export const formatPercent = (ratio) => (ratio == null ? "-" : `${(ratio * 100).toFixed(ratio > 0 && ratio < 0.1 ? 1 : 0)}%`);

/** "18 Nov" from "2026-11-18" (treated as a calendar date, not a UTC instant). */
export function formatDay(isoDate, withWeekday = false) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    ...(withWeekday ? { weekday: "short" } : {}),
  });
}

/** A clean axis maximum: 1, 2, 5 x 10^n at or above `value`. */
export function niceMax(value) {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 5, 10].find((s) => s * power >= value);
  return step * power;
}
