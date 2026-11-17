import { Fragment, useEffect, useRef } from "react";
import { CornerDownRight } from "lucide-react";
import { generatedFileUrl } from "../lib/api";
import { agentIcon, agentLabel } from "../lib/agents";
import ThinkingIndicator from "./ThinkingIndicator";
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

export default function MessageList({ agentStatus, agents, conversation, isLoading, isSending, messages, progress }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isSending, agentStatus, progress]);

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
          <Fragment key={message.id}>
          {message.streaming && isSending ? <ThinkingIndicator agents={agents} progress={progress} /> : null}
          <div className={`message-row message-row--${message.role}`}>
            {switched ? (
              <div className="agent-switch-banner" aria-live="polite">
                <CornerDownRight aria-hidden="true" className="icon" size={14} />
                Switched to <strong className="agent-name">{agentIcon(agent, 14)} {agentLabel(agents, agent)}</strong>
              </div>
            ) : null}
            <article
              className={[
                "message",
                `message--${message.role}`,
                message.pending ? "message--pending" : "",
                message.streaming ? "message--streaming" : "",
                message.error ? "message--error" : "",
              ].join(" ")}
            >
              <div className="message-meta">
                <span className="message-role">
                  {isAssistant ? <>{agentIcon(agent, 15)} {agentLabel(agents, agent)}</> : "You"}
                </span>
                <span className="message-time">{message.pending ? "Sending..." : formatTime(message.created_at)}</span>
              </div>
              <div className={`message-body${isAssistant ? " message-body--markdown" : ""}`}>
                {isAssistant ? <MarkdownMessage content={message.content} /> : renderContentWithLinks(message.content)}
                {message.streaming && !message.content ? <span className="stream-cursor" aria-hidden="true" /> : null}
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
          </Fragment>
        );
      })}

      {isSending && !isStreaming ? <ThinkingIndicator agents={agents} progress={progress} /> : null}

      <div ref={endRef} />
    </div>
  );
}
