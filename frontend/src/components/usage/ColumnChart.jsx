import { useState } from "react";
import { useElementWidth } from "../../hooks/useElementWidth";
import { formatCount, formatDay, niceMax } from "./format";

const HEIGHT = 180;
const PAD = { top: 12, right: 8, bottom: 26, left: 36 };
const MAX_BAR = 24; // thin marks: never fill the slot
const GAP = 2; // surface gap between adjacent bars

/** Column path: 4px rounded data-end (top), square at the baseline. */
function barPath(x, y, w, h) {
  const r = Math.min(4, w / 2, h);
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}

/**
 * One series of daily values (turns per day). Single series: no legend box, the
 * title names it. Every bar is focusable and has a tooltip; values lead.
 */
export default function ColumnChart({ data, label, valueKey, valueLabel, detail }) {
  const [ref, width] = useElementWidth();
  const [hover, setHover] = useState(null);
  const plotW = Math.max(width - PAD.left - PAD.right, 50);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const max = niceMax(Math.max(...data.map((d) => d[valueKey]), 0));
  const slot = plotW / data.length;
  const barW = Math.max(2, Math.min(MAX_BAR, slot - GAP));
  const ticks = [0, max / 2, max];
  const labelEvery = data.length <= 7 ? 1 : data.length <= 31 ? 5 : 15;
  const total = data.reduce((sum, d) => sum + d[valueKey], 0);
  const busiest = data.reduce((best, d) => (d[valueKey] > (best?.[valueKey] ?? -1) ? d : best), null);
  const summary = `${label}: ${formatCount(total)} in total${busiest && busiest[valueKey] ? `, busiest ${formatDay(busiest.date)} with ${formatCount(busiest[valueKey])}` : ""}.`;

  return (
    <div className="column-chart" ref={ref}>
      <svg aria-label={summary} height={HEIGHT} role="img" width={width}>
        {ticks.map((t) => {
          const y = PAD.top + plotH - (t / max) * plotH;
          return (
            <g key={t}>
              <line className="chart-grid" x1={PAD.left} x2={PAD.left + plotW} y1={y} y2={y} />
              <text className="chart-axis" textAnchor="end" x={PAD.left - 6} y={y + 4}>{formatCount(t)}</text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const value = d[valueKey];
          const h = (value / max) * plotH;
          const x = PAD.left + i * slot + (slot - barW) / 2;
          const text = `${formatDay(d.date, true)}: ${formatCount(value)} ${valueLabel}${detail ? `, ${detail(d)}` : ""}`;
          return (
            <g
              aria-label={text}
              className="chart-bar"
              key={d.date}
              onBlur={() => setHover(null)}
              onFocus={() => setHover({ d, x: x + barW / 2 })}
              onPointerEnter={() => setHover({ d, x: x + barW / 2 })}
              onPointerLeave={() => setHover(null)}
              role="img"
              tabIndex={0}
            >
              {/* hit target: the whole slot, bigger than the mark */}
              <rect fill="transparent" height={plotH} width={slot} x={PAD.left + i * slot} y={PAD.top} />
              {value > 0 ? <path className="chart-mark" d={barPath(x, PAD.top + plotH - h, barW, h)} /> : null}
              {i % labelEvery === 0 || i === data.length - 1 ? (
                <text className="chart-axis" textAnchor="middle" x={x + barW / 2} y={HEIGHT - 8}>{formatDay(d.date)}</text>
              ) : null}
            </g>
          );
        })}
        <line className="chart-baseline" x1={PAD.left} x2={PAD.left + plotW} y1={PAD.top + plotH} y2={PAD.top + plotH} />
      </svg>
      {hover ? (
        <div className="chart-tooltip" style={{ left: Math.min(Math.max(hover.x, 70), width - 70) }}>
          <strong>{formatCount(hover.d[valueKey])} {valueLabel}</strong>
          <span>{formatDay(hover.d.date, true)}</span>
          {detail ? <span>{detail(hover.d)}</span> : null}
        </div>
      ) : null}
      <details className="chart-table">
        <summary>Show as table</summary>
        <table>
          <thead><tr><th scope="col">Day</th><th scope="col">{valueLabel}</th>{detail ? <th scope="col">Details</th> : null}</tr></thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.date}><td>{formatDay(d.date, true)}</td><td>{formatCount(d[valueKey])}</td>{detail ? <td>{detail(d)}</td> : null}</tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
