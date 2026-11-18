import { formatCount } from "./format";

/**
 * Ranked horizontal bars ("meter list"): name, bar, figure per row, largest first,
 * one hue. Values are printed, so nothing depends on hover or colour.
 */
export default function RankedBars({ rows, label, unit = "", empty = "No data yet." }) {
  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const max = Math.max(...sorted.map((r) => r.value), 1);
  if (!sorted.length) return <p className="usage-empty">{empty}</p>;
  return (
    <ul aria-label={label} className="ranked-bars">
      {sorted.map((row) => (
        <li className="ranked-bars__row" key={row.name}>
          <span className="ranked-bars__name" title={row.name}>{row.name}</span>
          <span aria-hidden="true" className="ranked-bars__track">
            <span className="ranked-bars__bar" style={{ width: `${Math.max((row.value / max) * 100, 1)}%` }} />
          </span>
          <span className="ranked-bars__value">{formatCount(row.value)}{unit}</span>
        </li>
      ))}
    </ul>
  );
}
