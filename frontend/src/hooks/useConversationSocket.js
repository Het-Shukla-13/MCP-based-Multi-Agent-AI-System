import { useCallback, useEffect, useRef, useState } from "react";
import { ensureFreshToken, refreshSession } from "../lib/api";
import { buildConversationWebSocketUrl } from "../lib/socket";
import { progressFromSnapshot, progressReducer } from "../lib/turnProgress";

/**
 * One WebSocket per open conversation, with automatic reconnection.
 *
 * Server -> client events (see README "WebSocket protocol"):
 *   turn_state    {current: {status, agent, draft}, queued}   on connect (replay)
 *   agent_status  {status: routing|working|tool|waiting, agent, tool?, seconds?}
 *   chat_delta    {agent, text}                                streamed reply text
 *   chat          {user_message, ai_message, active_agent, error}  final, saved
 *
 * Streamed text builds a local DRAFT message; the final "chat" event replaces it
 * with the saved message (the server's copy is the source of truth).
 *
 * Deltas are batched: they're buffered and applied once per animation frame, so
 * a fast stream causes at most one render per frame instead of one per token.
 *
 * Reconnection: unexpected closes retry with exponential backoff + jitter. After
 * reconnecting, `onResync` reloads the conversation, so a reply that finished while
 * we were offline still appears. Close code 1008 (auth rejected) refreshes the
 * token first.
 */

export const DRAFT_ID = "draft-assistant";
const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 15000;
const POLICY_VIOLATION = 1008; // server's "not authenticated / not your conversation"

function createTempMessage(content, fileIds) {
  return {
    id: `temp-${crypto.randomUUID()}`,
    content,
    created_at: new Date().toISOString(),
    pending: true,
    role: "user",
    file_ids: fileIds,
  };
}

function appendDraft(messages, text, agent) {
  if (messages.some((m) => m.id === DRAFT_ID)) {
    return messages.map((m) => (m.id === DRAFT_ID ? { ...m, content: m.content + text } : m));
  }
  return [
    ...messages,
    { id: DRAFT_ID, role: "assistant", content: text, agent_name: agent, streaming: true, created_at: new Date().toISOString() },
  ];
}

function replaceWithSaved(messages, userMessage, aiMessage) {
  const next = messages.filter((m) => m.id !== DRAFT_ID);
  const pendingIndex = next.findIndex((m) => m.pending && m.role === "user");
  if (pendingIndex >= 0) next.splice(pendingIndex, 1, userMessage);
  else if (!next.some((m) => m.id === userMessage.id)) next.push(userMessage);
  if (!next.some((m) => m.id === aiMessage.id)) next.push(aiMessage);
  return next;
}

/** 1s, 2s, 4s, 8s, 15s, 15s... plus up to 30% random jitter, so clients that lost
 * the same server don't all reconnect at the same instant ("thundering herd"). */
function backoffDelay(attempt) {
  const base = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt);
  return base + Math.random() * base * 0.3;
}

