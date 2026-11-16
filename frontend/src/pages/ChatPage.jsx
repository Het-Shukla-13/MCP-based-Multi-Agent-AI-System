import { useCallback, useEffect, useMemo, useState } from "react";
import ChatWindow from "../components/ChatWindow";
import Sidebar from "../components/Sidebar";
import MemoryPanel from "../components/MemoryPanel";
import {
  createConversation,
  deleteConversation,
  errorMessage,
  exportConversation,
  importConversation,
  renameConversation,
  fetchAgents,
  fetchConversations,
  fetchConversationFiles,
  fetchMessages,
} from "../lib/api";
import { useConversationSocket } from "../hooks/useConversationSocket";
import { useConversationUploads } from "../hooks/useConversationUploads";
import { checkFiles } from "../lib/uploads";

export default function ChatPage({ user, onLogout }) {
  // Pinned agent PER CONVERSATION (it used to be one global localStorage value,
  // so a pick in one chat silently disabled routing in every chat).
  const [pinnedAgentByConversation, setPinnedAgentByConversation] = useState({});
  const [isMemoryOpen, setIsMemoryOpen] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [messagesByConversation, setMessagesByConversation] = useState({});
  const [isConversationListLoading, setIsConversationListLoading] =
    useState(true);
  const [messageLoadingConversationId, setMessageLoadingConversationId] =
    useState("");
  const [isCreatingConversation, setIsCreatingConversation] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Loading conversations...");
  const [draftFilesByConversation, setDraftFilesByConversation] = useState({});
  // Agents fetched from /ws/agents on mount
  const [agents, setAgents] = useState([]);

  const selectedConversation = useMemo(
    () =>
      conversations.find((conversation) => conversation.id === selectedConversationId) ||
      null,
    [conversations, selectedConversationId]
  );

  const messages = useMemo(
    () => (selectedConversationId ? messagesByConversation[selectedConversationId] || [] : []),
    [messagesByConversation, selectedConversationId]
  );

  const isLoadingMessages =
    !!selectedConversationId &&
    messageLoadingConversationId === selectedConversationId;

  const setConversationMessages = (conversationId, updater) => {
    setMessagesByConversation((current) => {
      const previousMessages = current[conversationId] || [];
      const nextMessages =
        typeof updater === "function" ? updater(previousMessages) : updater;

      return {
        ...current,
        [conversationId]: nextMessages,
      };
    });
  };

  const pinnedAgent = pinnedAgentByConversation[selectedConversationId] || null;

  // After a reconnect, reload the conversation from the server: a reply that
  // finished while we were offline would otherwise never appear.
  const resyncConversation = useCallback(async (conversationId) => {
    try {
      const latest = await fetchMessages(conversationId);
      setMessagesByConversation((current) => ({
        ...current,
        [conversationId]: [...latest].sort((a, b) => new Date(a.created_at) - new Date(b.created_at)),
      }));
    } catch {
      // Not fatal: the next successful load will catch up.
    }
  }, []);

  const { agentStatus, connectionState, isSending, sendMessage } = useConversationSocket({
    selectedAgent: pinnedAgent,
    selectedConversationId,
    setMessagesByConversation,
    setStatusMessage,
    onResync: resyncConversation,
  });

  // Derived, not stored: the agent that wrote the latest reply, else the saved state.
  const activeAgent = useMemo(() => {
    const lastReply = [...messages].reverse().find((m) => m.role === "assistant" && m.agent_name);
    return lastReply?.agent_name || selectedConversation?.convo_metadata?.agent_state?.active_agent || "general";
  }, [messages, selectedConversation]);

  // Fetch agents list from the backend on mount
  useEffect(() => {
    fetchAgents()
      .then(setAgents)
      .catch(() => {
        // Fall back to a hardcoded list if the endpoint isn't reachable yet
        setAgents([
          { name: "general",  label: "General Assistant", description: "Default conversational agent" },
          { name: "code",     label: "Code Agent",         description: "Code analysis and generation" },
          { name: "data",     label: "Data Agent",         description: "CSV / Excel analysis" },
          { name: "research", label: "Research Agent",     description: "Web search and synthesis" },
          { name: "document", label: "Document Agent",     description: "PDF / DOCX analysis" },
          { name: "image",    label: "Image Agent",        description: "Image understanding and generation" },
        ]);
      });
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function loadConversations() {
      setIsConversationListLoading(true);

      try {
        const data = await fetchConversations();
        if (!isMounted) {
          return;
        }

        const sorted = [...data].sort(
          (left, right) =>
            new Date(right.updated_at).getTime() -
            new Date(left.updated_at).getTime()
        );

        setConversations(sorted);
        setSelectedConversationId(sorted[0]?.id || "");
        setStatusMessage(
          sorted.length > 0
            ? "Conversations loaded."
            : "No conversations yet. Start a new chat."
        );
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setStatusMessage(errorMessage(error, "Could not load conversations from the backend."));
      } finally {
        if (isMounted) {
          setIsConversationListLoading(false);
        }
      }
    }

    loadConversations();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedConversationId) {
      return;
    }

    let isMounted = true;

    async function loadMessages() {
      setMessageLoadingConversationId(selectedConversationId);

      try {
        const data = await fetchMessages(selectedConversationId);
        if (!isMounted) {
          return;
        }

        const sorted = [...data].sort(
          (left, right) =>
            new Date(left.created_at).getTime() -
            new Date(right.created_at).getTime()
        );

        setConversationMessages(selectedConversationId, sorted);
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setStatusMessage(
          error.response?.data?.detail ||
            "Could not load messages for the selected conversation."
        );
      } finally {
        if (isMounted) {
          setMessageLoadingConversationId("");
        }
      }
    }

    loadMessages();

    return () => {
      isMounted = false;
    };
  }, [selectedConversationId]);

  const handleCreateConversation = async () => {
    setIsCreatingConversation(true);

    try {
      const conversation = await createConversation(`New Chat ${conversations.length + 1}`);

      setConversations((current) => [conversation, ...current]);
      setSelectedConversationId(conversation.id);
      setStatusMessage("New conversation created.");
    } catch (error) {
      setStatusMessage(
        error.response?.data?.detail ||
          "Could not create a new conversation."
      );
    } finally {
      setIsCreatingConversation(false);
    }
  };

  const handleRenameConversation = async (conversationId, title) => {
    try {
      const updated = await renameConversation(conversationId, title);
      setConversations((current) => current.map((c) => (c.id === conversationId ? { ...c, title: updated.title } : c)));
    } catch (error) {
      setStatusMessage(errorMessage(error, "Could not rename the conversation."));
    }
  };

  const handleDeleteConversation = async (conversationId) => {
    try {
      await deleteConversation(conversationId);
      const remaining = conversations.filter((c) => c.id !== conversationId);
      setConversations(remaining);
      setMessagesByConversation((current) => {
        const next = { ...current };
        delete next[conversationId];
        return next;
      });
      if (conversationId === selectedConversationId) setSelectedConversationId(remaining[0]?.id || "");
      setStatusMessage("Conversation deleted.");
    } catch (error) {
      setStatusMessage(errorMessage(error, "Could not delete the conversation."));
    }
  };

  const handleExportConversation = async (conversation) => {
    try {
      const data = await exportConversation(conversation.id);
      // Build the file in the browser and "click" a temporary link to download it.
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = Object.assign(document.createElement("a"), {
        href: url,
        download: `${conversation.title.replace(/[^\w-]+/g, "_") || "conversation"}.json`,
      });
      link.click();
      URL.revokeObjectURL(url); // free the in-memory file
    } catch (error) {
      setStatusMessage(errorMessage(error, "Could not export the conversation."));
    }
  };

  const handleImportConversation = async (file) => {
    try {
      const payload = JSON.parse(await file.text());
      const result = await importConversation(payload);
      const refreshed = await fetchConversations();
      setConversations(refreshed);
      setSelectedConversationId(result.conversation_id);
      setStatusMessage(`Imported ${result.message_count} messages. Memories are being rebuilt in the background.`);
    } catch (error) {
      setStatusMessage(
        error instanceof SyntaxError ? "That file is not valid JSON." : errorMessage(error, "Could not import the conversation.")
      );
    }
  };

  const mergeConversationFiles = (conversationId, uploadedFiles) => {
    setConversations((current) =>
      current.map((conversation) => {
        if (conversation.id !== conversationId) {
          return conversation;
        }

        const existingFiles = conversation.files || [];
        const nextFilesById = new Map(
          existingFiles.map((file) => [file.id, file])
        );

        uploadedFiles.forEach((file) => {
          nextFilesById.set(file.id, file);
        });

        return {
          ...conversation,
          files: Array.from(nextFilesById.values()),
        };
      })
    );
  };

  const { isUploadingFiles, uploadFiles } = useConversationUploads({
    mergeConversationFiles,
    setStatusMessage,
  });

  const hasPendingConversationFiles = useMemo(
    () =>
      (selectedConversation?.files || []).some(
        (file) => file.status !== "processed" && file.status !== "failed"
      ),
    [selectedConversation?.files]
  );

  const setDraftFiles = (conversationId, updater) => {
    setDraftFilesByConversation((current) => {
      const previousFiles = current[conversationId] || [];
      const nextFiles =
        typeof updater === "function" ? updater(previousFiles) : updater;

      return {
        ...current,
        [conversationId]: nextFiles,
      };
    });
  };

  useEffect(() => {
    if (!selectedConversationId) {
      return;
    }

    if (!hasPendingConversationFiles) {
      return;
    }

    let isActive = true;
    let timeoutId = null;
    let attempt = 0;

    const pollStatuses = async () => {
      try {
        const latestFiles = await fetchConversationFiles(selectedConversationId);
        if (!isActive) {
          return;
        }

        mergeConversationFiles(selectedConversationId, latestFiles);
        attempt = 0;
      } catch (error) {
        if (!isActive) {
          return;
        }

        attempt += 1;
        console.error("Failed to refresh file statuses", error);
      }

      if (!isActive) {
        return;
      }

      const nextDelay = Math.min(1000 * 2 ** attempt, 5000);
      timeoutId = window.setTimeout(() => {
        void pollStatuses();
      }, nextDelay);
    };

    void pollStatuses();

    return () => {
      isActive = false;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [hasPendingConversationFiles, selectedConversationId]);

  const handleAttachFiles = async (files) => {
    if (!selectedConversationId) {
      setStatusMessage("Select a conversation before uploading files.");
      return;
    }

    const { accepted, rejected } = checkFiles(files);
    const rejectedNote = rejected.length
      ? `Skipped: ${rejected.map((r) => `${r.name} (${r.reason})`).join(", ")}. `
      : "";
    if (accepted.length === 0) {
      setStatusMessage(rejectedNote);
      return;
    }

    try {
      const uploadedFiles = await uploadFiles({
        conversationId: selectedConversationId,
        files: accepted,
      });
      setDraftFiles(selectedConversationId, (currentFiles) => [
        ...currentFiles,
        ...uploadedFiles.filter(
          (file) => !currentFiles.some((currentFile) => currentFile.id === file.id)
        ),
      ]);
      setStatusMessage(`${rejectedNote}Files uploaded. Waiting for processing to finish...`);
    } catch (error) {
      setStatusMessage(rejectedNote + errorMessage(error, "Could not upload files for this conversation."));
    }
  };

  const handleRemoveAttachedFile = (fileId) => {
    if (!selectedConversationId) {
      return;
    }

    setDraftFiles(selectedConversationId, (currentFiles) =>
      currentFiles.filter((file) => file.id !== fileId)
    );
  };

  const handleClearAttachedFiles = () => {
    if (!selectedConversationId) {
      return;
    }

    setDraftFiles(selectedConversationId, []);
  };

  const handleSendMessage = async ({ content, fileIds, format }) => {
    if (!selectedConversationId) {
      setStatusMessage("Select a conversation before sending a message.");
      return false;
    }
    return sendMessage(content, fileIds, { format });
  };

  const handlePinAgent = (agentName) => {
    setPinnedAgentByConversation((current) => ({ ...current, [selectedConversationId]: agentName || null }));
  };


  const attachedFiles = useMemo(() => {
    if (!selectedConversationId) {
      return [];
    }

    const conversationFiles = selectedConversation?.files || [];
    const conversationFileMap = new Map(
      conversationFiles.map((file) => [file.id, file])
    );

    return (draftFilesByConversation[selectedConversationId] || []).map(
      (file) => conversationFileMap.get(file.id) || file
    );
  }, [draftFilesByConversation, selectedConversation, selectedConversationId]);

  const sendDisabledReason = useMemo(() => {
    if (attachedFiles.some((file) => file.status === "failed")) {
      return "Remove failed files before sending.";
    }

    if (
      attachedFiles.some(
        (file) => file.status !== "processed" && file.status !== "failed"
      )
    ) {
      return "Files are still being processed. Send will unlock automatically.";
    }

    return "";
  }, [attachedFiles]);

  useEffect(() => {
    if (attachedFiles.length === 0) {
      return;
    }

    if (attachedFiles.every((file) => file.status === "processed")) {
      setStatusMessage("Files processed. You can send your message now.");
      return;
    }

    if (attachedFiles.some((file) => file.status === "failed")) {
      setStatusMessage("One or more files failed processing. Remove them to continue.");
    }
  }, [attachedFiles]);

  return (
    <div className="app-shell">
      <Sidebar
        user={user}
        onLogout={onLogout}
        conversations={conversations}
        isConversationListLoading={isConversationListLoading}
        isCreatingConversation={isCreatingConversation}
        onCreateConversation={handleCreateConversation}
        onSelectConversation={setSelectedConversationId}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
        onExportConversation={handleExportConversation}
        onImportConversation={handleImportConversation}
        selectedConversationId={selectedConversationId}
      />

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <p className="workspace-header__label">Current Chat</p>
            <h2>{selectedConversation?.title || "No conversation selected"}</h2>
          </div>
          <div className="workspace-header__actions">
            <button className="secondary-button" onClick={() => setIsMemoryOpen(true)} type="button">🧠 Memory</button>
            <span className={`status-pill status-pill--${connectionState}`}>{connectionState}</span>
          </div>
        </header>

        <div className="status-banner">{statusMessage}</div>

        <ChatWindow
          activeAgent={activeAgent}
          agentStatus={agentStatus}
          agents={agents}
          attachedFiles={attachedFiles}
          conversation={selectedConversation}
          isLoading={isLoadingMessages}
          isSending={isSending}
          isUploading={isUploadingFiles}
          messages={messages}
          onAttachFiles={handleAttachFiles}
          onClearAttachedFiles={handleClearAttachedFiles}
          onRemoveAttachedFile={handleRemoveAttachedFile}
          onSend={handleSendMessage}
          onPinAgent={handlePinAgent}
          pinnedAgent={pinnedAgent}
          sendDisabledReason={sendDisabledReason}
        />
      </main>
      {isMemoryOpen ? <MemoryPanel onClose={() => setIsMemoryOpen(false)} /> : null}
    </div>
  );
}
