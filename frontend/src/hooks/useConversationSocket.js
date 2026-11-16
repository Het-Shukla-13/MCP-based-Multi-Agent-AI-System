import { useCallback, useEffect, useRef, useState } from "react";
import { ensureFreshToken } from "../lib/api";
import { buildConversationWebSocketUrl } from "../lib/socket";

/**
 * One WebSocket per open conversation.
 *
 * Server -> client events (see README "WebSocket protocol"):
 *   agent_status  {status: routing|working|tool, agent, tool?}  live progress
 *   chat_delta    {agent, text}                                streamed reply text
 *   chat          {user_message, ai_message, active_agent, error}  final, saved
 *
 * The streamed text builds a local DRAFT message; the final "chat" event replaces
 * it with the saved message (the server's copy is the source of truth).
 */

const DRAFT_ID = "draft-assistant";

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

function replaceWithSaved(messages, userMessage, aiMessage) {
  const next = messages.filter((m) => m.id !== DRAFT_ID);
  const pendingIndex = next.findIndex((m) => m.pending && m.role === "user");
  if (pendingIndex >= 0) next.splice(pendingIndex, 1, userMessage);
  else if (!next.some((m) => m.id === userMessage.id)) next.push(userMessage);
  if (!next.some((m) => m.id === aiMessage.id)) next.push(aiMessage);
  return next;
}

export function useConversationSocket({
  selectedAgent,
  selectedConversationId,
  setMessagesByConversation,
  setStatusMessage,
}) {
  const socketRef = useRef(null);
  // Keyed by conversation so switching chats never shows another chat's state.
  const [connection, setConnection] = useState({ conversationId: null, state: "idle" });
  const [sendingConversationId, setSendingConversationId] = useState("");
  const [agentStatus, setAgentStatus] = useState(null); // {conversationId, status, agent, tool}

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
    let cancelled = false;
    const isCurrent = () => socket !== null && socketRef.current === socket;
    const finishTurn = () => {
      setSendingConversationId((c) => (c === conversationId ? "" : c));
      setAgentStatus(null);
    };

    const wire = () => {
      socket.onopen = () => isCurrent() && setConnection({ conversationId, state: "connected" });

      socket.onmessage = (event) => {
        if (!isCurrent()) return;
        const payload = JSON.parse(event.data);
        const data = payload.data || {};

        if (payload.type === "agent_status") {
          setAgentStatus({ conversationId, status: data.status, agent: data.agent, tool: data.tool });
          return;
        }

        if (payload.type === "chat_delta") {
          updateMessages(conversationId, (messages) => {
            const draft = messages.find((m) => m.id === DRAFT_ID);
            if (draft) {
              return messages.map((m) => (m.id === DRAFT_ID ? { ...m, content: m.content + data.text } : m));
            }
            return [
              ...messages,
              { id: DRAFT_ID, role: "assistant", content: data.text, agent_name: data.agent, streaming: true, created_at: new Date().toISOString() },
            ];
          });
          return;
        }

        if (payload.type === "chat") {
          const aiMessage = { ...data.ai_message, error: data.error === true };
          updateMessages(conversationId, (messages) => replaceWithSaved(messages, data.user_message, aiMessage));
          finishTurn();
          setStatusMessage(data.error ? "The assistant could not complete that request." : "");
          return;
        }

        if (payload.type === "error") {
          updateMessages(conversationId, (messages) => messages.filter((m) => !m.pending && m.id !== DRAFT_ID));
          finishTurn();
          setStatusMessage(payload.detail || "Failed to process the message.");
        }
      };

      socket.onerror = () => {
        if (!isCurrent()) return;
        setConnection({ conversationId, state: "error" });
        finishTurn();
        setStatusMessage("Connection problem. Reconnect by reopening the chat.");
      };

      socket.onclose = () => {
        if (!isCurrent()) return;
        setConnection({ conversationId, state: "closed" });
        finishTurn();
      };
    };

    // A WebSocket can't "retry on 401" like an HTTP call, so make sure the access
    // token is fresh BEFORE connecting (refreshes it if it expires within a minute).
    ensureFreshToken()
      .then(() => {
        if (cancelled) return;
        socket = new WebSocket(buildConversationWebSocketUrl(conversationId));
        socketRef.current = socket;
        wire();
      })
      .catch(() => {}); // refresh failed -> session cleared -> app shows sign-in

    return () => {
      cancelled = true;
      if (socket) socket.close();
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [selectedConversationId, setStatusMessage, updateMessages]);

  const sendMessage = (content, attachedFileIds = [], options = {}) => {
    const socket = socketRef.current;
    if (!selectedConversationId || !socket || socket.readyState !== WebSocket.OPEN) {
      setStatusMessage("Chat connection is not ready yet.");
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
        format: options.format || null,       // ask the agent for a downloadable file
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
    connectionState,
    isSending: !!selectedConversationId && sendingConversationId === selectedConversationId,
    sendMessage,
  };
}
