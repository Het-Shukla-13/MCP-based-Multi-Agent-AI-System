import { useRef, useState } from "react";
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
  pinnedAgent,
  onPinAgent,
}) {
  const status = agentStatus?.agent && agentStatus.agent !== "root" ? agentStatus.agent : null;
  const shownAgent = status || activeAgent;

  // Drag-and-drop anywhere on the chat. dragenter/dragleave fire for every child
  // element, so a counter (not a boolean) tracks whether we're still over the zone.
  const [isDragging, setIsDragging] = useState(false);
  const depth = useRef(0);
  const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes("Files");
  const dropHandlers = conversation
    ? {
        onDragEnter: (e) => { if (!hasFiles(e)) return; e.preventDefault(); depth.current += 1; setIsDragging(true); },
        onDragOver: (e) => { if (hasFiles(e)) e.preventDefault(); }, // required, or the browser opens the file
        onDragLeave: () => { depth.current = Math.max(0, depth.current - 1); if (!depth.current) setIsDragging(false); },
        onDrop: (e) => {
          if (!hasFiles(e)) return;
          e.preventDefault();
          depth.current = 0;
          setIsDragging(false);
          const files = Array.from(e.dataTransfer.files || []);
          if (files.length) onAttachFiles(files);
        },
      }
    : {};

  return (
    <section className={`chat-window${isDragging ? " chat-window--dragging" : ""}`} {...dropHandlers}>
      {isDragging ? <div className="drop-overlay">Drop files to attach</div> : null}
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
        pinnedAgent={pinnedAgent}
        onPinAgent={onPinAgent}
      />
    </section>
  );
}
