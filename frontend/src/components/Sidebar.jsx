import { useRef, useState } from "react";

function formatConversationDate(value) {
  if (!value) return "New";
  return new Intl.DateTimeFormat([], { month: "short", day: "numeric" }).format(new Date(value));
}

function ConversationItem({ conversation, isActive, onSelect, onRename, onDelete, onExport }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(conversation.title);

  const save = async () => {
    setEditing(false);
    if (title.trim() && title.trim() !== conversation.title) await onRename(conversation.id, title.trim());
    else setTitle(conversation.title);
  };

  return (
    <div className={`conversation-item${isActive ? " conversation-item--active" : ""}`}>
      {editing ? (
        <input
          aria-label="Conversation title"
          autoFocus
          className="conversation-item__edit"
          maxLength={200}
          onBlur={save}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
            if (e.key === "Escape") { setTitle(conversation.title); setEditing(false); }
          }}
          value={title}
        />
      ) : (
        <button className="conversation-item__main" onClick={() => onSelect(conversation.id)} type="button">
          <strong>{conversation.title}</strong>
          <span>{formatConversationDate(conversation.updated_at)}</span>
        </button>
      )}
      <div className="conversation-item__actions">
        <button aria-label="Rename" onClick={() => setEditing(true)} title="Rename" type="button">✎</button>
        <button aria-label="Export" onClick={() => onExport(conversation)} title="Export as JSON" type="button">⤓</button>
        <button
          aria-label="Delete"
          onClick={() => window.confirm(`Delete "${conversation.title}" and its messages and files?`) && onDelete(conversation.id)}
          title="Delete"
          type="button"
        >
          🗑
        </button>
      </div>
    </div>
  );
}

export default function Sidebar({
  isOpen,
  user,
  onLogout,
  conversations,
  isConversationListLoading,
  isCreatingConversation,
  onCreateConversation,
  onSelectConversation,
  onRenameConversation,
  onDeleteConversation,
  onExportConversation,
  onImportConversation,
  selectedConversationId,
}) {
  const importRef = useRef(null);

  return (
    <aside className={`sidebar${isOpen ? " sidebar--open" : ""}`}>
      <div className="sidebar__header">
        <p className="sidebar__eyebrow">Multi-Agent Assistant</p>
        <h1>Conversations</h1>
      </div>

      <div className="sidebar__buttons">
        <button className="primary-button sidebar__new-chat" disabled={isCreatingConversation} onClick={onCreateConversation} type="button">
          {isCreatingConversation ? "Creating..." : "New Chat"}
        </button>
        <button className="secondary-button" onClick={() => importRef.current?.click()} title="Import an exported conversation" type="button">
          Import
        </button>
        <input
          accept="application/json,.json"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) onImportConversation(file);
          }}
          ref={importRef}
          type="file"
        />
      </div>

      <div className="conversation-list">
        {isConversationListLoading ? (
          <p className="sidebar__hint">Loading conversations...</p>
        ) : conversations.length === 0 ? (
          <p className="sidebar__hint">No conversations yet.</p>
        ) : (
          conversations.map((conversation) => (
            <ConversationItem
              conversation={conversation}
              isActive={conversation.id === selectedConversationId}
              key={conversation.id}
              onDelete={onDeleteConversation}
              onExport={onExportConversation}
              onRename={onRenameConversation}
              onSelect={onSelectConversation}
            />
          ))
        )}
      </div>

      <div className="sidebar__account">
        <span className="sidebar__email" title={user?.email}>{user?.email}</span>
        <button className="link-button" onClick={onLogout} type="button">Sign out</button>
      </div>
    </aside>
  );
}
