import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from "lucide-react";

const ICONS = { info: Info, success: CircleCheck, warning: TriangleAlert, error: CircleAlert };

/**
 * Two live regions: errors are announced immediately (role="alert"), everything
 * else politely, so screen readers aren't interrupted by "Conversation renamed".
 */
export default function Toaster({ toasts, onDismiss }) {
  const render = (toast) => {
    const Icon = ICONS[toast.tone] || Info;
    return (
      <div className={`toast toast--${toast.tone}`} key={toast.id}>
        <Icon aria-hidden="true" className="toast__icon" size={18} />
        <p className="toast__message">{toast.message}</p>
        <button aria-label="Dismiss notification" className="icon-button toast__close" onClick={() => onDismiss(toast.id)} type="button">
          <X aria-hidden="true" size={16} />
        </button>
      </div>
    );
  };
  return (
    <div className="toaster">
      <div aria-live="polite" className="toaster__stack">{toasts.filter((t) => t.tone !== "error").map(render)}</div>
      <div className="toaster__stack" role="alert">{toasts.filter((t) => t.tone === "error").map(render)}</div>
    </div>
  );
}
