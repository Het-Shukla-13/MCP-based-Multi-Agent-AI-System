/*
 * Theme preference: "system" (default), "light" or "dark", stored in localStorage.
 * index.html applies it with an inline script BEFORE the first paint, so the page
 * never flashes the wrong theme; this module keeps it in sync afterwards.
 */
const KEY = "theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function getThemePreference() {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system"; // storage blocked (private mode): just follow the OS
  }
}

export function resolveTheme(preference = getThemePreference()) {
  if (preference === "system") return media().matches ? "dark" : "light";
  return preference;
}

export function applyTheme(preference = getThemePreference()) {
  document.documentElement.dataset.theme = resolveTheme(preference);
}

export function setThemePreference(preference) {
  try {
    if (preference === "system") window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, preference);
  } catch {
    /* ignore: the choice still applies for this page view */
  }
  applyTheme(preference);
}

/** While the preference is "system", follow OS changes live (e.g. sunset switch). */
export function followSystemTheme() {
  applyTheme();
  media().addEventListener("change", () => {
    if (getThemePreference() === "system") applyTheme("system");
  });
}

export const THEME_CYCLE = { system: "light", light: "dark", dark: "system" };
