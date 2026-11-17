import { useEffect, useRef, useState } from "react";
import { agentIcon, agentLabel } from "../lib/agents";
import { ACCEPT_ATTRIBUTE } from "../lib/uploads";

const FILE_FORMATS = [
  { value: "", label: "Reply in chat" },
  { value: "pdf", label: "Reply as PDF" },
  { value: "md", label: "Reply as Markdown" },
  { value: "txt", label: "Reply as text file" },
  { value: "csv", label: "Reply as CSV" },
  { value: "json", label: "Reply as JSON" },
];

/**
 * Find an "@word" being typed right before the cursor. Only counts when the "@" is
 * at the start or after whitespace, so e-mail addresses ("me@code.dev") don't open
 * the agent menu (the backend's mention parser uses the same rule).
 */
function findMention(value, cursor) {
  const match = /(^|\s)@([a-z_]*)$/i.exec(value.slice(0, cursor));
  return match ? { query: match[2].toLowerCase(), start: cursor - match[2].length - 1 } : null;
}

export default function MessageInput({
  agents,
  attachedFiles,
  disabled,
  isSending,
  isUploading,
  onAttachFiles,
  onClearAttachedFiles,
  onRemoveAttachedFile,
  onSend,
  sendDisabledReason,
  pinnedAgent,
  onPinAgent,
}) {
  const [text, setText] = useState("");
  const [mention, setMention] = useState(null); // {query, start} | null
  const [highlighted, setHighlighted] = useState(0);
  const [format, setFormat] = useState("");
  const textareaRef = useRef(null);
  const menuRef = useRef(null);

  const isSendBlocked = disabled || isSending || isUploading || !text.trim() || Boolean(sendDisabledReason);
  const suggestions = mention ? agents.filter((a) => a.name.startsWith(mention.query)) : [];

  const submit = async () => {
    const content = text.trim();
    if (!content || isSendBlocked) return;
    const sent = await onSend({ content, fileIds: attachedFiles.map((f) => f.id), format: format || null });
    if (sent === false) return;
    setText("");
    setFormat("");
    onClearAttachedFiles();
  };

  const handleChange = (event) => {
    setText(event.target.value);
    setMention(findMention(event.target.value, event.target.selectionStart));
    setHighlighted(0);
  };

  // Picking an agent INSERTS "@name " into the message (visible, editable). The
  // backend routes on typed mentions, so the text is the single source of truth.
  const insertMention = (agent) => {
    if (!mention) return;
    const cursor = mention.start + 1 + mention.query.length;
    const next = `${text.slice(0, mention.start)}@${agent.name} ${text.slice(cursor)}`;
    setText(next);
    setMention(null);
    requestAnimationFrame(() => {
      const position = mention.start + agent.name.length + 2;
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(position, position);
    });
  };

  const handleKeyDown = (event) => {
    if (suggestions.length > 0) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        setHighlighted((i) => (i + step + suggestions.length) % suggestions.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        insertMention(suggestions[highlighted]);
        return;
      }
      if (event.key === "Escape") {
        setMention(null);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  const handleFileChange = async (event) => {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (files.length) await onAttachFiles(files);
  };

  useEffect(() => {
    const close = (e) => {
      if (!menuRef.current?.contains(e.target) && !textareaRef.current?.contains(e.target)) setMention(null);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const inputDisabled = disabled || isSending || isUploading;

  return (
    <div className="composer-shell">
      <div className="composer-toolbar">
        <label className="composer-select">
          <span>Agent</span>
          <select disabled={disabled} onChange={(e) => onPinAgent(e.target.value || null)} value={pinnedAgent || ""}>
            <option value="">Auto (router picks)</option>
            {agents.map((a) => (
              <option key={a.name} value={a.name}>{agentLabel(agents, a.name)}</option>
            ))}
          </select>
        </label>
        <label className="composer-select">
          <span>Output</span>
          <select disabled={disabled} onChange={(e) => setFormat(e.target.value)} value={format}>
            {FILE_FORMATS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </label>
      </div>

      {suggestions.length > 0 ? (
        <div aria-label="Agent suggestions" className="mention-dropdown" ref={menuRef} role="listbox">
          {suggestions.map((agent, idx) => (
            <button
              aria-selected={idx === highlighted}
              className={`mention-option${idx === highlighted ? " mention-option--highlighted" : ""}`}
              key={agent.name}
              onMouseDown={(e) => { e.preventDefault(); insertMention(agent); }}
              onMouseEnter={() => setHighlighted(idx)}
              role="option"
              type="button"
            >
              <span className="mention-option__icon">{agentIcon(agent.name)}</span>
              <span className="mention-option__name">@{agent.name}</span>
              <span className="mention-option__desc">{agent.description}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="composer">
        <div className="composer-main">
          {attachedFiles.length > 0 ? (
            <div className="composer-files">
              {attachedFiles.map((file) => (
                <div className="composer-file-chip" key={file.id}>
                  <span>{file.filename}</span>
                  <span className={`composer-file-status composer-file-status--${file.status}`}>{file.status}</span>
                  <button className="composer-file-remove" disabled={inputDisabled} onClick={() => onRemoveAttachedFile(file.id)} type="button">
                    Remove
                  </button>
                </div>
              ))}
            </div>
          ) : null}

          <textarea
            aria-autocomplete="list"
            aria-label="Chat message input"
            className="composer-input"
            disabled={inputDisabled}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? "Select or create a conversation" : "Message... (@ to mention an agent, drop files anywhere)"}
            ref={textareaRef}
            rows={2}
            value={text}
          />
          {sendDisabledReason ? <p className="composer-help-text">{sendDisabledReason}</p> : null}
          <div className="composer-actions">
            <label className="secondary-button composer-upload-button">
              <input accept={ACCEPT_ATTRIBUTE} className="composer-file-input" disabled={inputDisabled} multiple onChange={handleFileChange} type="file" />
              Add files
            </label>
          </div>
        </div>
        <button className="primary-button" disabled={isSendBlocked} onClick={() => void submit()} type="button">
          {isUploading ? "Uploading..." : isSending ? "Sending..." : "Send"}
        </button>
      </div>
    </div>
  );
}
