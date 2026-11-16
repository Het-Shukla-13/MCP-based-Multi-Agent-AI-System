import { useEffect, useRef } from "react";
import { generatedFileUrl } from "../lib/api";
import { agentIcon, agentLabel, describeStatus } from "../lib/agents";
import MarkdownMessage from "./MarkdownMessage";

function formatTime(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function renderContentWithLinks(content) {
  if (!content) return content;
  const urlRegex = /(https?:\/\/[^\s)]+)/g;
  const parts = [];
  let lastIndex = 0;
  let match;
  while ((match = urlRegex.exec(content)) !== null) {
    if (match.index > lastIndex) parts.push(content.slice(lastIndex, match.index));
    parts.push(<a href={match[0]} key={match.index} rel="noreferrer" target="_blank">{match[0]}</a>);
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) parts.push(content.slice(lastIndex));
  return parts;
}

export default function MessageList({ agentStatus, agents, conversation, isLoading, isSending, messages }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isSending, agentStatus]);

  if (!conversation) {
    return (
      <div className="message-list message-list--empty">
        <div className="empty-state-card">
          <h2>Select a conversation</h2>
          <p>Choose one from the sidebar or create a new chat.</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="message-list message-list--empty">
        <div className="empty-state-card"><h2>Loading messages...</h2></div>
      </div>
    );
  }

  if (messages.length === 0 && !isSending) {
    return (
      <div className="message-list message-list--empty">
        <div className="empty-state-card">
          <h2>{conversation.title}</h2>
          <p>Ask anything, attach files, or type @ to pick an agent.</p>
        </div>
      </div>
    );
  }

  const isStreaming = messages.some((m) => m.streaming);
  // Each reply carries the agent that WROTE it (saved server-side), so labels and
  // switch banners stay correct for old messages after a reload.
  const switchedAt = new Set();
  let previousAgent = null;
  for (const message of messages) {
    if (message.role !== "assistant") continue;
    const agent = message.agent_name || "general";
    if (previousAgent !== null && agent !== previousAgent) switchedAt.add(message.id);
    previousAgent = agent;
  }

  return (
    <div className="message-list">
      {messages.map((message) => {
        const isAssistant = message.role === "assistant";
        const agent = isAssistant ? message.agent_name || "general" : null;
        const switched = switchedAt.has(message.id);

        return (
          <div key={message.id}>
            {switched ? (
              <div className="agent-switch-banner" aria-live="polite">
                ↪ Switched to <strong>{agentIcon(agent)} {agentLabel(agents, agent)}</strong>
              </div>
            ) : null}
            <article
              className={[
                "message",
                `message--${message.role}`,
                message.pending ? "message--pending" : "",
                message.error ? "message--error" : "",
              ].join(" ")}
            >
              <div className="message-meta">
                <span className="message-role">
                  {isAssistant ? `${agentIcon(agent)} ${agentLabel(agents, agent)}` : "You"}
                </span>
                <span className="message-time">{message.pending ? "Sending..." : formatTime(message.created_at)}</span>
              </div>
              <div className={`message-body${isAssistant ? " message-body--markdown" : ""}`}>
                {isAssistant ? <MarkdownMessage content={message.content} /> : renderContentWithLinks(message.content)}
                {message.streaming ? <span className="stream-cursor" aria-hidden="true">▍</span> : null}
              </div>
              {message.files?.length ? (
                <div className="message-files">
                  {message.files.map((file) => (
                    <div className="message-file" key={file.id}>
                      <a className="message-file__name" href={generatedFileUrl(file.id, "preview")} rel="noreferrer" target="_blank">
                        {file.filename}
                      </a>
                      <span className={`message-file__status message-file__status--${file.status}`}>{file.status}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </article>
          </div>
        );
      })}

      {isSending && !isStreaming ? (
        <div className="typing-indicator" aria-live="polite">{describeStatus(agents, agentStatus)}</div>
      ) : null}
      {isStreaming && agentStatus?.status === "tool" ? (
        <div className="typing-indicator" aria-live="polite">{describeStatus(agents, agentStatus)}</div>
      ) : null}

      <div ref={endRef} />
    </div>
  );
}
