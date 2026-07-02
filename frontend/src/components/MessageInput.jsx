function MessageInput({ input, setInput, sendMessage, loading }) {
  return (
    <div className="p-5 border-t border-slate-800 bg-slate-950 flex gap-3">
      <input
        className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white outline-none"
        placeholder="Ask anything..."
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && sendMessage()}
      />

      <button
        onClick={sendMessage}
        disabled={loading}
        className="bg-green-600 hover:bg-green-700 px-5 rounded-xl text-white font-bold"
      >
        ➤
      </button>
    </div>
  );
}

export default MessageInput;