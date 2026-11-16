import { getApiBaseUrl } from "./api";
import { getToken } from "./auth";

/** WebSockets can't send headers from the browser, so the token goes in the URL. */
export function buildConversationWebSocketUrl(conversationId) {
  const apiBaseUrl = new URL(getApiBaseUrl());
  const protocol = apiBaseUrl.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${protocol}//${apiBaseUrl.host}/ws/${conversationId}`);
  url.searchParams.set("token", getToken() || "");
  return url.toString();
}
