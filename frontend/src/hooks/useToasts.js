import { useCallback, useEffect, useRef, useState } from "react";

const DURATION = { info: 4000, success: 3500, warning: 6000, error: 8000 };
const MAX_VISIBLE = 3;

/**
 * Transient notifications. notify(message, tone) where tone is
 * info | success | warning | error. Empty messages are ignored (callers used ""
 * to clear the old status banner), and an identical message already on screen
 * isn't stacked twice.
 */
export function useToasts() {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());

  const dismiss = useCallback((id) => {
    window.clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback(
    (message, tone = "info") => {
      if (!message) return;
      const id = crypto.randomUUID();
      setToasts((current) => {
        if (current.some((toast) => toast.message === message)) return current;
        return [...current, { id, message, tone }].slice(-MAX_VISIBLE);
      });
      timers.current.set(id, window.setTimeout(() => dismiss(id), DURATION[tone] ?? DURATION.info));
    },
    [dismiss]
  );

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => window.clearTimeout(timer));
  }, []);

  return { toasts, notify, dismiss };
}
