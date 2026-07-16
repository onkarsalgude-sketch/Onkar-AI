import {
  useEffect,
  useRef,
  useState,
} from "react";

import Message from "./Message";
import MessageInput from "./MessageInput";
import Thinking from "./Thinking";
import WelcomeScreen from "../Common/WelcomeScreen";
import DocumentLibrary from "../Documents/DocumentLibrary";


function ChatWindow({
  activeChatId,
  documentRefreshKey,
  messages,
  input,
  setInput,
  sendMessage,
  loading,
  uploadFile,
  pendingFiles,
  removePendingFileAt,
  clearAllPendingFiles,
  uploadProgress,
  uploadSummary,
  dismissUploadSummary,
  regenerateResponse,
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
      className={`relative flex h-screen min-w-0 flex-1 flex-col transition-colors duration-300 ${
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
        className={`flex h-20 shrink-0 items-center justify-between border-b px-3 sm:px-5 md:px-8 ${
          isDark
            ? "border-slate-800 bg-[#0f172a]"
            : "border-slate-200 bg-white"
        }`}
      >
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onOpenSidebar}
            className={`shrink-0 rounded-lg p-2 text-xl md:hidden ${
              isDark
                ? "bg-slate-800 hover:bg-slate-700"
                : "bg-slate-200 hover:bg-slate-300"
            }`}
            aria-label="Open sidebar"
          >
            ☰
          </button>

          <div className="min-w-0">
            <h2 className="truncate text-base font-bold sm:text-lg md:text-xl">
              Onkar Personal AI
            </h2>

            <p className="hidden truncate text-sm text-slate-500 sm:block">
              PDF RAG • Vision • Voice •
              Internet Search
            </p>
          </div>
        </div>

        <div
          className={`ml-2 flex shrink-0 items-center gap-2 rounded-full px-3 py-2 text-xs md:px-4 md:text-sm ${
            isOnline
              ? isDark
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-emerald-100 text-emerald-700"
              : isDark
                ? "bg-red-500/10 text-red-400"
                : "bg-red-100 text-red-700"
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              isOnline
                ? "bg-emerald-500"
                : "bg-red-500"
            }`}
          />

          {isOnline
            ? "Online"
            : "Offline"}
        </div>
      </header>

      <DocumentLibrary
        activeChatId={activeChatId}
        refreshKey={documentRefreshKey}
        theme={theme}
      />

      <section className="flex-1 overflow-y-auto px-3 py-4 sm:px-5 md:px-8 md:py-6">
        <div className="mx-auto max-w-4xl">
          {messages.length <= 1 && (
            <WelcomeScreen
              setInput={setInput}
              theme={theme}
            />
          )}

          {messages.map(
            (message, index) => {
              const messageId =
                Number(message.id) ||
                null;

              const isHighlighted =
                messageId !== null &&
                highlightedMessageId ===
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
                    role={message.role}
                    content={
                      message.content
                    }
                    imageUrl={
                      message.imageUrl
                    }
                    fileName={
                      message.fileName
                    }
                    fileType={
                      message.fileType
                    }
                    fileSize={
                      message.fileSize
                    }
                    sources={
                      message.sources || []
                    }
                    isLast={
                      index ===
                      messages.length - 1
                    }
                    regenerateResponse={
                      regenerateResponse
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
      </section>

      <div
        className={`shrink-0 px-3 pb-4 sm:px-5 md:px-8 md:pb-6 ${
          isDark
            ? "bg-[#0f172a]"
            : "bg-slate-100"
        }`}
      >
        <div className="mx-auto max-w-4xl">
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