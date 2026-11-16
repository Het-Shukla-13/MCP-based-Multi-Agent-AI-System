/**
 * Session tokens.
 *
 * access_token  : short-lived JWT sent on every request.
 * refresh_token : long-lived, used ONLY to get a new pair from /auth/refresh.
 *                 The server rotates it on every use and treats reuse of an old
 *                 one as theft (ends the session), so refreshes must never race.
 *
 * Trade-off: localStorage survives reloads but any script on the page can read
 * it, so the app never renders untrusted HTML (react-markdown without raw HTML).
 */
const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";
const EXPIRES_KEY = "access_expires_at";
const listeners = new Set();

export function getToken() {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}

/** True when the access token expires within `marginMs` (or its expiry is unknown). */
export function accessTokenExpiresSoon(marginMs = 60_000) {
  const expiresAt = Number(localStorage.getItem(EXPIRES_KEY) || 0);
  return !expiresAt || Date.now() > expiresAt - marginMs;
}

/** Save the pair returned by /auth/login, /auth/register or /auth/refresh. */
export function setSession({ access_token, refresh_token, expires_in }) {
  localStorage.setItem(ACCESS_KEY, access_token);
  if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
  localStorage.setItem(EXPIRES_KEY, String(Date.now() + (expires_in || 3600) * 1000));
  listeners.forEach((listener) => listener(access_token));
}

export function clearToken() {
  [ACCESS_KEY, REFRESH_KEY, EXPIRES_KEY].forEach((key) => localStorage.removeItem(key));
  listeners.forEach((listener) => listener(null));
}

/** Subscribe to sign-in / sign-out (including server-side session expiry). */
export function onTokenChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
