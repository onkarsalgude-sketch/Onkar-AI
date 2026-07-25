import {
  useEffect,
  useRef,
  useState,
} from "react";

import Message from "./Message";
import {
  resolveAgentBadge,
} from "../../utils/agentChat";
import MessageInput from "./MessageInput";
import Thinking from "./Thinking";
import BranchExplorer from "./BranchExplorer";
import WorkspaceWelcome from "../Workspace/WorkspaceWelcome";
import DocumentLibrary from "../Documents/DocumentLibrary";
import {
  FiBell,
  FiBookmark,
  FiMenu,
  FiMoreHorizontal,
  FiSearch,
  FiShare2,
  FiUser,
} from "react-icons/fi";


function ChatWindow({
  activeChatId,
  chats = [],
  selectChat,
  onMergeCompleted,
  documentRefreshKey,
  messages,
  input,
  setInput,
  sendMessage,
  loading,
  agents = [],
  agentsLoading = false,
  agentsAvailable = false,
  selectedAgentId = "",
  onAgentChange,
  uploadFile,
  pendingFiles,
  removePendingFileAt,
  clearAllPendingFiles,
  uploadProgress,
  uploadSummary,
   dismissUploadSummary,
  regenerateResponse,

 onEditMessage,
onDeleteMessage,
onRegenerateMessage,
onCreateConversationBranch,
onSaveMessageBookmark,
onRemoveMessageBookmark,
messageActionLoadingId = null,

  onOpenSidebar,
  theme = "dark",

  messageSearchTarget = null,

  chatError = null,
  retryLastRequest,
  dismissChatError,
}) {
  const [isDragging, setIsDragging] =
    useState(false);

  const [highlightedMessageId, setHighlightedMessageId] =
    useState(null);

  const [
    workspacePanel,
    setWorkspacePanel,
  ] = useState(null);

  const [isOnline, setIsOnline] =
    useState(() => {
      if (
        typeof navigator ===
        "undefined"
      ) {
        return true;
      }

      return navigator.onLine;
    });

  const dragCounter = useRef(0);
  const messagesEndRef = useRef(null);
  const messageRefs = useRef(
    new Map()
  );
  const highlightTimerRef =
    useRef(null);

  const isDark = theme === "dark";

  const activeChat =
    chats.find(
      (chat) =>
        Number(chat?.id) ===
        Number(activeChatId)
    ) || null;

  const workspaceBranchCount =
    Math.max(
      0,
      Number(
        activeChat?.branch_count
      ) || 0
    );

  const targetMessageId =
    Number(
      messageSearchTarget?.messageId
    ) || null;

  const targetRequestId =
    messageSearchTarget?.requestId ||
    null;


  useEffect(() => {
    if (targetMessageId) {
      return;
    }

    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [
    messages,
    loading,
    chatError,
    targetMessageId,
  ]);


  useEffect(() => {
    if (!targetMessageId) {
      setHighlightedMessageId(null);
      return undefined;
    }

    const targetElement =
      messageRefs.current.get(
        targetMessageId
      );

    if (!targetElement) {
      return undefined;
    }

    const scrollTimer =
      window.setTimeout(() => {
        targetElement.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });

        setHighlightedMessageId(
          targetMessageId
        );

        if (
          highlightTimerRef.current
        ) {
          window.clearTimeout(
            highlightTimerRef.current
          );
        }

        highlightTimerRef.current =
          window.setTimeout(() => {
            setHighlightedMessageId(
              null
            );
          }, 2800);
      }, 120);

    return () => {
      window.clearTimeout(
        scrollTimer
      );
    };
  }, [
    activeChatId,
    messages,
    targetMessageId,
    targetRequestId,
  ]);


  useEffect(() => {
    return () => {
      if (
        highlightTimerRef.current
      ) {
        window.clearTimeout(
          highlightTimerRef.current
        );
      }
    };
  }, []);


  useEffect(() => {
    function handleOnline() {
      setIsOnline(true);
    }

    function handleOffline() {
      setIsOnline(false);
    }

    window.addEventListener(
      "online",
      handleOnline
    );

    window.addEventListener(
      "offline",
      handleOffline
    );

    return () => {
      window.removeEventListener(
        "online",
        handleOnline
      );

      window.removeEventListener(
        "offline",
        handleOffline
      );
    };
  }, []);


  useEffect(() => {
    function handleWorkspacePanel(
      event
    ) {
      const panel =
        event?.detail?.panel;

      if (
        panel === "branches" ||
        panel === "knowledge"
      ) {
        setWorkspacePanel(panel);
      }
    }

    window.addEventListener(
      "onkar-ai:open-workspace-panel",
      handleWorkspacePanel
    );

    return () => {
      window.removeEventListener(
        "onkar-ai:open-workspace-panel",
        handleWorkspacePanel
      );
    };
  }, []);


  useEffect(() => {
    function handleWorkspaceShortcut(
      event
    ) {
      if (
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "k"
      ) {
        event.preventDefault();
        onOpenSidebar?.();
      }
    }

    window.addEventListener(
      "keydown",
      handleWorkspaceShortcut
    );

    return () => {
      window.removeEventListener(
        "keydown",
        handleWorkspaceShortcut
      );
    };
  }, [onOpenSidebar]);


  function registerMessageRef(
    messageId,
    element
  ) {
    const numericMessageId =
      Number(messageId);

    if (!numericMessageId) {
      return;
    }

    if (element) {
      messageRefs.current.set(
        numericMessageId,
        element
      );
      return;
    }

    messageRefs.current.delete(
      numericMessageId
    );
  }


  function handleDragEnter(event) {
    event.preventDefault();
    event.stopPropagation();

    dragCounter.current += 1;

    if (
      event.dataTransfer?.items
        ?.length > 0
    ) {
      setIsDragging(true);
    }
  }


  function handleDragOver(event) {
    event.preventDefault();
    event.stopPropagation();

    event.dataTransfer.dropEffect =
      "copy";
  }


  function handleDragLeave(event) {
    event.preventDefault();
    event.stopPropagation();

    dragCounter.current -= 1;

    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragging(false);
    }
  }


  async function handleDrop(event) {
    event.preventDefault();
    event.stopPropagation();

    dragCounter.current = 0;
    setIsDragging(false);

    if (loading) return;

    if (!isOnline) {
      alert(
        "You are offline. Please reconnect and try again."
      );

      return;
    }

    const files =
      event.dataTransfer?.files;

    if (
      !files ||
      files.length === 0
    ) {
      return;
    }

    await uploadFile({
      target: {
        files,
        value: "",
      },
    });
  }


  async function handleRetry() {
    if (
      loading ||
      !isOnline ||
      !retryLastRequest
    ) {
      return;
    }

    await retryLastRequest();
  }


  const errorTitle =
    chatError?.title ||
    "Something went wrong";

  const errorMessage =
    chatError?.message ||
    "The request could not be completed.";

  const canRetry =
    chatError?.canRetry !== false &&
    typeof retryLastRequest ===
      "function";


  return (
    <main
      data-workspace-chat="primary"
      className={`relative flex h-full min-w-0 flex-1 flex-col transition-colors duration-300 ${
        isDark
          ? "bg-[#0f172a] text-white"
          : "bg-slate-100 text-slate-900"
      }`}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div
          className={`pointer-events-none absolute inset-0 z-50 flex items-center justify-center px-4 backdrop-blur-sm ${
            isDark
              ? "bg-slate-950/80"
              : "bg-slate-200/80"
          }`}
        >
          <div
            className={`w-full max-w-md rounded-2xl border-2 border-dashed border-blue-500 px-6 py-10 text-center shadow-2xl sm:px-12 ${
              isDark
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-900"
            }`}
          >
            <div className="mb-4 text-5xl">
              📎
            </div>

            <h3 className="text-xl font-semibold">
              Drop your file here
            </h3>

            <p className="mt-2 text-sm text-slate-500">
              PDF and image files are
              supported
            </p>
          </div>
        </div>
      )}

      <header
        data-workspace-topbar="v2.40"
        className={`flex h-16 shrink-0 items-center justify-between gap-3 border-b px-3 sm:px-5 md:px-6 ${
          isDark
            ? "border-white/10 bg-[#0b1020]/95"
            : "border-slate-200 bg-white/95"
        }`}
      >
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onOpenSidebar}
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition md:hidden ${
              isDark
                ? "text-slate-300 hover:bg-white/[0.06] hover:text-white"
                : "text-slate-600 hover:bg-slate-100"
            }`}
            aria-label="Open sidebar"
          >
            <FiMenu
              aria-hidden="true"
              size={18}
            />
          </button>

          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">
              {activeChat?.title ||
                "Onkar-AI Workspace"}
            </p>

            <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-500">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isOnline
                    ? "bg-emerald-500"
                    : "bg-red-500"
                }`}
              />
              {isOnline
                ? "Online"
                : "Offline"}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={onOpenSidebar}
            className={`hidden h-9 min-w-0 items-center gap-2 rounded-xl border px-3 text-left text-xs transition sm:flex md:w-64 lg:w-80 ${
              isDark
                ? "border-white/10 bg-white/[0.035] text-slate-400 hover:border-white/15 hover:bg-white/[0.06]"
                : "border-slate-200 bg-slate-50 text-slate-500 hover:bg-slate-100"
            }`}
            title="Open workspace search"
            aria-label="Open workspace search"
          >
            <FiSearch
              aria-hidden="true"
              size={15}
            />

            <span className="min-w-0 flex-1 truncate">
              Search chats & bookmarks...
            </span>

            <kbd
              className={`rounded-md border px-1.5 py-0.5 text-[10px] ${
                isDark
                  ? "border-white/10 bg-slate-950/70 text-slate-500"
                  : "border-slate-200 bg-white text-slate-500"
              }`}
            >
              Ctrl K
            </kbd>
          </button>

          <button
            type="button"
            disabled
            title="Notifications are not available yet"
            aria-label="Notifications are not available yet"
            className={`flex h-9 w-9 cursor-not-allowed items-center justify-center rounded-xl border opacity-55 ${
              isDark
                ? "border-white/10 text-slate-400"
                : "border-slate-200 text-slate-500"
            }`}
          >
            <FiBell
              aria-hidden="true"
              size={16}
            />
          </button>

          <button
            type="button"
            disabled
            title="Profile is not available yet"
            aria-label="Profile is not available yet"
            className="flex h-9 w-9 cursor-not-allowed items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-fuchsia-600 text-white opacity-75"
          >
            <FiUser
              aria-hidden="true"
              size={15}
            />
          </button>
        </div>
      </header>

      {workspacePanel && (
        <div
          data-workspace-tool-overlay={
            workspacePanel
          }
          className="absolute inset-x-3 top-[72px] z-40 max-h-[calc(100%-88px)] overflow-hidden rounded-2xl border border-white/10 bg-[#080d19]/98 shadow-2xl shadow-black/50 backdrop-blur-xl sm:inset-x-5 md:inset-x-6"
        >
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div>
              <p className="text-sm font-semibold">
                {workspacePanel ===
                "branches"
                  ? "Chat Branches"
                  : "Knowledge Base"}
              </p>

              <p className="mt-0.5 text-[11px] text-slate-500">
                {workspacePanel ===
                "branches"
                  ? "Explore and manage the real branch tree."
                  : "Manage the real PDF and RAG tools for this chat."}
              </p>
            </div>

            <button
              type="button"
              onClick={() =>
                setWorkspacePanel(null)
              }
              className="rounded-lg px-3 py-1.5 text-sm text-slate-400 transition hover:bg-white/[0.06] hover:text-white"
              aria-label="Close workspace tool"
            >
              Close
            </button>
          </div>

          <div className="max-h-[calc(100vh-190px)] overflow-y-auto">
            {workspacePanel ===
            "branches" ? (
              <div
                id="workspace-branch-explorer"
                data-workspace-feature="branches"
              >
                <BranchExplorer
                  chats={chats}
                  activeChatId={
                    activeChatId
                  }
                  onSelectChat={
                    selectChat
                  }
                  onMergeCompleted={
                    onMergeCompleted
                  }
                  theme={theme}
                />
              </div>
            ) : (
              <div
                id="workspace-document-library"
                data-workspace-feature="knowledge"
              >
                <DocumentLibrary
                  activeChatId={
                    activeChatId
                  }
                  refreshKey={
                    documentRefreshKey
                  }
                  theme={theme}
                />
              </div>
            )}
          </div>
        </div>
      )}

      <div
        data-workspace-command-deck="v2.40"
        className={`shrink-0 border-b px-3 sm:px-5 md:px-6 ${
          isDark
            ? "border-white/10 bg-[#0f172a]/98"
            : "border-slate-200 bg-slate-100/98"
        }`}
      >
        <div className="mx-auto max-w-5xl">
          <WorkspaceWelcome
            setInput={setInput}
            activeChatId={activeChatId}
            branchCount={
              workspaceBranchCount
            }
            onOpenKnowledge={() =>
              setWorkspacePanel(
                "knowledge"
              )
            }
            onOpenBranches={() =>
              setWorkspacePanel(
                "branches"
              )
            }
            onOpenSidebar={
              onOpenSidebar
            }
            showGreetingActions
            showBottomCards={false}
            theme={theme}
          />
        </div>
      </div>

      <section
        data-chat-canvas="v2.40"
        className="flex-1 overflow-y-auto px-3 py-3 sm:px-5 md:px-6 md:py-4"
      >
        <div className="mx-auto max-w-5xl">

          {activeChatId &&
            messages.length > 0 && (
            <div
              data-chat-thread-header="live"
              className={`mb-3 flex items-center justify-between gap-3 rounded-t-2xl border px-4 py-3 ${
                isDark
                  ? "border-white/10 bg-[#0b1020]/90"
                  : "border-slate-200 bg-white"
              }`}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-semibold">
                    {activeChat?.title ||
                      "Current conversation"}
                  </p>

                  {activeChat?.is_pinned && (
                    <span
                      className="text-amber-400"
                      title="Pinned chat"
                      aria-label="Pinned chat"
                    >
                      ★
                    </span>
                  )}
                </div>

                <p className="mt-0.5 text-[11px] text-slate-500">
                  {workspaceBranchCount > 0
                    ? `${workspaceBranchCount} ${
                        workspaceBranchCount === 1
                          ? "branch"
                          : "branches"
                      }`
                    : "Onkar-AI conversation"}
                </p>
              </div>

              <div
                className="flex shrink-0 items-center gap-1"
                aria-label="Conversation actions preview"
              >
                <button
                  type="button"
                  disabled
                  title="Thread bookmark shortcut is not available here yet"
                  aria-label="Thread bookmark shortcut is not available here yet"
                  className={`flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-lg opacity-45 ${
                    isDark
                      ? "text-slate-400"
                      : "text-slate-500"
                  }`}
                >
                  <FiBookmark
                    aria-hidden="true"
                    size={15}
                  />
                </button>

                <button
                  type="button"
                  disabled
                  title="Share conversation is not available yet"
                  aria-label="Share conversation is not available yet"
                  className={`flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-lg opacity-45 ${
                    isDark
                      ? "text-slate-400"
                      : "text-slate-500"
                  }`}
                >
                  <FiShare2
                    aria-hidden="true"
                    size={15}
                  />
                </button>

                <button
                  type="button"
                  disabled
                  title="More conversation actions are not available yet"
                  aria-label="More conversation actions are not available yet"
                  className={`flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-lg opacity-45 ${
                    isDark
                      ? "text-slate-400"
                      : "text-slate-500"
                  }`}
                >
                  <FiMoreHorizontal
                    aria-hidden="true"
                    size={17}
                  />
                </button>
              </div>
            </div>
          )}

          <div
            data-chat-thread-body={
              activeChatId &&
              messages.length > 0
                ? "active"
                : "idle"
            }
            className={
              activeChatId &&
              messages.length > 0
                ? `rounded-b-2xl border border-t-0 px-3 pb-2 pt-4 sm:px-4 ${
                    isDark
                      ? "border-white/10 bg-[#0b1020]/55"
                      : "border-slate-200 bg-white/70"
                  }`
                : ""
            }
          >
          {messages.map(
            (message, index) => {
              const messageId =
                Number(message.id) ||
                null;

              const isHighlighted =
                messageId !== null &&
                highlightedMessageId ===
                  messageId;

                  const isMessageActionLoading =
                 messageId !== null &&
                Number(messageActionLoadingId) ===
                  messageId;

              return (
                <div
                  key={
                    message.id ||
                    `${message.role}-${index}`
                  }
                  ref={(element) =>
                    registerMessageRef(
                      messageId,
                      element
                    )
                  }
                  data-message-id={
                    messageId || undefined
                  }
                  className={`scroll-mt-24 rounded-2xl transition-all duration-500 ${
                    isHighlighted
                      ? isDark
                        ? "ring-2 ring-amber-400 ring-offset-4 ring-offset-slate-900"
                        : "ring-2 ring-amber-500 ring-offset-4 ring-offset-slate-100"
                      : ""
                  }`}
                >
                  <Message
  id={messageId}
  role={message.role}
  content={message.content}
  createdAt={
    message.created_at ||
    message.createdAt
  }
  imageUrl={message.imageUrl}
  fileName={message.fileName}
  fileType={message.fileType}
  fileSize={message.fileSize}
  sources={message.sources || []}
  agentName={
    message.role === "assistant"
      ? resolveAgentBadge(
          message.agentId,
          agents
        )?.name || null
      : null
  }
  isLast={
    index ===
    messages.length - 1
  }
  regenerateResponse={
    regenerateResponse
  }
  onEditMessage={
    message.role === "user"
      ? onEditMessage
      : undefined
  }
  onDeleteMessage={
    onDeleteMessage
  }
  onRegenerateMessage={
    message.role === "user"
      ? onRegenerateMessage
      : undefined
  }
  onCreateConversationBranch={
  message.role === "user"
    ? onCreateConversationBranch
    : undefined
}
  isBookmarked={
  message.isBookmarked
}
bookmarkNote={
  message.bookmarkNote || ""
}
onSaveMessageBookmark={
  onSaveMessageBookmark
}
onRemoveMessageBookmark={
  onRemoveMessageBookmark
}
  actionLoading={
    loading ||
    isMessageActionLoading
  }
  theme={theme}
/>
                </div>
              );
            }
          )}

          {!isOnline && (
            <div
              className={`mb-4 rounded-2xl border p-4 ${
                isDark
                  ? "border-amber-500/30 bg-amber-500/10"
                  : "border-amber-300 bg-amber-50"
              }`}
              role="alert"
            >
              <div className="flex items-start gap-3">
                <span className="text-xl">
                  📡
                </span>

                <div>
                  <p className="font-semibold text-amber-600">
                    Internet connection
                    lost
                  </p>

                  <p
                    className={`mt-1 text-sm ${
                      isDark
                        ? "text-slate-300"
                        : "text-slate-600"
                    }`}
                  >
                    Reconnect to the
                    internet before sending
                    or retrying a message.
                  </p>
                </div>
              </div>
            </div>
          )}

          {chatError && (
            <div
              className={`mb-4 rounded-2xl border p-4 ${
                isDark
                  ? "border-red-500/30 bg-red-500/10"
                  : "border-red-300 bg-red-50"
              }`}
              role="alert"
            >
              <div className="flex items-start gap-3">
                <span className="text-xl">
                  ⚠️
                </span>

                <div className="min-w-0 flex-1">
                  <p
                    className={`font-semibold ${
                      isDark
                        ? "text-red-300"
                        : "text-red-700"
                    }`}
                  >
                    {errorTitle}
                  </p>

                  <p
                    className={`mt-1 break-words text-sm ${
                      isDark
                        ? "text-slate-300"
                        : "text-slate-600"
                    }`}
                  >
                    {errorMessage}
                  </p>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {canRetry && (
                      <button
                        type="button"
                        onClick={
                          handleRetry
                        }
                        disabled={
                          loading ||
                          !isOnline
                        }
                        className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {loading
                          ? "Retrying..."
                          : "🔄 Retry"}
                      </button>
                    )}

                    {dismissChatError && (
                      <button
                        type="button"
                        onClick={
                          dismissChatError
                        }
                        className={`rounded-lg px-3 py-2 text-sm transition ${
                          isDark
                            ? "bg-slate-700 text-slate-200 hover:bg-slate-600"
                            : "bg-slate-200 text-slate-700 hover:bg-slate-300"
                        }`}
                      >
                        Dismiss
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {loading && (
            <Thinking theme={theme} />
          )}

          <div ref={messagesEndRef} />
          </div>

          <div
            data-workspace-bottom-deck="after-thread"
            className="pt-2"
          >
            <WorkspaceWelcome
              setInput={setInput}
              activeChatId={activeChatId}
              branchCount={
                workspaceBranchCount
              }
              onOpenKnowledge={() =>
                setWorkspacePanel(
                  "knowledge"
                )
              }
              onOpenBranches={() =>
                setWorkspacePanel(
                  "branches"
                )
              }
              onOpenSidebar={
                onOpenSidebar
              }
              showGreetingActions={false}
              showBottomCards
              theme={theme}
            />
          </div>
        </div>
      </section>

      <div
        data-chat-composer-dock="v2.40"
        className={`shrink-0 border-t px-3 pb-4 pt-3 sm:px-5 md:px-6 md:pb-5 ${
          isDark
            ? "border-white/10 bg-[#0b1020]/95"
            : "border-slate-200 bg-white/95"
        }`}
      >
        <div className="mx-auto max-w-5xl">
          <MessageInput
            input={input}
            setInput={setInput}
            sendMessage={
              isOnline
                ? sendMessage
                : () =>
                    alert(
                      "You are offline. Please reconnect and try again."
                    )
            }
            loading={loading}
            agents={agents}
            agentsLoading={agentsLoading}
            agentsAvailable={agentsAvailable}
            selectedAgentId={selectedAgentId}
            onAgentChange={onAgentChange}
            uploadProgress={uploadProgress}
            uploadSummary={uploadSummary}
            dismissUploadSummary={dismissUploadSummary}
            uploadFile={uploadFile}
            pendingFiles={pendingFiles}
            removePendingFileAt={removePendingFileAt}
            clearAllPendingFiles={clearAllPendingFiles}
            theme={theme}
          />
        </div>
      </div>
    </main>
  );
}

export default ChatWindow;
