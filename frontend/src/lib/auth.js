/**
 * Access-token storage.
 *
 * Trade-off: localStorage survives reloads and is simple for a Bearer-token API,
 * but any script running on the page can read it. So the app must never inject
 * untrusted HTML (no dangerouslySetInnerHTML; Markdown is rendered without raw
 * HTML). The alternative, an httpOnly cookie, hides the token from scripts but
 * then needs CSRF protection.
 */
const TOKEN_KEY = "access_token";
const listeners = new Set();

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
  listeners.forEach((listener) => listener(token));
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  listeners.forEach((listener) => listener(null));
}

/** Subscribe to login/logout (also fired when the server rejects the token). */
export function onTokenChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
