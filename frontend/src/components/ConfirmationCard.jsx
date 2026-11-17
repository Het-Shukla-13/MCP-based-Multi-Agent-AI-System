import { useEffect, useState } from "react";
import { Check, CheckCheck, FileText, ImageIcon, LayoutTemplate, PenLine, ShieldQuestion, X } from "lucide-react";
import { agentLabel } from "../lib/agents";

const TOOLS = {
  create_file: { icon: FileText, verb: "Create a file" },
  create_from_template: { icon: LayoutTemplate, verb: "Create a document from a template" },
  generate_image: { icon: ImageIcon, verb: "Generate an image" },
};

function useSecondsLeft(expiresAt) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return Math.max(0, Math.ceil((expiresAt - now) / 1000));
}

const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** What the tool will do, in words (args are already previewed/truncated server-side). */
function Summary({ tool, args }) {
  if (tool === "create_file") {
    return (
      <>
        <p className="confirm-card__line">
          <strong>{args.title || "Untitled"}</strong>
          {args.file_format ? <span className="confirm-card__tag">.{args.file_format}</span> : null}
        </p>
        {args.content ? (
          <details className="confirm-card__preview">
            <summary>Preview content</summary>
            <pre>{String(args.content)}</pre>
          </details>
        ) : null}
      </>
    );
  }
  if (tool === "create_from_template") {
    return (
      <>
        <p className="confirm-card__line">
          <strong>{args.title || "Untitled"}</strong> from the <em>{args.template}</em> template
          {args.file_format ? <span className="confirm-card__tag">.{args.file_format}</span> : null}
        </p>
        {args.fields && typeof args.fields === "object" ? (
          <details className="confirm-card__preview">
            <summary>Preview fields</summary>
            <dl>
              {Object.entries(args.fields).map(([key, value]) => (
                <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
              ))}
            </dl>
          </details>
        ) : null}
      </>
    );
  }
  if (tool === "generate_image") {
    return (
      <p className="confirm-card__line">
        &ldquo;{args.prompt}&rdquo;
        {args.width && args.height ? <span className="confirm-card__tag">{args.width}×{args.height}</span> : null}
      </p>
    );
  }
  return (
    <dl className="confirm-card__args">
      {Object.entries(args).map(([key, value]) => (
        <div key={key}><dt>{key}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>
      ))}
    </dl>
  );
}

/**
 * "The agent wants to <do something>": approve / approve all / revise / reject.
 * Unanswered requests expire server-side (treated as rejected), so the buttons lock
 * when the countdown reaches zero.
 */
export default function ConfirmationCard({ agents, confirmation, onDecide }) {
  const [revising, setRevising] = useState(false);
  const [feedback, setFeedback] = useState("");
  const secondsLeft = useSecondsLeft(confirmation.expiresAt);
  const { icon: Icon, verb } = TOOLS[confirmation.tool] || { icon: ShieldQuestion, verb: `Run ${confirmation.tool}` };
  const locked = confirmation.submitting || secondsLeft === 0;
  const decide = (decision, text = "") => onDecide(confirmation.id, decision, text);

  return (
    <section aria-label={`Approval needed: ${verb}`} className="confirm-card">
      <header className="confirm-card__header">
        <Icon aria-hidden="true" className="confirm-card__icon" size={18} />
        <div>
          <p className="confirm-card__title">{agentLabel(agents, confirmation.agent)} wants to {verb.toLowerCase()}</p>
          <p className="confirm-card__expiry">
            {secondsLeft === 0 ? "Expired: treated as rejected" : `Waiting for you · expires in ${mmss(secondsLeft)}`}
          </p>
        </div>
      </header>

      <Summary args={confirmation.args} tool={confirmation.tool} />

      {revising ? (
        <form
          className="confirm-card__revise"
          onSubmit={(e) => {
            e.preventDefault();
            if (feedback.trim()) decide("revise", feedback.trim());
          }}
        >
          <label className="visually-hidden" htmlFor={`revise-${confirmation.id}`}>What should change?</label>
          <textarea
            autoFocus
            disabled={locked}
            id={`revise-${confirmation.id}`}
            maxLength={1000}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="What should change? e.g. call it summary.md and add a conclusion"
            rows={2}
            value={feedback}
          />
          <div className="confirm-card__actions">
            <button className="secondary-button" disabled={locked} onClick={() => setRevising(false)} type="button">Cancel</button>
            <button className="primary-button button-with-icon" disabled={locked || !feedback.trim()} type="submit">
              <PenLine aria-hidden="true" size={15} />
              Send feedback
            </button>
          </div>
        </form>
      ) : (
        <div className="confirm-card__actions">
          <button className="primary-button button-with-icon" disabled={locked} onClick={() => decide("approve")} type="button">
            <Check aria-hidden="true" size={15} />
            Approve
          </button>
          <button
            className="secondary-button button-with-icon"
            disabled={locked}
            onClick={() => decide("approve_all")}
            title="Approve this and any further requests in this reply"
            type="button"
          >
            <CheckCheck aria-hidden="true" size={15} />
            Approve all
          </button>
          <button className="secondary-button button-with-icon" disabled={locked} onClick={() => setRevising(true)} type="button">
            <PenLine aria-hidden="true" size={15} />
            Revise
          </button>
          <button className="secondary-button button-with-icon confirm-card__reject" disabled={locked} onClick={() => decide("reject")} type="button">
            <X aria-hidden="true" size={15} />
            Reject
          </button>
        </div>
      )}
    </section>
  );
}
