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
import { DRAFT_ID, useConversationSocket } from "../hooks/useConversationSocket";
import { useConversationUploads } from "../hooks/useConversationUploads";
import { Brain, Menu } from "lucide-react";
import SearchPalette from "../components/SearchPalette";
import Toaster from "../components/Toaster";
import { useToasts } from "../hooks/useToasts";
import { checkFiles } from "../lib/uploads";

/**
 * Saved messages from the server + what only exists locally: a draft restored from
 * turn_state (which can arrive BEFORE this fetch finishes) and messages still being
 * sent. Replacing the list wholesale used to wipe a live draft on page load.
 */
function withLocalMessages(saved, current) {
  const local = current.filter((m) => (m.id === DRAFT_ID || m.pending) && !saved.some((s) => s.id === m.id));
  return [...saved, ...local];
}

export default function ChatPage({ user, onLogout }) {
  // Pinned agent PER CONVERSATION (it used to be one global localStorage value,
  // so a pick in one chat silently disabled routing in every chat).
  const [pinnedAgentByConversation, setPinnedAgentByConversation] = useState({});
  const [isMemoryOpen, setIsMemoryOpen] = useState(false);
  // Mobile only: the conversation list is an off-canvas drawer (CSS hides the
  // toggle and keeps the sidebar visible on wide screens).
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState("");
  const [messagesByConversation, setMessagesByConversation] = useState({});
  const [isConversationListLoading, setIsConversationListLoading] =
    useState(true);
  const [messageLoadingConversationId, setMessageLoadingConversationId] =
    useState("");
  const [isCreatingConversation, setIsCreatingConversation] = useState(false);
  // Transient feedback is a toast (it used to be a banner that pushed the chat down).
  const { toasts, notify: setStatusMessage, dismiss: dismissToast } = useToasts();
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [focusMessageId, setFocusMessageId] = useState(null); // scroll to a search hit
  // Unsent text per conversation: switching chats no longer loses what you typed.
  const [composerDrafts, setComposerDrafts] = useState({});

  // ⌘K (macOS) / Ctrl+K (elsewhere) opens search from anywhere in the app.
  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); // browsers use Ctrl+K for the address bar
        setIsSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
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
      const saved = [...latest].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
      setMessagesByConversation((current) => ({
        ...current,
        [conversationId]: withLocalMessages(saved, current[conversationId] || []),
      }));
    } catch {
      // Not fatal: the next successful load will catch up.
    }
  }, []);

  const {
    agentStatus,
    confirmations,
    confirmTool,
    connectionState,
    isSending,
    progress,
    queue,
    removeQueued,
    sendMessage,
    stop,
  } = useConversationSocket({
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
        // An empty list is a STATE (the sidebar shows a hint), not an event: no toast.
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setStatusMessage(errorMessage(error, "Could not load conversations from the backend."), "error");
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
  }, [setStatusMessage]);

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

        // Merge, don't replace: turn_state may already have restored a live draft.
        setConversationMessages(selectedConversationId, (current) => withLocalMessages(sorted, current));
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setStatusMessage(
          error.response?.data?.detail ||
            "Could not load messages for the selected conversation.",
          "error"
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
  }, [selectedConversationId, setStatusMessage]);

  const handleCreateConversation = async () => {
    setIsCreatingConversation(true);

    try {
      const conversation = await createConversation(`New Chat ${conversations.length + 1}`);

      setConversations((current) => [conversation, ...current]);
      setSelectedConversationId(conversation.id);
      setStatusMessage("New conversation created.", "success");
    } catch (error) {
      setStatusMessage(
        error.response?.data?.detail ||
          "Could not create a new conversation.",
        "error"
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
      setStatusMessage(errorMessage(error, "Could not rename the conversation."), "error");
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
      setStatusMessage("Conversation deleted.", "success");
    } catch (error) {
      setStatusMessage(errorMessage(error, "Could not delete the conversation."), "error");
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
      setStatusMessage(errorMessage(error, "Could not export the conversation."), "error");
    }
  };

  const handleImportConversation = async (file) => {
    try {
      const payload = JSON.parse(await file.text());
      const result = await importConversation(payload);
      const refreshed = await fetchConversations();
      setConversations(refreshed);
      setSelectedConversationId(result.conversation_id);
      setStatusMessage(`Imported ${result.message_count} messages. Memories are being rebuilt in the background.`, "success");
    } catch (error) {
      setStatusMessage(
        error instanceof SyntaxError ? "That file is not valid JSON." : errorMessage(error, "Could not import the conversation."),
        "error"
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
      setStatusMessage("Select a conversation before uploading files.", "warning");
      return;
    }

    const { accepted, rejected } = checkFiles(files);
    const rejectedNote = rejected.length
      ? `Skipped: ${rejected.map((r) => `${r.name} (${r.reason})`).join(", ")}. `
      : "";
    if (accepted.length === 0) {
      setStatusMessage(rejectedNote, "warning");
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
      setStatusMessage(`${rejectedNote}Files uploaded. Waiting for processing to finish...`, rejectedNote ? "warning" : "info");
    } catch (error) {
      setStatusMessage(rejectedNote + errorMessage(error, "Could not upload files for this conversation."), "error");
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
      setStatusMessage("Select a conversation before sending a message.", "warning");
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
      setStatusMessage("Files processed. You can send your message now.", "success");
      return;
    }

    if (attachedFiles.some((file) => file.status === "failed")) {
      setStatusMessage("One or more files failed processing. Remove them to continue.", "error");
    }
  }, [attachedFiles, setStatusMessage]);

  return (
    <div className="app-shell">
      {isSidebarOpen ? <div aria-hidden="true" className="sidebar-backdrop" onClick={() => setIsSidebarOpen(false)} /> : null}
      <Sidebar
        isOpen={isSidebarOpen}
        user={user}
        onLogout={onLogout}
        conversations={conversations}
        isConversationListLoading={isConversationListLoading}
        isCreatingConversation={isCreatingConversation}
        onCreateConversation={async () => {
          await handleCreateConversation();
          setIsSidebarOpen(false);
        }}
        onSelectConversation={(id) => {
          setSelectedConversationId(id);
          setIsSidebarOpen(false);
        }}
        onOpenSearch={() => setIsSearchOpen(true)}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
        onExportConversation={handleExportConversation}
        onImportConversation={handleImportConversation}
        selectedConversationId={selectedConversationId}
      />

      <main className="workspace">
        <header className="workspace-header">
          <button
            aria-expanded={isSidebarOpen}
            aria-label="Open conversations"
            className="sidebar-toggle"
            onClick={() => setIsSidebarOpen(true)}
            type="button"
          >
            <Menu aria-hidden="true" size={20} />
          </button>
          <div className="workspace-header__title">
            <p className="workspace-header__label">Current Chat</p>
            <h2>{selectedConversation?.title || "No conversation selected"}</h2>
          </div>
          <div className="workspace-header__actions">
            <button className="secondary-button button-with-icon" onClick={() => setIsMemoryOpen(true)} type="button">
              <Brain aria-hidden="true" size={16} />
              Memory
            </button>
            <span className={`status-pill status-pill--${connectionState}`}>{connectionState}</span>
          </div>
        </header>

        <ChatWindow
          activeAgent={activeAgent}
          agentStatus={agentStatus}
          progress={progress}
          confirmations={confirmations}
          onConfirmTool={confirmTool}
          focusMessageId={focusMessageId}
          onFocusMessageDone={() => setFocusMessageId(null)}
          composerText={composerDrafts[selectedConversationId] || ""}
          onComposerTextChange={(value) =>
            setComposerDrafts((current) => ({ ...current, [selectedConversationId]: value }))
          }
          connectionState={connectionState}
          queue={queue}
          onRemoveQueued={removeQueued}
          onStop={stop}
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
      <Toaster onDismiss={dismissToast} toasts={toasts} />
      {isSearchOpen ? (
        <SearchPalette
          conversations={conversations}
          onClose={() => setIsSearchOpen(false)}
          onOpen={(hit) => {
            setIsSearchOpen(false);
            setIsSidebarOpen(false);
            setSelectedConversationId(hit.conversation_id);
            setFocusMessageId(hit.message_id);
          }}
        />
      ) : null}
    </div>
  );
}
