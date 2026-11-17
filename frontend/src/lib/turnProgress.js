/*
 * Live progress of one turn as a checklist, built from the server's agent_status
 * events. Pure functions (no React) so the rules are easy to read and test.
 *
 * The server only says when a step STARTS (routing, an agent working, a tool call,
 * text streaming). A step is therefore done when the next one starts or the turn
 * ends - the same inference most chat UIs make.
 *
 * state: null (idle) | { steps: [{ key, kind, agent, tool, done }], waitingUntil }
 *   kind: routing | agent | tool | approval | writing
 */

const finishAll = (steps) => steps.map((s) => (s.done ? s : { ...s, done: true }));

function push(state, step) {
  const steps = state?.steps || [];
  const last = steps[steps.length - 1];
  if (last && last.key === step.key && !last.done) return { ...state, steps }; // duplicate event
  return { waitingUntil: null, ...state, steps: [...finishAll(steps), { done: false, ...step }] };
}

/** event: an agent_status payload ({status, agent, tool, seconds}) or {status: "writing"}. */
export function progressReducer(state, event, now = Date.now()) {
  switch (event.status) {
    case "routing":
      return push(null, { key: "routing", kind: "routing", agent: "root" });
    case "working":
      return push(state, { key: `agent:${event.agent}`, kind: "agent", agent: event.agent });
    case "tool": {
      const count = (state?.steps || []).filter((s) => s.kind === "tool").length;
      return push(state, { key: `tool:${count}:${event.tool}`, kind: "tool", agent: event.agent, tool: event.tool });
    }
    case "writing":
      return push(state, { key: "writing", kind: "writing", agent: event.agent });
    case "awaiting_approval": {
      const count = (state?.steps || []).filter((s) => s.kind === "approval").length;
      return push(state, { key: `approval:${count}`, kind: "approval", agent: event.agent, tool: event.tool });
    }
    case "approval_resolved":
      // The user answered: tick the approval step (the tool then runs or is skipped).
      return state && { ...state, steps: state.steps.map((s) => (s.kind === "approval" ? { ...s, done: true } : s)) };
    case "waiting":
      // Not a step: a temporary pause of the current one (rate limit), shown as a countdown.
      return { steps: state?.steps || [], waitingUntil: now + (event.seconds || 0) * 1000 };
    default:
      return state;
  }
}

/** Rebuild an approximate checklist from a turn_state snapshot (after a reconnect). */
export function progressFromSnapshot(current) {
  if (!current || current.status !== "running") return null;
  let state = null;
  if (current.agent) state = progressReducer(state, { status: "working", agent: current.agent });
  if (current.draft) state = progressReducer(state, { status: "writing", agent: current.agent });
  return state || progressReducer(null, { status: "routing" });
}

export function stepLabel(step, labelFor) {
  if (step.kind === "routing") return "Choosing the best agent";
  if (step.kind === "agent") return `${labelFor(step.agent)} is on it`;
  if (step.kind === "tool") return `Using ${step.tool.replaceAll("_", " ")}`;
  if (step.kind === "approval") return "Waiting for your approval";
  return "Writing the answer";
}
