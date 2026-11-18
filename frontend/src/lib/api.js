import axios from "axios";
import { accessTokenExpiresSoon, clearToken, getRefreshToken, getToken, setSession } from "./auth";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export const api = axios.create({ baseURL: API_BASE_URL });

// Attach the access token to every request.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Plain client for /auth/refresh: it must not go through the interceptors below
// (a failing refresh would otherwise try to refresh itself).
const authClient = axios.create({ baseURL: API_BASE_URL });

/**
 * Single-flight refresh: concurrent callers share ONE in-flight request. Two
 * parallel refreshes would rotate the token twice; the server sees the second as
 * reuse of a revoked token (= theft) and ends the whole session.
 */
let refreshInFlight = null;

export function refreshSession() {
  if (!refreshInFlight) {
    const refreshToken = getRefreshToken();
    refreshInFlight = (refreshToken
      ? authClient.post("/auth/refresh", { refresh_token: refreshToken }).then(({ data }) => {
          setSession(data);
          return data.access_token;
        })
      : Promise.reject(new Error("No refresh token"))
    )
      .catch((error) => {
        clearToken(); // refresh failed: the session is over, back to sign-in
        throw error;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

/** Valid access token for things that can't retry on 401 (opening a WebSocket). */
export async function ensureFreshToken() {
  if (getToken() && !accessTokenExpiresSoon()) return getToken();
  return refreshSession();
}

// 401 -> refresh once, then replay the original request with the new token.
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status !== 401 || !original || original._retried || !getRefreshToken()) {
      return Promise.reject(error);
    }
    original._retried = true; // never loop: a second 401 is final
    try {
      const token = await refreshSession();
      original.headers.Authorization = `Bearer ${token}`;
      return api(original);
    } catch {
      return Promise.reject(error);
    }
  }
);

/** Sign out everywhere: revoke on the server, then forget locally. */
export async function logout() {
  const refreshToken = getRefreshToken();
  clearToken();
  if (refreshToken) {
    try {
      await authClient.post("/auth/logout", { refresh_token: refreshToken });
    } catch {
      // Already signed out locally; an unreachable server is not a reason to stay signed in.
    }
  }
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}

/** Readable error text from an API failure (FastAPI returns {detail}). */
export function errorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg; // validation errors
  return fallback;
}

// ---- auth ----
export async function register(email, password) {
  return (await api.post("/auth/register", { email, password })).data;
}

export async function login(email, password) {
  return (await api.post("/auth/login", { email, password })).data;
}

export async function fetchMe() {
  return (await api.get("/auth/me")).data;
}

// ---- conversations ----
export async function fetchConversations() {
  return (await api.get("/conversations/")).data;
}

export async function createConversation(title) {
  return (await api.post("/conversations/", { title })).data;
}

export async function renameConversation(conversationId, title) {
  return (await api.patch(`/conversations/${conversationId}`, { title })).data;
}

export async function deleteConversation(conversationId) {
  await api.delete(`/conversations/${conversationId}`);
}

/** Full-text search over the user's conversations. `signal` cancels a stale request. */
export async function searchConversations(query, { signal } = {}) {
  const { data } = await api.get("/conversations/search", { params: { q: query }, signal });
  return data.results;
}

/** Usage summary for the signed-in user (latency, tokens, tools, a daily series). */
export async function fetchUsageSummary(days, { signal } = {}) {
  return (await api.get("/metrics/summary", { params: { days }, signal })).data;
}

export async function fetchRecentTurns(limit = 20, { signal } = {}) {
  return (await api.get("/metrics/turns", { params: { limit }, signal })).data;
}

export async function fetchMessages(conversationId) {
  return (await api.get("/messages/", { params: { conversation_id: conversationId } })).data;
}

// ---- files ----
export async function fetchConversationFiles(conversationId) {
  return (await api.get("/files/", { params: { conversation_id: conversationId } })).data;
}

export async function uploadConversationFiles({ conversationId, files }) {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const response = await api.post("/files/upload", formData, {
    params: { conversation_id: conversationId },
  });
  return response.data;
}

export async function fetchAgents() {
  return (await api.get("/ws/agents")).data.agents;
}

/**
 * Links the BROWSER opens itself (<a href>, <img src>, new tab) can't carry the
 * Authorization header, so the token goes in the query string. The backend accepts
 * ?token= only on these read-only file routes.
 */
export function withToken(path) {
  const url = new URL(path, API_BASE_URL);
  const token = getToken();
  if (token) url.searchParams.set("token", token);
  return url.toString();
}

export const generatedFileUrl = (fileId, kind = "preview") =>
  withToken(`/files/generated/${fileId}/${kind}`);

// ---- export / import ----
export async function exportConversation(conversationId) {
  return (await api.get(`/conversations/${conversationId}/export`)).data;
}

export async function importConversation(payload) {
  return (await api.post("/conversations/import", payload)).data;
}

// ---- memories (always the signed-in user's) ----
export async function listMemories({ includeInactive = false } = {}) {
  return (await api.get("/memories", { params: { include_inactive: includeInactive } })).data;
}

export async function searchMemories(query) {
  return (await api.get("/memories/search", { params: { query, top_k: 10 } })).data;
}

export async function createMemory(content, memoryType) {
  return (await api.post("/memories", { content, memory_type: memoryType })).data;
}

export async function updateMemory(memoryId, changes) {
  return (await api.patch(`/memories/${memoryId}`, changes)).data;
}

export async function removeMemory(memoryId, { hard = false } = {}) {
  await api.delete(`/memories/${memoryId}`, { params: { hard } });
}

export async function fetchProfile() {
  return (await api.get("/memories/profile")).data;
}

export async function rebuildProfile() {
  return (await api.post("/memories/profile/rebuild")).data;
}

export async function removeProfileItem(value) {
  return (await api.delete("/memories/profile/items", { params: { value } })).data;
}
