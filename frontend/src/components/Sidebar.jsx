function Sidebar({ uploadPDF, uploading, newChat }) {
  return (
    <div className="w-72 bg-slate-950 text-white h-screen p-5">
      <h1 className="text-3xl font-bold">🤖 Onkar AI</h1>

      <button onClick={newChat} className="bg-blue-600 w-full mt-8 p-3 rounded-xl">
        + New Chat
      </button>

      <label className="bg-green-600 w-full mt-4 p-3 rounded-xl block text-center cursor-pointer">
        📎 {uploading ? "Uploading..." : "Upload PDF"}
        <input type="file" accept="application/pdf" hidden onChange={uploadPDF} />
      </label>

      <div className="mt-10">
        <h3 className="text-gray-400">Recent Chats</h3>
        <p className="mt-4">📄 Resume</p>
        <p>🤖 IBM Project</p>
        <p>🐍 Python Notes</p>
      </div>
    </div>
  );
}

export default Sidebar;