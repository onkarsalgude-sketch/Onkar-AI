function SettingsModal({
  open,
  onClose,
  theme = "dark",
  onThemeChange,
}) {
  if (!open) return null;

  const isDark = theme === "dark";

  function handleOverlayClick(event) {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }

  return (
    <div
      onClick={handleOverlayClick}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm"
    >
      <div
        className={`w-full max-w-md rounded-2xl border shadow-2xl ${
          isDark
            ? "border-slate-700 bg-slate-900 text-white"
            : "border-slate-200 bg-white text-slate-900"
        }`}
      >
        {/* Header */}
        <div
          className={`flex items-center justify-between border-b p-5 ${
            isDark
              ? "border-slate-700"
              : "border-slate-200"
          }`}
        >
          <div>
            <h2 className="text-xl font-bold">
              ⚙ Settings
            </h2>

            <p
              className={`mt-1 text-sm ${
                isDark
                  ? "text-slate-400"
                  : "text-slate-500"
              }`}
            >
              Customize your Onkar AI experience
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className={`rounded-lg p-2 text-xl transition ${
              isDark
                ? "text-slate-400 hover:bg-slate-800 hover:text-white"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            }`}
            aria-label="Close settings"
          >
            ✕
          </button>
        </div>

        <div className="space-y-5 p-5">
          {/* Theme */}
          <section>
            <h3 className="mb-3 text-sm font-semibold">
              🎨 Appearance
            </h3>

            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => onThemeChange?.("dark")}
                className={`rounded-xl border p-4 text-left transition ${
                  theme === "dark"
                    ? "border-blue-500 bg-blue-500/15"
                    : isDark
                      ? "border-slate-700 bg-slate-800 hover:bg-slate-700"
                      : "border-slate-200 bg-slate-50 hover:bg-slate-100"
                }`}
              >
                <div className="text-2xl">🌙</div>

                <p className="mt-2 font-semibold">
                  Dark
                </p>

                <p
                  className={`mt-1 text-xs ${
                    isDark
                      ? "text-slate-400"
                      : "text-slate-500"
                  }`}
                >
                  Easier on the eyes
                </p>
              </button>

              <button
                type="button"
                onClick={() => onThemeChange?.("light")}
                className={`rounded-xl border p-4 text-left transition ${
                  theme === "light"
                    ? "border-blue-500 bg-blue-500/15"
                    : isDark
                      ? "border-slate-700 bg-slate-800 hover:bg-slate-700"
                      : "border-slate-200 bg-slate-50 hover:bg-slate-100"
                }`}
              >
                <div className="text-2xl">☀️</div>

                <p className="mt-2 font-semibold">
                  Light
                </p>

                <p
                  className={`mt-1 text-xs ${
                    isDark
                      ? "text-slate-400"
                      : "text-slate-500"
                  }`}
                >
                  Bright and clean
                </p>
              </button>
            </div>
          </section>

          {/* Other settings */}
          <section className="space-y-2">
            <button
              type="button"
              className={`w-full rounded-xl p-4 text-left transition ${
                isDark
                  ? "bg-slate-800 hover:bg-slate-700"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              🧹 Clear Memory
            </button>

            <button
              type="button"
              className={`w-full rounded-xl p-4 text-left transition ${
                isDark
                  ? "bg-slate-800 hover:bg-slate-700"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              📤 Export Chat
            </button>

            <button
              type="button"
              className={`w-full rounded-xl p-4 text-left transition ${
                isDark
                  ? "bg-slate-800 hover:bg-slate-700"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              ℹ About
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}

export default SettingsModal;