export function useConversationSocket({
  selectedAgent,
  selectedConversationId,
  setMessagesByConversation,
  setStatusMessage,
  onResync,
}) {
  const socketRef = useRef(null);
  // Keyed by conversation so switching chats never shows another chat's state.
  const [connection, setConnection] = useState({ conversationId: null, state: "idle" });
  const [sendingConversationId, setSendingConversationId] = useState("");
  const [agentStatus, setAgentStatus] = useState(null); // {conversationId, status, agent, tool}
  const [progress, setProgress] = useState({ conversationId: null, state: null }); // checklist (turnProgress.js)
  const onResyncRef = useRef(onResync);
  useEffect(() => {
    onResyncRef.current = onResync;
  }, [onResync]);

  const updateMessages = useCallback(
    (conversationId, updater) =>
      setMessagesByConversation((current) => ({
        ...current,
        [conversationId]: updater(current[conversationId] || []),
      })),
    [setMessagesByConversation]
  );

  useEffect(() => {
    if (!selectedConversationId) return undefined;
    const conversationId = selectedConversationId;
    let socket = null;
    let stopped = false; // set when the user leaves this conversation / unmounts
    let attempt = 0;
    let retryTimer = null;
    let hasConnectedBefore = false;

    const isCurrent = (s) => !stopped && socketRef.current === s;
    const step = (event) =>
      setProgress((current) => ({
        conversationId,
        state: progressReducer(current.conversationId === conversationId ? current.state : null, event),
      }));

    // ---- delta batching: one state update per animation frame ----
    let buffered = null; // { text, agent }
    let frame = 0;
    let writing = false; // "Writing the answer" step already shown for this turn
    const flush = () => {
      frame = 0;
      if (!buffered) return;
      const { text, agent } = buffered;
      buffered = null;
      updateMessages(conversationId, (messages) => appendDraft(messages, text, agent));
    };
    const flushNow = () => {
      if (frame) window.cancelAnimationFrame(frame);
      flush();
    };

    const finishTurn = () => {
      flushNow();
      writing = false;
      setSendingConversationId((c) => (c === conversationId ? "" : c));
      setAgentStatus(null);
      setProgress({ conversationId, state: null });
    };

    const handleMessage = (event) => {
      const payload = JSON.parse(event.data);
      const data = payload.data || {};

      if (payload.type === "turn_state") {
        // Replay after (re)connecting: a reply may be mid-stream on the server.
        const current = data.current;
        if (current?.status === "running") {
          setSendingConversationId(conversationId);
          if (current.draft) {
            writing = true;
            updateMessages(conversationId, (messages) =>
              appendDraft(messages.filter((m) => m.id !== DRAFT_ID), current.draft, current.agent)
            );
          }
          setProgress({ conversationId, state: progressFromSnapshot(current) });
        }
        return;
      }

      if (payload.type === "agent_status") {
        setAgentStatus({ conversationId, status: data.status, agent: data.agent, tool: data.tool });
        step(data);
        return;
      }

      if (payload.type === "chat_delta") {
        if (!writing) {
          writing = true;
          step({ status: "writing", agent: data.agent });
        }
        if (!buffered) buffered = { text: "", agent: data.agent };
        buffered.text += data.text;
        if (!frame) frame = window.requestAnimationFrame(flush);
        return;
      }

      if (payload.type === "chat") {
        flushNow(); // apply any buffered text before the saved message replaces the draft
        const aiMessage = { ...data.ai_message, error: data.error === true };
        updateMessages(conversationId, (messages) => replaceWithSaved(messages, data.user_message, aiMessage));
        finishTurn();
        if (data.error) setStatusMessage("The assistant could not complete that request.", "error");
        return;
      }

      if (payload.type === "error") {
        flushNow();
        updateMessages(conversationId, (messages) => messages.filter((m) => !m.pending && m.id !== DRAFT_ID));
        finishTurn();
        setStatusMessage(payload.detail || "Failed to process the message.", "error");
      }
    };

    const scheduleReconnect = (needsFreshToken) => {
      if (stopped) return;
      const delay = backoffDelay(attempt);
      attempt += 1;
      setConnection({ conversationId, state: "reconnecting" });
      retryTimer = window.setTimeout(() => void connect(needsFreshToken), delay);
    };

    const connect = async (needsFreshToken = false) => {
      if (stopped) return;
      try {
        // A WebSocket can't "retry on 401" like an HTTP call: make sure the token is
        // fresh BEFORE connecting (forced after the server rejected it).
        if (needsFreshToken) await refreshSession();
        else await ensureFreshToken();
      } catch {
        return; // refresh failed -> session cleared -> the app shows sign-in
      }
      if (stopped) return;

      const s = new WebSocket(buildConversationWebSocketUrl(conversationId));
      socket = s;
      socketRef.current = s;

      s.onopen = () => {
        if (!isCurrent(s)) return;
        attempt = 0;
        setConnection({ conversationId, state: "connected" });
        if (hasConnectedBefore) {
          // We were offline: a reply may have finished meanwhile. Reload saved messages;
          // a reply still running is restored by the turn_state event that follows.
          finishTurn();
          updateMessages(conversationId, (messages) => messages.filter((m) => m.id !== DRAFT_ID));
          onResyncRef.current?.(conversationId);
          setStatusMessage("Reconnected.", "success");
        }
        hasConnectedBefore = true;
      };

      s.onmessage = (event) => {
        if (isCurrent(s)) handleMessage(event);
      };

      s.onclose = (event) => {
        if (!isCurrent(s)) return; // closed on purpose (chat switched / unmounted)
        finishTurn();
        scheduleReconnect(event.code === POLICY_VIOLATION);
      };
      // onerror is always followed by onclose, which handles reconnection.
    };

    // Back online -> reconnect now instead of waiting for the backoff timer.
    const onOnline = () => {
      if (stopped || socket?.readyState === WebSocket.OPEN) return;
      window.clearTimeout(retryTimer);
      attempt = 0;
      void connect();
    };
    window.addEventListener("online", onOnline);

    void connect();

    return () => {
      stopped = true;
      if (frame) window.cancelAnimationFrame(frame);
      window.clearTimeout(retryTimer);
      window.removeEventListener("online", onOnline);
      if (socket) socket.close();
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [selectedConversationId, setStatusMessage, updateMessages]);

  const sendMessage = (content, attachedFileIds = [], options = {}) => {
    const socket = socketRef.current;
    if (!selectedConversationId || !socket || socket.readyState !== WebSocket.OPEN) {
      setStatusMessage("Not connected right now. Reconnecting; try again in a moment.", "warning");
      return false;
    }
    updateMessages(selectedConversationId, (messages) => [...messages, createTempMessage(content, attachedFileIds)]);
    setSendingConversationId(selectedConversationId);
    setStatusMessage("");
    socket.send(
      JSON.stringify({
        content,
        file_ids: attachedFileIds,
        selected_agent: selectedAgent || null, // explicit pick skips the router
        format: options.format || null, // ask the agent for a downloadable file
      })
    );
    return true;
  };

  // Derived (not stored) state: what applies to the conversation on screen now.
  const connectionState = !selectedConversationId
    ? "idle"
    : connection.conversationId === selectedConversationId
      ? connection.state
      : "connecting";

  return {
    agentStatus: agentStatus?.conversationId === selectedConversationId ? agentStatus : null,
    progress: progress.conversationId === selectedConversationId ? progress.state : null,
    connectionState,
    isSending: !!selectedConversationId && sendingConversationId === selectedConversationId,
    sendMessage,
  };
}
