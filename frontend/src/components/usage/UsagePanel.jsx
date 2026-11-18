import { useEffect, useRef, useState } from "react";
import { CircleAlert, CircleCheck, X } from "lucide-react";
import { errorMessage, fetchRecentTurns, fetchUsageSummary } from "../../lib/api";
import { agentLabel } from "../../lib/agents";
import ColumnChart from "./ColumnChart";
import RankedBars from "./RankedBars";
import { formatCount, formatMs, formatPercent } from "./format";

const RANGES = [7, 30, 90];

const PURPOSES = {
  router: "Choosing an agent",
  stm_summarization: "Conversation summary",
  memory_extraction: "Learning memories",
  memory_comparison: "Comparing memories",
  profile_extraction: "Updating your profile",
  conversation_metadata_extraction: "Topics & metadata",
  metadata_annotation: "Classifying memories",
};

function purposeLabel(purpose, agents) {
  if (purpose?.startsWith("agent:")) return agentLabel(agents, purpose.slice(6));
  return PURPOSES[purpose] || (purpose || "other").replaceAll("_", " ");
}

function Tile({ label, value, sub }) {
  return (
    <div className="stat-tile">
      <p className="stat-tile__label">{label}</p>
      <p className="stat-tile__value">{value}</p>
      {sub ? <p className="stat-tile__sub">{sub}</p> : null}
    </div>
  );
}

/** Status is never colour alone: icon + label + colour. */
function Status({ ok, okText = "OK", badText }) {
  const Icon = ok ? CircleCheck : CircleAlert;
  return (
    <span className={`status-label status-label--${ok ? "ok" : "bad"}`}>
      <Icon aria-hidden="true" size={14} />
      {ok ? okText : badText}
    </span>
  );
}

/**
 * The signed-in user's own usage: how fast replies are, what they cost in tokens,
 * which agents and tools do the work. One range filter scopes everything below it.
 */
