function Sidebar({
  uploadPDF,
  uploading,
  newChat,
  documents,
  deleteDocument,
}) {
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

        <div className="space-y-2 text-sm">
          <div className="p-3 rounded-lg bg-slate-900 text-slate-300">📄 Resume Chat</div>
          <div className="p-3 rounded-lg hover:bg-slate-900 cursor-pointer text-slate-400">🤖 IBM Project</div>
          <div className="p-3 rounded-lg hover:bg-slate-900 cursor-pointer text-slate-400">🐍 Python Notes</div>
        </div>
      </div>

      <div className="p-5 border-t border-slate-800 text-xs text-slate-500">
        Model: llama3.2:3b
      </div>
    </aside>
  );
}

export default Sidebar;