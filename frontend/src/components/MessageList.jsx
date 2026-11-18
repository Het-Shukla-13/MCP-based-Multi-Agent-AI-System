import { Fragment, useLayoutEffect, useRef, useState } from "react";
import { ArrowDown, CornerDownRight, Sparkles } from "lucide-react";
import { generatedFileUrl } from "../lib/api";
import { agentIcon, agentLabel } from "../lib/agents";
import ConfirmationCard from "./ConfirmationCard";
import { CopyButton } from "./MarkdownMessage";
import { useCopy } from "../hooks/useCopy";
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

const SHORTCUT = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "⌘K" : "Ctrl K";

// Starter prompts for an empty chat: one per kind of agent, so new users see the range.
const SUGGESTIONS = [
  { agent: "research", text: "Plan a relaxed 2-day trip to Lisbon in May" },
  { agent: "data", text: "Analyse the CSV I attach: revenue by region as a table" },
  { agent: "code", text: "Explain this Python function and point out bugs" },
  { agent: "document", text: "Summarise the PDF I attach in 5 bullet points" },
  { agent: "image", text: "Generate an image of a cosy reading nook at sunset" },
  { agent: "general", text: "Write meeting notes as a downloadable PDF" },
];

function AnswerCopy({ content }) {
  const [state, copy] = useCopy();
  return <CopyButton label="Copy answer" onCopy={() => copy(content)} state={state} />;
}

export default function MessageList({
  agentStatus,
  agents,
  confirmations = [],
  conversation,
  isLoading,
  isSending,
  messages,
  onConfirmTool,
  focusMessageId,
  onFocusMessageDone,
  onSuggestion,
  progress,
}) {
  const listRef = useRef(null);
  const stickRef = useRef(true); // follow new content only while the user is at the bottom
  const conversationRef = useRef(null);
  const [isAtBottom, setIsAtBottom] = useState(true);

  const handleScroll = () => {
    const el = listRef.current;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    stickRef.current = atBottom;
    setIsAtBottom(atBottom);
  };

  const scrollToBottom = (smooth = false) => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    stickRef.current = true;
  };

  // Layout effect: runs before paint, so following a stream never flickers.
  useLayoutEffect(() => {
    const switched = conversationRef.current !== conversation?.id;
    conversationRef.current = conversation?.id;
    const last = messages[messages.length - 1];
    const justSent = last?.role === "user" && last?.pending;
    // Instant, not smooth: smooth scrolling lags behind a fast stream.
    if (switched || justSent || stickRef.current) scrollToBottom(false);
    // Keep the "Latest" button in sync with the REAL position after every layout:
    // the list can be re-mounted (skeleton -> list) and a freshly mounted element
    // gets no scroll event for its initial offset. Same-value setState is a no-op.
    const frame = window.requestAnimationFrame(() => listRef.current && handleScroll());
    return () => window.cancelAnimationFrame(frame);
  }, [messages, isSending, agentStatus, progress, confirmations, conversation?.id]);

  // Opened from search: centre the matching message and flash it. Declared AFTER the
  // stick-to-bottom effect so it wins on the render where the messages arrive.
  useLayoutEffect(() => {
    if (!focusMessageId) return;
    const el = listRef.current?.querySelector(`[data-message-id="${focusMessageId}"]`);
    if (!el) return; // not loaded yet: runs again when the messages arrive
    el.scrollIntoView({ block: "center" });
    stickRef.current = false; // (the effect above re-reads the position next frame)
    el.classList.add("message--flash");
    window.setTimeout(() => el.classList.remove("message--flash"), 2200);
    onFocusMessageDone?.();
  }, [focusMessageId, messages, onFocusMessageDone]);

  if (!conversation) {
    return (
      <div className="message-list message-list--empty">
        <div className="empty-state-card empty-state-card--welcome">
          <Sparkles aria-hidden="true" className="empty-state-card__icon" size={28} />
          <h2>Start a conversation</h2>
          <p>Create a new chat, or pick one from the sidebar. Search everything you've discussed with <kbd>{SHORTCUT}</kbd>.</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="message-list message-list--empty">
        <div aria-busy="true" aria-label="Loading messages" className="skeleton-chat" role="status">
          <div className="skeleton skeleton--bubble skeleton--right" />
          <div className="skeleton skeleton--line" />
          <div className="skeleton skeleton--line skeleton--short" />
          <div className="skeleton skeleton--bubble skeleton--right" />
          <div className="skeleton skeleton--line" />
        </div>
      </div>
    );
  }

  if (messages.length === 0 && !isSending) {
    return (
      <div className="message-list message-list--empty">
        <div className="empty-state-card">
          <h2>What can I help with?</h2>
          <p>Ask anything, drop files in, or type @ to pick an agent. Some ideas:</p>
          <div className="suggestions">
            {SUGGESTIONS.map(({ agent, text }) => (
              <button
                className="suggestion-chip"
                key={text}
                onClick={() => {
                  onSuggestion?.(text);
                  document.querySelector('[aria-label="Chat message input"]')?.focus();
                }}
                type="button"
              >
                {agentIcon(agent, 15)}
                <span>{text}</span>
              </button>
            ))}
          </div>
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
    <div className="message-list-wrap">
    <div className="message-list" onScroll={handleScroll} ref={listRef}>
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
              data-message-id={message.id}
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
                <span className="message-meta__end">
                  {isAssistant && !message.streaming && !message.pending && message.content ? (
                    <AnswerCopy content={message.content} />
                  ) : null}
                  {message.status === "stopped" || message.status === "interrupted" ? (
                    <span className={`message-badge message-badge--${message.status}`}>
                      {message.status === "stopped" ? "Stopped" : "Interrupted"}
                    </span>
                  ) : null}
                  <span className="message-time">{message.pending ? "Sending..." : formatTime(message.created_at)}</span>
                </span>
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
      {confirmations.map((confirmation) => (
        <ConfirmationCard agents={agents} confirmation={confirmation} key={confirmation.id} onDecide={onConfirmTool} />
      ))}

    </div>
    {isAtBottom ? null : (
      <button className="jump-to-latest button-with-icon" onClick={() => scrollToBottom(true)} type="button">
        <ArrowDown aria-hidden="true" size={15} />
        Latest
      </button>
    )}
    </div>
  );
}
