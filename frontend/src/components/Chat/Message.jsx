import {
  useEffect,
  useMemo,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import CodeBlock from "./CodeBlock";
import SourcesCard from "./SourcesCard";


function Message({
  id,
  messageId,
  role,
  content = "",
  createdAt,
  imageUrl,
  fileName,
  fileType,
  fileSize,
  sources = [],
  agentName = null,
  regenerateResponse,
  onEditMessage,
onDeleteMessage,
onRegenerateMessage,
onCreateConversationBranch,

    isBookmarked = false,
  bookmarkNote = "",
  onSaveMessageBookmark,
  onRemoveMessageBookmark,
  isLast,
  actionLoading = false,
  theme = "dark",
}) {
  const isUser = role === "user";
  const isDark = theme === "dark";

  const resolvedMessageId =
    messageId ?? id ?? null;

  const [copied, setCopied] =
    useState(false);

  const [isEditing, setIsEditing] =
    useState(false);

  const [draftContent, setDraftContent] =
    useState(content);

  const [localAction, setLocalAction] =
    useState(null);

  const isBusy =
    actionLoading || localAction !== null;


  useEffect(() => {
    if (!isEditing) {
      setDraftContent(content);
    }
  }, [content, isEditing]);


  const formattedTimestamp = useMemo(() => {
    if (!createdAt) return "";

    const date = new Date(createdAt);

    if (
      Number.isNaN(date.getTime())
    ) {
      return "";
    }

    return new Intl.DateTimeFormat(
      "en-IN",
      {
        dateStyle: "medium",
        timeStyle: "short",
      }
    ).format(date);
  }, [createdAt]);


  function speak() {
    if (
      !content.trim() ||
      !window.speechSynthesis
    ) {
      return;
    }

    const speech =
      new SpeechSynthesisUtterance(
        content
      );

    speech.lang = "en-IN";
    speech.rate = 1;
    speech.pitch = 1;

    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(
      speech
    );
  }


  async function copyText() {
    if (!content.trim()) return;

    try {
      await navigator.clipboard.writeText(
        content
      );

      setCopied(true);

      window.setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch (error) {
      console.error(
        "Copy failed:",
        error
      );
    }
  }


  function startEditing() {
    setDraftContent(content);
    setIsEditing(true);
  }


  function cancelEditing() {
    setDraftContent(content);
    setIsEditing(false);
  }


  async function saveEditedMessage() {
    const cleanedContent =
      draftContent.trim();

    if (
      !cleanedContent ||
      !resolvedMessageId ||
      !onEditMessage
    ) {
      return;
    }

    if (cleanedContent === content.trim()) {
      setIsEditing(false);
      return;
    }

    try {
      setLocalAction("edit");

      await onEditMessage(
        resolvedMessageId,
        cleanedContent
      );

      setIsEditing(false);
    } catch (error) {
      console.error(
        "Edit message failed:",
        error
      );
    } finally {
      setLocalAction(null);
    }
  }


  async function deleteCurrentMessage() {
    if (
      !resolvedMessageId ||
      !onDeleteMessage
    ) {
      return;
    }

    const confirmed = window.confirm(
      isUser
        ? "Delete this user message?"
        : "Delete this assistant response?"
    );

    if (!confirmed) return;

    try {
      setLocalAction("delete");

      await onDeleteMessage(
        resolvedMessageId,
        role
      );
    } catch (error) {
      console.error(
        "Delete message failed:",
        error
      );
    } finally {
      setLocalAction(null);
    }
  }


  async function regenerateFromMessage() {
    if (
      !resolvedMessageId ||
      !onRegenerateMessage
    ) {
      return;
    }

    try {
      setLocalAction("regenerate");

      await onRegenerateMessage(
        resolvedMessageId
      );
    } catch (error) {
      console.error(
        "Regenerate message failed:",
        error
      );
    } finally {
      setLocalAction(null);
    }
  }

  async function createConversationBranch() {
  if (
    !resolvedMessageId ||
    !onCreateConversationBranch
  ) {
    return;
  }

  const enteredTitle =
    window.prompt(
      "Enter a title for the new branch (optional):",
      ""
    );

  if (enteredTitle === null) {
    return;
  }

  const cleanedTitle =
    enteredTitle.trim();

  if (cleanedTitle.length > 200) {
    window.alert(
      "Branch title must be 200 characters or fewer."
    );

    return;
  }

  try {
    setLocalAction("branch");

    await onCreateConversationBranch(
      resolvedMessageId,
      cleanedTitle || null
    );
  } catch (error) {
    console.error(
      "Create conversation branch failed:",
      error
    );
  } finally {
    setLocalAction(null);
  }
}

  async function regenerateLatestResponse() {
    if (!regenerateResponse) return;

    try {
      setLocalAction("regenerate");
      await regenerateResponse();
    } catch (error) {
      console.error(
        "Regenerate response failed:",
        error
      );
    } finally {
      setLocalAction(null);
    }
  }

  async function saveBookmark() {
    if (
      !resolvedMessageId ||
      !onSaveMessageBookmark
    ) {
      return;
    }

    const enteredNote =
      window.prompt(
        isBookmarked
          ? "Update bookmark note:"
          : "Add an optional bookmark note:",
        bookmarkNote || ""
      );

    if (enteredNote === null) {
      return;
    }

    try {
      setLocalAction("bookmark");

      await onSaveMessageBookmark(
        resolvedMessageId,
        enteredNote.trim()
      );
    } catch (error) {
      console.error(
        "Save bookmark failed:",
        error
      );
    } finally {
      setLocalAction(null);
    }
  }


  async function removeBookmark() {
    if (
      !resolvedMessageId ||
      !onRemoveMessageBookmark
    ) {
      return;
    }

    const confirmed =
      window.confirm(
        "Remove this bookmark?"
      );

    if (!confirmed) return;

    try {
      setLocalAction(
        "remove-bookmark"
      );

      await onRemoveMessageBookmark(
        resolvedMessageId
      );
    } catch (error) {
      console.error(
        "Remove bookmark failed:",
        error
      );
    } finally {
      setLocalAction(null);
    }
  }

  function handleEditorKeyDown(event) {
    if (
      event.key === "Enter" &&
      (event.ctrlKey || event.metaKey)
    ) {
      event.preventDefault();
      saveEditedMessage();
    }

    if (event.key === "Escape") {
      cancelEditing();
    }
  }


  return (
    <div
      className={`mb-5 flex ${
        isUser
          ? "justify-end"
          : "justify-start"
      }`}
    >
      <div
        className={`max-w-[90%] rounded-2xl px-4 py-3 leading-relaxed sm:max-w-3xl sm:px-5 sm:py-4 ${
          isUser
            ? "rounded-br-md bg-blue-600 text-white"
            : isDark
              ? "rounded-bl-md border border-slate-700 bg-slate-800 text-slate-100"
              : "rounded-bl-md border border-slate-200 bg-white text-slate-900 shadow-sm"
        }`}
      >
        {/* Image preview */}
        {imageUrl && (
          <div className="mb-3">
            <img
              src={imageUrl}
              alt={
                fileName ||
                "Uploaded image"
              }
              className={`max-h-80 max-w-full rounded-xl border ${
                isDark
                  ? "border-slate-700"
                  : "border-slate-200"
              }`}
            />

            <p
              className={`mt-2 text-xs ${
                isUser
                  ? "text-blue-100"
                  : isDark
                    ? "text-slate-400"
                    : "text-slate-500"
              }`}
            >
              📷{" "}
              {fileName ||
                "Uploaded image"}
            </p>
          </div>
        )}

        {/* PDF preview */}
        {fileType === "pdf" && (
          <div
            className={`mb-3 flex items-center gap-3 rounded-xl border p-3 ${
              isUser
                ? "border-blue-400/50 bg-blue-700/40"
                : isDark
                  ? "border-slate-600 bg-slate-900"
                  : "border-slate-200 bg-slate-100"
            }`}
          >
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-red-500/20 text-2xl">
              📄
            </div>

            <div className="min-w-0">
              <p
                className={`max-w-64 truncate font-medium ${
                  isUser
                    ? "text-white"
                    : isDark
                      ? "text-slate-100"
                      : "text-slate-900"
                }`}
              >
                {fileName ||
                  "Uploaded PDF"}
              </p>

              <p
                className={`text-xs ${
                  isUser
                    ? "text-blue-100"
                    : isDark
                      ? "text-slate-400"
                      : "text-slate-500"
                }`}
              >
                PDF document
                {fileSize
                  ? ` • ${fileSize}`
                  : ""}
              </p>
            </div>
          </div>
        )}

        {/* Message editor */}
        {isEditing ? (
          <div>
            <textarea
              value={draftContent}
              onChange={(event) =>
                setDraftContent(
                  event.target.value
                )
              }
              onKeyDown={
                handleEditorKeyDown
              }
              disabled={isBusy}
              autoFocus
              rows={5}
              className={`w-full resize-y rounded-xl border p-3 text-sm outline-none transition ${
                isDark
                  ? "border-blue-400 bg-slate-950 text-white focus:ring-2 focus:ring-blue-400"
                  : "border-blue-300 bg-white text-slate-900 focus:ring-2 focus:ring-blue-300"
              }`}
            />

            <div className="mt-2 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={cancelEditing}
                disabled={isBusy}
                className="rounded-lg bg-slate-600 px-3 py-1.5 text-sm text-white transition hover:bg-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={
                  saveEditedMessage
                }
                disabled={
                  isBusy ||
                  !draftContent.trim()
                }
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {localAction === "edit"
                  ? "Saving..."
                  : "Save & regenerate"}
              </button>
            </div>

            <p className="mt-2 text-right text-xs text-blue-100">
              Ctrl + Enter to save •
              Esc to cancel
            </p>
          </div>
        ) : (
          <>
            {/* Message content */}
            {content && (
              <div className="break-words">
                <ReactMarkdown
                  remarkPlugins={[
                    remarkGfm,
                  ]}
                  components={{
                    code({
                      inline,
                      className,
                      children,
                      ...props
                    }) {
                      const match =
                        /language-(\w+)/.exec(
                          className || ""
                        );

                      return (
                        !inline && match
                      ) ? (
                        <CodeBlock
                          language={
                            match[1]
                          }
                          value={String(
                            children
                          ).replace(
                            /\n$/,
                            ""
                          )}
                          theme={theme}
                        />
                      ) : (
                        <code
                          className={`rounded px-1 py-0.5 ${
                            isUser
                              ? "bg-blue-800/50"
                              : isDark
                                ? "bg-slate-950"
                                : "bg-slate-200"
                          }`}
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    },

                    a({
                      children,
                      href,
                    }) {
                      return (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={
                            isUser
                              ? "text-white underline"
                              : "text-blue-500 underline"
                          }
                        >
                          {children}
                        </a>
                      );
                    },
                  }}
                >
                  {content}
                </ReactMarkdown>
              </div>
            )}

            {!isUser && (
              <SourcesCard
                sources={sources}
                theme={theme}
              />
            )}
          </>
        )}

        {/* Bookmark details */}
        {isBookmarked &&
          !isEditing && (
            <div
              className={`mt-3 rounded-xl border px-3 py-2 text-sm ${
                isUser
                  ? "border-amber-300/50 bg-blue-700/40"
                  : isDark
                    ? "border-amber-500/30 bg-amber-500/10"
                    : "border-amber-300 bg-amber-50"
              }`}
            >
              <p className="font-semibold">
                🔖 Bookmarked
              </p>

              {bookmarkNote && (
                <p
                  className={`mt-1 break-words text-xs ${
                    isUser
                      ? "text-blue-100"
                      : isDark
                        ? "text-slate-300"
                        : "text-slate-600"
                  }`}
                >
                  {bookmarkNote}
                </p>
              )}
            </div>
          )}

        {/* Timestamp */}
        {formattedTimestamp &&
          !isEditing && (
            <p
              className={`mt-3 text-xs ${
                isUser
                  ? "text-blue-100"
                  : isDark
                    ? "text-slate-400"
                    : "text-slate-500"
              }`}
              title={createdAt}
            >
              {formattedTimestamp}
            </p>
          )}

        {/* Message actions */}
        {!isEditing && content && (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={copyText}
              disabled={isBusy}
              className={`rounded-lg px-3 py-1 text-sm transition disabled:cursor-not-allowed disabled:opacity-60 ${
                isUser
                  ? "bg-blue-700 hover:bg-blue-800"
                  : isDark
                    ? "bg-slate-700 hover:bg-slate-600"
                    : "bg-slate-200 hover:bg-slate-300"
              }`}
            >
              {copied
                ? "✅ Copied"
                : "📋 Copy"}
            </button>

            {onSaveMessageBookmark &&
              resolvedMessageId && (
                <button
                  type="button"
                  onClick={saveBookmark}
                  disabled={isBusy}
                  className="rounded-lg bg-amber-500 px-3 py-1 text-sm text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {localAction ===
                  "bookmark"
                    ? "Saving..."
                    : isBookmarked
                      ? "✏️ Bookmark note"
                      : "🔖 Bookmark"}
                </button>
              )}

            {isBookmarked &&
              onRemoveMessageBookmark &&
              resolvedMessageId && (
                <button
                  type="button"
                  onClick={
                    removeBookmark
                  }
                  disabled={isBusy}
                  className="rounded-lg bg-orange-700 px-3 py-1 text-sm text-white transition hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {localAction ===
                  "remove-bookmark"
                    ? "Removing..."
                    : "🔖 Remove"}
                </button>
              )}

            {!isUser &&
              agentName && (
                <span
                  className={`whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-semibold ${
                    isDark
                      ? "border-blue-500/40 bg-blue-500/10 text-blue-200"
                      : "border-blue-200 bg-blue-50 text-blue-700"
                  }`}
                  aria-label={`Agent: ${agentName}`}
                  title={`Agent: ${agentName}`}
                >
                  Agent Â· {agentName}
                </span>
              )}

            {!isUser && (
              <button
                type="button"
                onClick={speak}
                disabled={isBusy}
                className="rounded-lg bg-purple-600 px-3 py-1 text-sm text-white transition hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                🔊 Speak
              </button>
            )}

            {isUser &&
              onEditMessage &&
              resolvedMessageId && (
                <button
                  type="button"
                  onClick={startEditing}
                  disabled={isBusy}
                  className="rounded-lg bg-amber-500 px-3 py-1 text-sm text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  ✏️ Edit
                </button>
              )}

            {isUser &&
              onRegenerateMessage &&
              resolvedMessageId && (
                <button
                  type="button"
                  onClick={
                    regenerateFromMessage
                  }
                  disabled={isBusy}
                  className="rounded-lg bg-emerald-600 px-3 py-1 text-sm text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {localAction ===
                  "regenerate"
                    ? "Regenerating..."
                    : "🔄 Regenerate"}
                </button>
              )}

              {isUser &&
  onCreateConversationBranch &&
  resolvedMessageId && (
    <button
      type="button"
      onClick={
        createConversationBranch
      }
      disabled={isBusy}
      className="rounded-lg bg-teal-600 px-3 py-1 text-sm text-white transition hover:bg-teal-500 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {localAction === "branch"
        ? "Branching..."
        : "🌿 Branch"}
    </button>
  )}

            {!isUser &&
              isLast &&
              regenerateResponse &&
              !onRegenerateMessage && (
                <button
                  type="button"
                  onClick={
                    regenerateLatestResponse
                  }
                  disabled={isBusy}
                  className="rounded-lg bg-blue-600 px-3 py-1 text-sm text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {localAction ===
                  "regenerate"
                    ? "Regenerating..."
                    : "🔄 Regenerate"}
                </button>
              )}

            {onDeleteMessage &&
              resolvedMessageId && (
                <button
                  type="button"
                  onClick={
                    deleteCurrentMessage
                  }
                  disabled={isBusy}
                  className="rounded-lg bg-red-600 px-3 py-1 text-sm text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {localAction === "delete"
                    ? "Deleting..."
                    : "🗑️ Delete"}
                </button>
              )}

            {!isUser && (
              <>
                <button
                  type="button"
                  disabled={isBusy}
                  className={`rounded-lg px-3 py-1 transition disabled:cursor-not-allowed disabled:opacity-60 ${
                    isDark
                      ? "bg-slate-700 hover:bg-slate-600"
                      : "bg-slate-200 hover:bg-slate-300"
                  }`}
                  title="Helpful"
                >
                  👍
                </button>

                <button
                  type="button"
                  disabled={isBusy}
                  className={`rounded-lg px-3 py-1 transition disabled:cursor-not-allowed disabled:opacity-60 ${
                    isDark
                      ? "bg-slate-700 hover:bg-slate-600"
                      : "bg-slate-200 hover:bg-slate-300"
                  }`}
                  title="Not helpful"
                >
                  👎
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default Message;