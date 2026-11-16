import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import { agentIcon, agentLabel as labelFor } from "../lib/agents";

export default function ChatWindow({
  activeAgent,
  agentStatus,
  agents,
  attachedFiles,
  conversation,
  isLoading,
  isSending,
  isUploading,
  messages,
  onAttachFiles,
  onClearAttachedFiles,
  onRemoveAttachedFile,
  onSend,
  sendDisabledReason,
  selectedAgent,
  onAgentSelect,
}) {
  const status = agentStatus?.agent && agentStatus.agent !== "root" ? agentStatus.agent : null;
  const shownAgent = status || activeAgent;

  return (
    <section className="chat-window">
      {/* Active agent header bar */}
      {conversation && (
        <div className="active-agent-bar">
          <span className="active-agent-indicator">
            <span className={`active-agent-dot${status ? " active-agent-dot--busy" : ""}`} />
            {agentIcon(shownAgent)} {labelFor(agents, shownAgent)}
            {status ? <span className="active-agent-state">working</span> : null}
          </span>
        </div>
      )}

      <MessageList
        agentStatus={agentStatus}
        agents={agents}
        conversation={conversation}
        isLoading={isLoading}
        isSending={isSending}
        messages={messages}
      />
      <MessageInput
        agents={agents}
        attachedFiles={attachedFiles}
        disabled={!conversation}
        isSending={isSending}
        isUploading={isUploading}
        onAttachFiles={onAttachFiles}
        onClearAttachedFiles={onClearAttachedFiles}
        onRemoveAttachedFile={onRemoveAttachedFile}
        onSend={onSend}
        sendDisabledReason={sendDisabledReason}
        selectedAgent={selectedAgent}
        onAgentSelect={onAgentSelect}
      />
    </section>
  );
}