export default function UsagePanel({ agents, onClose }) {
  const [days, setDays] = useState(7);
  const [state, setState] = useState({ summary: null, turns: [], error: "", loadingDays: 7 });
  const returnFocus = useRef(document.activeElement);
  const closeRef = useRef(null);

  useEffect(() => {
    closeRef.current?.focus();
    const returnTo = returnFocus.current;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      returnTo?.focus?.();
    };
  }, [onClose]);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchUsageSummary(days, { signal: controller.signal }), fetchRecentTurns(15, { signal: controller.signal })])
      .then(([summary, turns]) => setState({ summary, turns, error: "", loadingDays: null }))
      .catch((error) => {
        if (!controller.signal.aborted) {
          setState((s) => ({ ...s, error: errorMessage(error, "Could not load usage."), loadingDays: null }));
        }
      });
    return () => controller.abort();
  }, [days]);

  const { summary, turns, error } = state;
  // Refetch keeps the frame: the previous numbers stay (dimmed) while a new range loads.
  const refreshing = summary && summary.days !== days && !error;
  const tokensTotal = summary ? summary.daily.reduce((n, d) => n + d.tokens, 0) : 0;
  const labelFor = (name) => (name === "unknown" ? "Not recorded" : agentLabel(agents, name));

  return (
    <div className="drawer-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <section aria-label="Usage" aria-modal="true" className="usage" role="dialog">
        <header className="usage__header">
          <div>
            <h3>Usage</h3>
            <p className="usage__intro">How fast replies are, what they use, and which agents and tools do the work. Only your own activity.</p>
          </div>
          <button aria-label="Close" className="icon-button" onClick={onClose} ref={closeRef} type="button">
            <X aria-hidden="true" size={18} />
          </button>
        </header>

        <div aria-label="Time range" className="range-filter" role="radiogroup">
          {RANGES.map((range) => (
            <button
              aria-checked={days === range}
              className={`range-filter__option${days === range ? " range-filter__option--active" : ""}`}
              key={range}
              onClick={() => {
                setDays(range);
                setState((s) => ({ ...s, loadingDays: range }));
              }}
              role="radio"
              type="button"
            >
              Last {range} days
            </button>
          ))}
        </div>

        {error ? <p className="usage-error" role="alert">{error}</p> : null}
        {!summary && !error ? <p className="usage-empty" role="status">Loading usage...</p> : null}

        {summary ? (
          <div aria-busy={refreshing || undefined} className={`usage__body${refreshing ? " usage__body--refreshing" : ""}`}>
            <div className="stat-row">
              <Tile label="Replies" value={formatCount(summary.turns)} sub={`in the last ${summary.days} days`} />
              <Tile
                label="Typical reply time"
                value={formatMs(summary.latency_ms.total_p50)}
                sub={summary.latency_ms.total_p95 != null ? `slow ones: ${formatMs(summary.latency_ms.total_p95)} (p95)` : null}
              />
              <Tile
                label="First words appear"
                value={formatMs(summary.latency_ms.ttft_p50)}
                sub={summary.latency_ms.ttft_p95 != null ? `p95 ${formatMs(summary.latency_ms.ttft_p95)}` : null}
              />
              <Tile label="Tokens" value={formatCount(tokensTotal)} sub="Free-tier models: $0" />
              <Tile
                label="Errors"
                value={formatPercent(summary.error_rate)}
                sub={<Status ok={summary.error_rate <= 0.05} okText="Healthy" badText="Higher than usual" />}
              />
              <Tile label="Backup model used" value={formatPercent(summary.fallback_rate)} sub="when the main model was busy" />
            </div>

            <section className="usage-card">
              <h4>Replies per day</h4>
              <ColumnChart
                data={summary.daily}
                detail={(d) => `${formatCount(d.tokens)} tokens${d.errors ? `, ${d.errors} error${d.errors > 1 ? "s" : ""}` : ""}`}
                label="Replies per day"
                valueKey="turns"
                valueLabel="replies"
              />
            </section>

            <div className="usage-grid">
              <section className="usage-card">
                <h4>Tokens by model</h4>
                <RankedBars
                  label="Tokens by model"
                  rows={summary.tokens_by_model.map((m) => ({ name: m.model, value: m.input_tokens + m.output_tokens }))}
                />
              </section>
              <section className="usage-card">
                <h4>What the tokens were spent on</h4>
                <RankedBars
                  label="Tokens by purpose"
                  rows={summary.tokens_by_purpose.map((p) => ({ name: purposeLabel(p.purpose, agents), value: p.tokens }))}
                />
              </section>
              <section className="usage-card">
                <h4>Replies by agent</h4>
                <RankedBars
                  label="Replies by agent"
                  rows={Object.entries(summary.agents).map(([name, n]) => ({ name: labelFor(name), value: n }))}
                />
              </section>
            </div>

            <section className="usage-card">
              <h4>Tools</h4>
              {Object.keys(summary.tools).length ? (
                <table className="usage-table">
                  <thead>
                    <tr><th scope="col">Tool</th><th scope="col">Calls</th><th scope="col">Typical time</th><th scope="col">Status</th></tr>
                  </thead>
                  <tbody>
                    {Object.entries(summary.tools).map(([name, t]) => (
                      <tr key={name}>
                        <td>{name.replaceAll("_", " ")}</td>
                        <td>{formatCount(t.calls)}</td>
                        <td>{formatMs(t.p50_ms)}</td>
                        <td><Status ok={t.failures === 0} okText="All succeeded" badText={`${t.failures} failed`} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="usage-empty">No tools used in this period.</p>
              )}
            </section>

            <section className="usage-card">
              <h4>Recent replies</h4>
              {turns.length ? (
                <table className="usage-table">
                  <thead>
                    <tr>
                      <th scope="col">When</th><th scope="col">Agent</th><th scope="col">Reply time</th>
                      <th scope="col">First words</th><th scope="col">Tokens</th><th scope="col">Tools</th><th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {turns.map((t) => (
                      <tr key={t.turn_id}>
                        <td>{new Date(`${t.created_at}Z`).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</td>
                        <td>{labelFor(t.agent_name || "unknown")}</td>
                        <td>{formatMs(t.total_ms)}</td>
                        <td>{formatMs(t.ttft_ms)}</td>
                        <td>{formatCount(t.input_tokens + t.output_tokens)}</td>
                        <td>{t.tool_calls}</td>
                        <td><Status ok={!t.error} okText="OK" badText="Error" /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="usage-empty">No replies yet. Send a message and come back.</p>
              )}
            </section>
          </div>
        ) : null}
      </section>
    </div>
  );
}
