function SettingsModal({ open, onClose }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-slate-900 w-[420px] rounded-2xl shadow-xl border border-slate-700">

        <div className="flex justify-between items-center p-5 border-b border-slate-700">
          <h2 className="text-xl font-bold text-white">
            ⚙ Settings
          </h2>

          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-xl"
          >
            ✕
          </button>
        </div>

        <div className="p-5 space-y-3">

          <button className="w-full text-left bg-slate-800 hover:bg-slate-700 rounded-xl p-4">
            🌙 Theme
          </button>

          <button className="w-full text-left bg-slate-800 hover:bg-slate-700 rounded-xl p-4">
            🧹 Clear Memory
          </button>

          <button className="w-full text-left bg-slate-800 hover:bg-slate-700 rounded-xl p-4">
            📤 Export Chat
          </button>

          <button className="w-full text-left bg-slate-800 hover:bg-slate-700 rounded-xl p-4">
            ℹ About
          </button>

        </div>
      </div>
    </div>
  );
}

export default SettingsModal;