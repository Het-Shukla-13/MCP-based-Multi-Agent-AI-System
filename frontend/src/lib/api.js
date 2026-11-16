import axios from "axios";
import { clearToken, getToken } from "./auth";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export const api = axios.create({ baseURL: API_BASE_URL });

// Attach the access token to every request.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// An expired or invalid token logs the user out everywhere at once.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && getToken()) clearToken();
    return Promise.reject(error);
  }
);

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
