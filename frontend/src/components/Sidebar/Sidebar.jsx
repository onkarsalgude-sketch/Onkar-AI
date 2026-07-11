import { useState } from "react";
import SettingsModal from "../Common/SettingsModal";

function getGroup(dateString) {
  if (!dateString) return "Older";

  const today = new Date();
  const date = new Date(dateString);

  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);

  const diff = Math.floor(
    (today.getTime() - date.getTime()) /
      (1000 * 60 * 60 * 24)
  );

  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff > 1 && diff < 7) return "Last Week";

  return "Older";
}

function Sidebar({
  uploadPDF,
  uploading,
  newChat,
  documents = [],
  deleteDocument,
  chats = [],
  activeChatId,
  selectChat,
  renameCurrentChat,
  deleteCurrentChat,
  isOpen,
  onClose,
}) {
  const [chatSearch, setChatSearch] = useState("");
  const [documentSearch, setDocumentSearch] =
    useState("");
  const [showSettings, setShowSettings] =
    useState(false);
  const [deletingDocument, setDeletingDocument] =
    useState(null);

  const filteredDocuments = documents.filter((doc) =>
    doc.name
      .toLowerCase()
      .includes(documentSearch.toLowerCase())
  );

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

  async function handleDeleteDocument(filename) {
    const confirmed = window.confirm(
      `Delete "${filename}"?\n\nThe PDF and its indexed data will be removed.`
    );

    if (!confirmed) return;

    try {
      setDeletingDocument(filename);
      await deleteDocument(filename);
    } finally {
      setDeletingDocument(null);
    }
  }

  function handleNewChat() {
    newChat();
    onClose();
  }

  function handleSelectChat(chatId) {
    selectChat(chatId);
    onClose();
  }

  return (
    <>
      {/* Mobile background overlay */}
      {isOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={onClose}
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex h-screen w-80 shrink-0 flex-col border-r border-slate-800 bg-[#0b1220] text-white transition-transform duration-300 md:static md:z-auto md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Logo */}
        <div className="flex items-center justify-between border-b border-slate-800 p-6">
          <div>
            <h1 className="text-2xl font-bold">
              🤖 Onkar AI
            </h1>

            <p className="mt-1 text-sm text-slate-400">
              Personal AI Assistant
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-xl hover:bg-slate-800 md:hidden"
            aria-label="Close sidebar"
          >
            ✕
          </button>
        </div>

        {/* Main buttons */}
        <div className="space-y-3 border-b border-slate-800 p-4">
          <button
            type="button"
            onClick={handleNewChat}
            className="w-full rounded-xl bg-blue-600 p-3 font-semibold transition hover:bg-blue-700"
          >
            + New Chat
          </button>

          <label
            className={`block w-full rounded-xl p-3 text-center font-semibold transition ${
              uploading
                ? "cursor-not-allowed bg-emerald-800 opacity-70"
                : "cursor-pointer bg-emerald-600 hover:bg-emerald-700"
            }`}
          >
            📎{" "}
            {uploading
              ? "Uploading..."
              : "Upload PDF"}

            <input
              type="file"
              accept="application/pdf,.pdf"
              hidden
              disabled={uploading}
              onChange={uploadPDF}
            />
          </label>

          <button
            type="button"
            onClick={() => setShowSettings(true)}
            className="w-full rounded-xl bg-slate-700 p-3 font-semibold transition hover:bg-slate-600"
          >
            ⚙ Settings
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-4 py-5">
          {/* Uploaded files */}
          <div className="mb-7">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-xs uppercase tracking-wider text-slate-500">
                Uploaded Files
              </h3>

              <span className="rounded-full bg-slate-800 px-2 py-1 text-xs text-slate-400">
                {documents.length}
              </span>
            </div>

            {documents.length > 0 && (
              <input
                type="text"
                placeholder="🔍 Search PDFs..."
                value={documentSearch}
                onChange={(event) =>
                  setDocumentSearch(event.target.value)
                }
                className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-900 p-2 text-sm text-white outline-none focus:border-blue-500"
              />
            )}

            <div className="space-y-2">
              {documents.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-700 p-4 text-center">
                  <p className="text-2xl">📂</p>

                  <p className="mt-2 text-sm text-slate-500">
                    No PDF uploaded
                  </p>
                </div>
              ) : filteredDocuments.length === 0 ? (
                <p className="py-3 text-center text-sm text-slate-500">
                  No matching PDF found
                </p>
              ) : (
                filteredDocuments.map((doc) => (
                  <div
                    key={doc.name}
                    className="group flex items-center justify-between gap-3 rounded-lg border border-transparent bg-slate-900 p-3 transition hover:border-slate-700 hover:bg-slate-800"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-red-500/15 text-xl">
                        📄
                      </div>

                      <div className="min-w-0">
                        <p
                          className="truncate text-sm font-medium text-slate-100"
                          title={doc.name}
                        >
                          {doc.name}
                        </p>

                        <p className="mt-1 text-xs text-slate-500">
                          {doc.size} KB · PDF
                        </p>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() =>
                        handleDeleteDocument(doc.name)
                      }
                      disabled={
                        deletingDocument === doc.name
                      }
                      className="shrink-0 rounded-lg p-2 text-slate-500 transition hover:bg-red-500/10 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-50"
                      title={`Delete ${doc.name}`}
                    >
                      {deletingDocument === doc.name
                        ? "⏳"
                        : "🗑️"}
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Recent chats */}
          <div>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-xs uppercase tracking-wider text-slate-500">
                Recent Chats
              </h3>

              <span className="rounded-full bg-slate-800 px-2 py-1 text-xs text-slate-400">
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
              className="mb-4 w-full rounded-lg border border-slate-700 bg-slate-900 p-2 text-sm text-white outline-none focus:border-blue-500"
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
                                ? "bg-blue-600"
                                : "bg-slate-900 hover:bg-slate-800"
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
                                    : "text-slate-400"
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
                                className="rounded p-1 hover:bg-white/10"
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
        </div>
      </aside>

      <SettingsModal
        open={showSettings}
        onClose={() => setShowSettings(false)}
      />
    </>
  );
}

export default Sidebar;