import { useEffect, useState } from "react";
import { Check, Hourglass, LoaderCircle } from "lucide-react";
import { agentIcon, agentLabel } from "../lib/agents";
import { stepLabel } from "../lib/turnProgress";

/** Seconds left until `until` (ms), ticking once a second while > 0. */
function useCountdown(until) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!until) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [until]);
  return until ? Math.max(0, Math.ceil((until - now) / 1000)) : 0;
}

/**
 * Live checklist of the running turn: routing -> agent -> tools -> writing.
 * `compact` once the answer is streaming (a quiet row of chips above the draft).
 */
export default function ThinkingIndicator({ agents, progress }) {
  const waitingSeconds = useCountdown(progress?.waitingUntil);
  const steps = progress?.steps?.length ? progress.steps : [{ key: "start", kind: "routing", agent: "root", done: false }];
  const labelFor = (name) => agentLabel(agents, name);
  const compact = steps.some((s) => s.kind === "writing");
  const current = steps.find((s) => !s.done) || steps[steps.length - 1];
  const announce = waitingSeconds
    ? `Rate-limited by the AI provider, retrying in ${waitingSeconds} seconds`
    : stepLabel(current, labelFor);

  return (
    <div className={`thinking${compact ? " thinking--compact" : ""}`}>
      <span className="visually-hidden" role="status">{announce}</span>
      <ol className="thinking__steps" aria-hidden="true">
        {steps.map((step) => (
          <li className={`thinking__step${step.done ? " thinking__step--done" : ""}`} key={step.key}>
            {step.done ? (
              <Check className="thinking__icon" size={14} />
            ) : (
              <LoaderCircle className="thinking__icon thinking__icon--spin" size={14} />
            )}
            {step.kind === "agent" ? agentIcon(step.agent, 14) : null}
            <span>{stepLabel(step, labelFor)}</span>
          </li>
        ))}
      </ol>
      {waitingSeconds ? (
        <p className="thinking__waiting">
          <Hourglass aria-hidden="true" size={14} />
          The AI provider is rate-limiting us. Retrying in {waitingSeconds}s...
        </p>
      ) : null}
    </div>
  );
}
