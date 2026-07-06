import { useState } from "react";

function getGroup(dateString) {
  const today = new Date();
  const date = new Date(dateString);

  const diff =
    Math.floor((today - date) / (1000 * 60 * 60 * 24));

  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 7) return "Last Week";

  return "Older";
}
function Sidebar({
  uploadPDF,
  uploading,
  newChat,
  documents,
  deleteDocument,
  chats,
  activeChatId,
  selectChat,
  renameCurrentChat,
  deleteCurrentChat,
}) {
  const [search, setSearch] = useState("");
  const filteredChats = chats.filter((chat) =>
  chat.title.toLowerCase().includes(search.toLowerCase())
);

const groupedChats = filteredChats.reduce((acc, chat) => {
  const group = getGroup(chat.created_at);

  if (!acc[group]) acc[group] = [];

  acc[group].push(chat);

  return acc;
}, {});
  return (
    <aside className="w-80 h-screen bg-[#0b1220] text-white border-r border-slate-800 flex flex-col">
      <div className="p-6 border-b border-slate-800">
        <h1 className="text-2xl font-bold">🤖 Onkar AI</h1>
        <p className="text-sm text-slate-400 mt-1">Local AI Assistant</p>
      </div>

      <div className="p-4 space-y-3">
        <button
          onClick={newChat}
          className="w-full bg-blue-600 hover:bg-blue-700 transition p-3 rounded-xl font-semibold"
        >
          + New Chat
        </button>

        <label className="w-full block bg-emerald-600 hover:bg-emerald-700 transition p-3 rounded-xl text-center cursor-pointer font-semibold">
          📎 {uploading ? "Uploading..." : "Upload PDF"}
          <input type="file" accept="application/pdf" hidden onChange={uploadPDF} />
        </label>
      </div>

      <div className="px-5 mt-4 flex-1">
        <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-3">
  Uploaded Files
</h3>

<div className="space-y-2 mb-6">
  {documents.length === 0 ? (
    <p className="text-slate-500 text-sm">No PDF uploaded</p>
  ) : (
   documents.map((doc, index) => (
  <div
    key={index}
    className="bg-slate-900 rounded-lg p-3 flex justify-between items-center"
  >
    <div>
      <p className="text-sm text-white">
        📄 {doc.name}
      </p>

      <p className="text-xs text-slate-500">
        {doc.size} KB
      </p>
    </div>

    <button
      onClick={() => deleteDocument(doc.name)}
      className="text-red-500 hover:text-red-300 text-xl"
      title="Delete PDF"
    >
      🗑️
    </button>
  </div>
))
  )}
</div>
        <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-3">
          Recent Chats
        </h3>
        <input
  type="text"
  placeholder="🔍 Search chats..."
  value={search}
  onChange={(e) => setSearch(e.target.value)}
  className="w-full mb-3 p-2 rounded-lg bg-slate-900 text-white outline-none border border-slate-700"
/>

        <div className="space-y-2">
          {Object.entries(groupedChats).map(([group, groupChats]) => (
  <div key={group} className="mb-5">
    <h4 className="text-xs uppercase text-slate-500 mb-2">
      {group}
    </h4>

    <div className="space-y-2">
      {groupChats.map((chat) => (
        <div
          key={chat.id}
          className={`flex justify-between items-center rounded-lg p-3 cursor-pointer ${
            activeChatId === chat.id
              ? "bg-blue-600"
              : "bg-slate-900 hover:bg-slate-800"
          }`}
        >
          <div
            className="flex-1 overflow-hidden"
            onClick={() => selectChat(chat.id)}
          >
            <p className="text-sm font-medium truncate">
              💬 {chat.title}
            </p>

            <p className="text-xs text-slate-400 truncate mt-1">
              {chat.last_message || "No messages yet"}
            </p>
          </div>

          <div className="flex gap-2">
            <button onClick={() => renameCurrentChat(chat.id)}>
              ✏️
            </button>

            <button onClick={() => deleteCurrentChat(chat.id)}>
              🗑️
            </button>
          </div>
        </div>
      ))}
    </div>
  </div>
))}
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;