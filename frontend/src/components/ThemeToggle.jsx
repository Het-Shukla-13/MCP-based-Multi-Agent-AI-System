import { useState } from "react";
import { getThemePreference, setThemePreference, THEME_CYCLE } from "../lib/theme";

const LABELS = { system: "Auto", light: "Light", dark: "Dark" };

/** Cycles Auto (follow the OS) -> Light -> Dark. */
export default function ThemeToggle() {
  const [preference, setPreference] = useState(getThemePreference);
  const next = THEME_CYCLE[preference];
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => {
        setThemePreference(next);
        setPreference(next);
      }}
      aria-label={`Theme: ${LABELS[preference]}. Switch to ${LABELS[next]}`}
      title={`Theme: ${LABELS[preference]} (click for ${LABELS[next]})`}
    >
      <span className="theme-toggle__swatch" aria-hidden="true" />
      {LABELS[preference]}
    </button>
  );
}
