import { useState } from "react";
import SettingsModal from "../Common/SettingsModal";

function getGroup(dateString) {
  if (!dateString) return "Older";

  const today = new Date();
  const date = new Date(dateString);

  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);

  const difference = Math.floor(
    (today.getTime() - date.getTime()) /
      (1000 * 60 * 60 * 24)
  );

  if (difference === 0) return "Today";
  if (difference === 1) return "Yesterday";
  if (difference > 1 && difference < 7) {
    return "Last Week";
  }

  return "Older";
}

function Sidebar({
  newChat,
  chats = [],
  activeChatId,
  selectChat,
  renameCurrentChat,
  deleteCurrentChat,
  isOpen,
  onClose,
  theme = "dark",
  onThemeChange,
}) {
  const [chatSearch, setChatSearch] = useState("");
  const [showSettings, setShowSettings] =
    useState(false);

  const isDark = theme === "dark";

  const filteredChats = chats.filter((chat) =>
    (chat.title || "New Chat")
      .toLowerCase()
      .includes(chatSearch.toLowerCase())
  );

  const groupedChats = filteredChats.reduce(
    (groups, chat) => {
      const group = getGroup(chat.created_at);

      if (!groups[group]) {
        groups[group] = [];
      }

      groups[group].push(chat);
      return groups;
    },
    {}
  );

  function handleNewChat() {
    newChat();
    onClose?.();
  }

  function handleSelectChat(chatId) {
    selectChat(chatId);
    onClose?.();
  }

  return (
    <>
      {/* Mobile overlay */}
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
          isOpen ? "translate-x-0" : "-translate-x-full"
        } ${
          isDark
            ? "border-slate-800 bg-[#0b1220] text-white"
            : "border-slate-200 bg-white text-slate-900"
        }`}
      >
        {/* Logo */}
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

        {/* Main buttons */}
        <div
          className={`space-y-3 border-b p-4 ${
            isDark
              ? "border-slate-800"
              : "border-slate-200"
          }`}
        >
          <button
            type="button"
            onClick={handleNewChat}
            className="w-full rounded-xl bg-blue-600 p-3 font-semibold text-white transition hover:bg-blue-700"
          >
            + New Chat
          </button>

          <button
            type="button"
            onClick={() => setShowSettings(true)}
            className={`w-full rounded-xl p-3 font-semibold transition ${
              isDark
                ? "bg-slate-700 text-white hover:bg-slate-600"
                : "bg-slate-200 text-slate-900 hover:bg-slate-300"
            }`}
          >
            ⚙ Settings
          </button>
        </div>

        {/* Recent chats */}
        <div className="flex-1 overflow-y-auto px-4 py-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-xs uppercase tracking-wider text-slate-500">
              Recent Chats
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

          <input
            type="text"
            placeholder="🔍 Search chats..."
            value={chatSearch}
            onChange={(event) =>
              setChatSearch(event.target.value)
            }
            className={`mb-4 w-full rounded-lg border p-2 text-sm outline-none transition focus:border-blue-500 ${
              isDark
                ? "border-slate-700 bg-slate-900 text-white placeholder:text-slate-500"
                : "border-slate-300 bg-slate-50 text-slate-900 placeholder:text-slate-400"
            }`}
          />

          {filteredChats.length === 0 ? (
            <p className="py-3 text-center text-sm text-slate-500">
              No chats found
            </p>
          ) : (
            <div className="space-y-5">
              {Object.entries(groupedChats).map(
                ([group, groupChats]) => (
                  <div key={group}>
                    <h4 className="mb-2 text-xs uppercase text-slate-500">
                      {group}
                    </h4>

                    <div className="space-y-2">
                      {groupChats.map((chat) => (
                        <div
                          key={chat.id}
                          onClick={() =>
                            handleSelectChat(chat.id)
                          }
                          className={`group flex cursor-pointer items-center justify-between gap-2 rounded-lg p-3 transition ${
                            activeChatId === chat.id
                              ? "bg-blue-600 text-white"
                              : isDark
                                ? "bg-slate-900 hover:bg-slate-800"
                                : "bg-slate-100 hover:bg-slate-200"
                          }`}
                        >
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">
                              💬{" "}
                              {chat.title || "New Chat"}
                            </p>

                            <p
                              className={`mt-1 truncate text-xs ${
                                activeChatId === chat.id
                                  ? "text-blue-100"
                                  : "text-slate-500"
                              }`}
                            >
                              {chat.last_message ||
                                "No messages yet"}
                            </p>
                          </div>

                          <div className="flex shrink-0 gap-1 opacity-70 transition group-hover:opacity-100">
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                renameCurrentChat(chat.id);
                              }}
                              className="rounded p-1 hover:bg-black/10"
                              title="Rename chat"
                            >
                              ✏️
                            </button>

                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                deleteCurrentChat(chat.id);
                              }}
                              className="rounded p-1 hover:bg-red-500/20"
                              title="Delete chat"
                            >
                              🗑️
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              )}
            </div>
          )}
        </div>
      </aside>

      <SettingsModal
        open={showSettings}
        onClose={() => setShowSettings(false)}
        theme={theme}
        onThemeChange={onThemeChange}
      />
    </>
  );
}

export default Sidebar;