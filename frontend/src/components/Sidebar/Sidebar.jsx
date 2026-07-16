import {
  useState,
} from "react";

import SettingsModal from "../Common/SettingsModal";
import GlobalChatSearch from "./GlobalChatSearch";

function getGroup(dateString) {
  if (!dateString) return "Older";

  const today = new Date();
  const date = new Date(dateString);

  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);

  const difference = Math.floor(
    (
      today.getTime() -
      date.getTime()
    ) /
      (1000 * 60 * 60 * 24)
  );

  if (difference === 0) return "Today";
  if (difference === 1) return "Yesterday";

  if (
    difference > 1 &&
    difference < 7
  ) {
    return "Last Week";
  }

  return "Older";
}

function Sidebar({
  messages = [],
  newChat,
  chats = [],
  activeChatId,
  selectChat,
  renameCurrentChat,
  deleteCurrentChat,
  restoreChatBackup,
  restoreFullChatBackup,
  toggleChatPin,

  folders = [],
  createChatFolder,
  renameChatFolder,
  deleteChatFolder,
  moveChatToFolder,

  models = [],
  defaultModel = "",
  selectedModel = "",
  onModelChange,

  isOpen,
  onClose,
  theme = "dark",
  onThemeChange,
}) {
  const [
    globalSearchActive,
    setGlobalSearchActive,
  ] = useState(false);

  const [
    newFolderName,
    setNewFolderName,
  ] = useState("");

  const [
    showSettings,
    setShowSettings,
  ] = useState(false);

  const isDark =
    theme === "dark";

  const activeChat =
    chats.find(
      (chat) =>
        chat.id === activeChatId
    ) || null;

  const pinnedChats =
    chats.filter(
      (chat) =>
        chat.is_pinned
    );

  const normalChats =
    chats.filter(
      (chat) =>
        !chat.is_pinned
    );

  const unfiledChats =
    normalChats.filter(
      (chat) =>
        chat.folder_id == null
    );

  const groupedUnfiledChats =
    unfiledChats.reduce(
      (groups, chat) => {
        const group = getGroup(
          chat.created_at
        );

        if (!groups[group]) {
          groups[group] = [];
        }

        groups[group].push(
          chat
        );

        return groups;
      },
      {}
    );

  function getChatsForFolder(
    folderId
  ) {
    return normalChats.filter(
      (chat) =>
        Number(
          chat.folder_id
        ) === Number(folderId)
    );
  }

  function handleNewChat() {
    newChat();
    onClose?.();
  }

  function handleSelectChat(
    chatId
  ) {
    selectChat(chatId);
    onClose?.();
  }

  function handleSearchResult(
    result
  ) {
    selectChat(
      result.chat_id,
      result.message_id || null
    );

    onClose?.();
  }

  async function handleCreateFolder(
    event
  ) {
    event.preventDefault();

    const folderName =
      newFolderName.trim();

    if (!folderName) return;

    const created =
      await createChatFolder?.(
        folderName
      );

    if (created) {
      setNewFolderName("");
    }
  }

  async function handleRenameFolder(
    folder
  ) {
    const name =
      window.prompt(
        "Enter new folder name:",
        folder.name
      );

    if (name === null) return;

    await renameChatFolder?.(
      folder.id,
      name
    );
  }

  async function handleDeleteFolder(
    folder
  ) {
    const confirmed =
      window.confirm(
        `Delete folder "${folder.name}"?\n\nChats will not be deleted. They will move to Unfiled Chats.`
      );

    if (!confirmed) return;

    await deleteChatFolder?.(
      folder.id
    );
  }

  async function handleMoveChat(
    event,
    chatId
  ) {
    event.stopPropagation();

    const value =
      event.target.value;

    const folderId =
      value === ""
        ? null
        : Number(value);

    await moveChatToFolder?.(
      chatId,
      folderId
    );
  }

  function renderChatItem(chat) {
    const isActive =
      activeChatId === chat.id;

    return (
      <div
        key={chat.id}
        onClick={() =>
          handleSelectChat(
            chat.id
          )
        }
        className={`group cursor-pointer rounded-xl border p-3 transition ${
          isActive
            ? "border-blue-500 bg-blue-600 text-white"
            : isDark
              ? "border-slate-800 bg-slate-900 hover:border-slate-700 hover:bg-slate-800"
              : "border-slate-200 bg-slate-100 hover:border-slate-300 hover:bg-slate-200"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">
              {chat.is_pinned
                ? "📌"
                : "💬"}{" "}
              {chat.title ||
                "New Chat"}
            </p>

            <p
              className={`mt-1 truncate text-xs ${
                isActive
                  ? "text-blue-100"
                  : "text-slate-500"
              }`}
            >
              {chat.last_message ||
                "No messages yet"}
            </p>

            {chat.folder_name && (
              <p
                className={`mt-1 truncate text-xs ${
                  isActive
                    ? "text-blue-100"
                    : isDark
                      ? "text-slate-400"
                      : "text-slate-600"
                }`}
              >
                📁{" "}
                {
                  chat.folder_name
                }
              </p>
            )}
          </div>

          <div className="flex shrink-0 gap-1 opacity-80 transition group-hover:opacity-100">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();

                toggleChatPin?.(
                  chat.id
                );
              }}
              className={`rounded-md p-1 transition ${
                chat.is_pinned
                  ? "bg-amber-500/30"
                  : "hover:bg-black/10"
              }`}
              title={
                chat.is_pinned
                  ? "Unpin chat"
                  : "Pin chat"
              }
              aria-label={
                chat.is_pinned
                  ? "Unpin chat"
                  : "Pin chat"
              }
            >
              📌
            </button>

            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();

                renameCurrentChat(
                  chat.id
                );
              }}
              className="rounded-md p-1 transition hover:bg-black/10"
              title="Rename chat"
              aria-label="Rename chat"
            >
              ✏️
            </button>

            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();

                deleteCurrentChat(
                  chat.id
                );
              }}
              className="rounded-md p-1 transition hover:bg-red-500/20"
              title="Delete chat"
              aria-label="Delete chat"
            >
              🗑️
            </button>
          </div>
        </div>

        <select
          value={
            chat.folder_id ??
            ""
          }
          onClick={(event) =>
            event.stopPropagation()
          }
          onChange={(event) =>
            handleMoveChat(
              event,
              chat.id
            )
          }
          className={`mt-3 w-full rounded-lg border px-2 py-1.5 text-xs outline-none transition focus:border-blue-400 ${
            isActive
              ? "border-blue-400 bg-blue-700 text-white"
              : isDark
                ? "border-slate-700 bg-slate-950 text-slate-300"
                : "border-slate-300 bg-white text-slate-700"
          }`}
          title="Move chat to folder"
          aria-label="Move chat to folder"
        >
          <option
            value=""
            className="text-slate-900"
          >
            📂 No folder
          </option>

          {folders.map(
            (folder) => (
              <option
                key={folder.id}
                value={folder.id}
                className="text-slate-900"
              >
                📁{" "}
                {folder.name}
              </option>
            )
          )}
        </select>
      </div>
    );
  }

  return (
    <>
      {isOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={onClose}
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex h-screen w-80 shrink-0 flex-col border-r transition-all duration-300 md:static md:z-auto md:translate-x-0 ${
          isOpen
            ? "translate-x-0"
            : "-translate-x-full"
        } ${
          isDark
            ? "border-slate-800 bg-[#0b1220] text-white"
            : "border-slate-200 bg-white text-slate-900"
        }`}
      >
        <div
          className={`flex items-center justify-between border-b p-6 ${
            isDark
              ? "border-slate-800"
              : "border-slate-200"
          }`}
        >
          <div>
            <h1 className="text-2xl font-bold">
              🤖 Onkar AI
            </h1>

            <p
              className={`mt-1 text-sm ${
                isDark
                  ? "text-slate-400"
                  : "text-slate-500"
              }`}
            >
              Personal AI Assistant
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className={`rounded-lg p-2 text-xl transition md:hidden ${
              isDark
                ? "hover:bg-slate-800"
                : "hover:bg-slate-100"
            }`}
            aria-label="Close sidebar"
          >
            ✕
          </button>
        </div>

        <div
          className={`space-y-3 border-b p-4 ${
            isDark
              ? "border-slate-800"
              : "border-slate-200"
          }`}
        >
          <button
            type="button"
            onClick={
              handleNewChat
            }
            className="w-full rounded-xl bg-blue-600 p-3 font-semibold text-white transition hover:bg-blue-700"
          >
            + New Chat
          </button>

          <button
            type="button"
            onClick={() =>
              setShowSettings(
                true
              )
            }
            className={`w-full rounded-xl p-3 font-semibold transition ${
              isDark
                ? "bg-slate-700 text-white hover:bg-slate-600"
                : "bg-slate-200 text-slate-900 hover:bg-slate-300"
            }`}
          >
            ⚙ Settings
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-xs uppercase tracking-wider text-slate-500">
              Chats
            </h3>

            <span
              className={`rounded-full px-2 py-1 text-xs ${
                isDark
                  ? "bg-slate-800 text-slate-400"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {chats.length}
            </span>
          </div>

          <GlobalChatSearch
            folders={folders}
            onSelectResult={
              handleSearchResult
            }
            onSearchActiveChange={
              setGlobalSearchActive
            }
            theme={theme}
          />

          {!globalSearchActive && (
            <>
              <div
                className={`mb-5 rounded-xl border p-3 ${
                  isDark
                    ? "border-slate-800 bg-slate-900/60"
                    : "border-slate-200 bg-slate-50"
                }`}
              >
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    📁 Folders
                  </h3>

                  <span className="text-xs text-slate-500">
                    {folders.length}
                  </span>
                </div>

                <form
                  onSubmit={
                    handleCreateFolder
                  }
                  className="flex gap-2"
                >
                  <input
                    type="text"
                    value={
                      newFolderName
                    }
                    onChange={(
                      event
                    ) =>
                      setNewFolderName(
                        event.target
                          .value
                      )
                    }
                    placeholder="Folder name..."
                    maxLength={50}
                    className={`min-w-0 flex-1 rounded-lg border px-2 py-2 text-sm outline-none focus:border-blue-500 ${
                      isDark
                        ? "border-slate-700 bg-slate-950 text-white"
                        : "border-slate-300 bg-white text-slate-900"
                    }`}
                  />

                  <button
                    type="submit"
                    disabled={
                      !newFolderName.trim()
                    }
                    className="rounded-lg bg-blue-600 px-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                    title="Create folder"
                  >
                    +
                  </button>
                </form>
              </div>

              <div className="space-y-6">
                {pinnedChats.length >
                  0 && (
                  <section>
                    <h4 className="mb-2 text-xs uppercase tracking-wider text-amber-500">
                      📌 Pinned
                    </h4>

                    <div className="space-y-2">
                      {pinnedChats.map(
                        renderChatItem
                      )}
                    </div>
                  </section>
                )}

                {folders.map(
                  (folder) => {
                    const folderChats =
                      getChatsForFolder(
                        folder.id
                      );

                    return (
                      <section
                        key={
                          folder.id
                        }
                      >
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            <h4 className="truncate text-xs font-semibold uppercase tracking-wider text-blue-500">
                              📁{" "}
                              {
                                folder.name
                              }
                            </h4>

                            <p className="mt-1 text-[11px] text-slate-500">
                              {folder.chat_count ||
                                0}{" "}
                              chats
                            </p>
                          </div>

                          <div className="flex shrink-0 gap-1">
                            <button
                              type="button"
                              onClick={() =>
                                handleRenameFolder(
                                  folder
                                )
                              }
                              className={`rounded-md p-1 text-xs transition ${
                                isDark
                                  ? "hover:bg-slate-800"
                                  : "hover:bg-slate-200"
                              }`}
                              title="Rename folder"
                            >
                              ✏️
                            </button>

                            <button
                              type="button"
                              onClick={() =>
                                handleDeleteFolder(
                                  folder
                                )
                              }
                              className="rounded-md p-1 text-xs transition hover:bg-red-500/20"
                              title="Delete folder"
                            >
                              🗑️
                            </button>
                          </div>
                        </div>

                        {folderChats.length >
                        0 ? (
                          <div className="space-y-2">
                            {folderChats.map(
                              renderChatItem
                            )}
                          </div>
                        ) : (
                          <p
                            className={`rounded-lg border border-dashed px-3 py-3 text-center text-xs ${
                              isDark
                                ? "border-slate-800 text-slate-500"
                                : "border-slate-300 text-slate-500"
                            }`}
                          >
                            No chats in this folder
                          </p>
                        )}
                      </section>
                    );
                  }
                )}

                {unfiledChats.length >
                  0 && (
                  <section>
                    <h4 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
                      📂 Unfiled Chats
                    </h4>

                    <div className="space-y-5">
                      {Object.entries(
                        groupedUnfiledChats
                      ).map(
                        ([
                          group,
                          groupChats,
                        ]) => (
                          <div
                            key={
                              group
                            }
                          >
                            <h5 className="mb-2 text-[11px] uppercase text-slate-500">
                              {group}
                            </h5>

                            <div className="space-y-2">
                              {groupChats.map(
                                renderChatItem
                              )}
                            </div>
                          </div>
                        )
                      )}
                    </div>
                  </section>
                )}

                {chats.length ===
                  0 && (
                  <p className="py-3 text-center text-sm text-slate-500">
                    Start your first chat
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      </aside>

      <SettingsModal
        open={showSettings}
        onClose={() =>
          setShowSettings(false)
        }
        theme={theme}
        onThemeChange={
          onThemeChange
        }
        messages={messages}
        activeChat={activeChat}
        restoreChatBackup={
          restoreChatBackup
        }
        restoreFullChatBackup={
          restoreFullChatBackup
        }
        models={models}
        defaultModel={
          defaultModel
        }
        selectedModel={
          selectedModel
        }
        onModelChange={
          onModelChange
        }
      />
    </>
  );
}

export default Sidebar;