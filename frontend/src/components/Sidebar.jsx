function formatConversationDate(value) {
  if (!value) {
    return "New";
  }

  return new Intl.DateTimeFormat([], {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export default function Sidebar({
  user,
  onLogout,
  conversations,
  isConversationListLoading,
  isCreatingConversation,
  onCreateConversation,
  onSelectConversation,
  selectedConversationId,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar__header">
        <p className="sidebar__eyebrow">AI Chatbot</p>
        <h1>Conversations</h1>
      </div>

      <button
        className="primary-button sidebar__new-chat"
        disabled={isCreatingConversation}
        onClick={onCreateConversation}
        type="button"
      >
        {isCreatingConversation ? "Creating..." : "New Chat"}
      </button>

      <div className="conversation-list">
        {isConversationListLoading ? (
          <p className="sidebar__hint">Loading conversations...</p>
        ) : conversations.length === 0 ? (
          <p className="sidebar__hint">No conversations yet.</p>
        ) : (
          conversations.map((conversation) => (
            <button
              className={`conversation-item ${
                conversation.id === selectedConversationId
                  ? "conversation-item--active"
                  : ""
              }`}
              key={conversation.id}
              onClick={() => onSelectConversation(conversation.id)}
              type="button"
            >
              <strong>{conversation.title}</strong>
              <span>{formatConversationDate(conversation.updated_at)}</span>
            </button>
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
