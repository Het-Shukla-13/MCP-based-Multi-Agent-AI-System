import { useCallback, useEffect, useRef, useState } from "react";
import { copyText } from "../lib/clipboard";

/** copy(text) -> state "copied" for 1.5s (or "failed"), then back to idle. */
export function useCopy() {
  const [state, setState] = useState("idle"); // idle | copied | failed
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const copy = useCallback(async (text) => {
    try {
      await copyText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 1500);
  }, []);
  return [state, copy];
}
