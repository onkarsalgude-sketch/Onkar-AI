import { useRef, useState } from "react";

function MessageInput({
  input,
  setInput,
  sendMessage,
  loading,
  agents = [],
  agentsLoading = false,
  agentsAvailable = false,
  selectedAgentId = "",
  onAgentChange,
  uploadProgress,
  uploadSummary,
  dismissUploadSummary,
  uploadFile,
  pendingFiles,
  removePendingFileAt,
  clearAllPendingFiles,
  theme = "dark",
}) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);

  const isDark = theme === "dark";
  const isBusy = loading || uploadProgress !== null;
  const selectedAgent =
    agents.find(
      (agent) =>
        agent.agent_id ===
        selectedAgentId
    ) || null;
  const canSend =
    !isBusy && (input.trim() || pendingFiles.length > 0);

  function startListening() {
    const SpeechRecognition =
      window.SpeechRecognition ||
      window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert(
        "Speech recognition या browser मध्ये support नाही."
      );
      return;
    }

    const recognition = new SpeechRecognition();

    recognition.lang = "en-IN";
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
      setListening(true);
    };

    recognition.onresult = (event) => {
      const text = event.results[0][0].transcript;
      setInput(text);
    };

    recognition.onerror = (event) => {
      console.error(
        "Speech recognition error:",
        event.error
      );
      setListening(false);
    };

    recognition.onend = () => {
      setListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
  }

  function stopListening() {
    recognitionRef.current?.stop();
    setListening(false);
  }

  function handleKeyDown(event) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      canSend
    ) {
      event.preventDefault();
      sendMessage();
    }
  }

  return (
    <div
      className={`w-full rounded-2xl border p-2 transition-colors sm:p-3 ${
        isDark
          ? "border-slate-800 bg-slate-950"
          : "border-slate-300 bg-white shadow-sm"
      }`}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <label
          htmlFor="agentPicker"
          className={`text-xs font-semibold ${
            isDark
              ? "text-slate-300"
              : "text-slate-700"
          }`}
        >
          Agent
        </label>

        <select
          id="agentPicker"
          value={selectedAgentId}
          onChange={(event) =>
            onAgentChange?.(
              event.target.value
            )
          }
          disabled={
            agentsLoading ||
            !agentsAvailable
          }
          className={`min-w-0 flex-1 rounded-lg border px-3 py-2 text-sm outline-none transition focus:border-blue-500 disabled:cursor-not-allowed disabled:opacity-60 sm:max-w-xs ${
            isDark
              ? "border-slate-700 bg-slate-900 text-white"
              : "border-slate-300 bg-slate-50 text-slate-900"
          }`}
          aria-label="Select chat agent"
        >
          <option value="">
            {agentsLoading
              ? "Loading agents..."
              : agentsAvailable
                ? "Automatic (no agent)"
                : "Automatic (catalog unavailable)"}
          </option>

          {agents.map((agent) => (
            <option
              key={agent.agent_id}
              value={agent.agent_id}
            >
              {agent.name}
            </option>
          ))}
        </select>

        {!agentsLoading &&
          !agentsAvailable && (
            <span
              className={`text-xs ${
                isDark
                  ? "text-slate-500"
                  : "text-slate-500"
              }`}
            >
              Agent catalog unavailable. Chat stays automatic.
            </span>
          )}
      </div>

      {selectedAgent && (
        <div
          className={`mb-2 rounded-xl border px-3 py-2 text-xs ${
            isDark
              ? "border-blue-500/30 bg-blue-500/10 text-slate-200"
              : "border-blue-200 bg-blue-50 text-slate-700"
          }`}
        >
          <p className="font-semibold">
            {selectedAgent.name}
          </p>

          <p className="mt-1">
            {selectedAgent.description}
          </p>

          {selectedAgent.capabilities.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {selectedAgent.capabilities.map(
                (capability) => (
                  <span
                    key={capability}
                    className={`rounded-full px-2 py-1 ${
                      isDark
                        ? "bg-slate-800 text-slate-300"
                        : "bg-white text-slate-600"
                    }`}
                  >
                    {capability}
                  </span>
                )
              )}
            </div>
          )}
        </div>
      )}

      {/* Upload summary banner */}
      {uploadSummary && (
        <div
          className={`mb-2 rounded-xl border px-3 py-2 text-xs ${
            isDark
              ? "border-slate-700 bg-slate-900 text-slate-200"
              : "border-slate-200 bg-slate-50 text-slate-800"
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="font-semibold mb-1">Upload summary</p>
              {uploadSummary.succeeded.length > 0 && (
                <p className="text-emerald-500">
                  ✓ {uploadSummary.succeeded.length} uploaded
                  {uploadSummary.succeeded.length <= 3
                    ? `: ${uploadSummary.succeeded.join(", ")}`
                    : ""}
                </p>
              )}
              {uploadSummary.duplicates.length > 0 && (
                <p className={isDark ? "text-amber-400" : "text-amber-600"}>
                  ⊘ {uploadSummary.duplicates.length} duplicate
                  {uploadSummary.duplicates.length <= 3
                    ? `: ${uploadSummary.duplicates.join(", ")}`
                    : ""}
                </p>
              )}
              {uploadSummary.failed.length > 0 && (
                <p className="text-red-500">
                  ✗ {uploadSummary.failed.length} failed
                  {uploadSummary.failed.length <= 3
                    ? `: ${uploadSummary.failed.join(", ")}`
                    : ""}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={dismissUploadSummary}
              className={`shrink-0 rounded p-1 text-base leading-none transition ${
                isDark
                  ? "text-slate-400 hover:text-white"
                  : "text-slate-500 hover:text-slate-900"
              }`}
              aria-label="Dismiss upload summary"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Pending PDFs list */}
      {pendingFiles.length > 0 && (
        <div className="mb-2 space-y-1">
          {pendingFiles.length > 1 && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={clearAllPendingFiles}
                disabled={isBusy}
                className={`text-xs px-2 py-0.5 rounded transition disabled:opacity-50 ${
                  isDark
                    ? "text-slate-400 hover:text-white"
                    : "text-slate-500 hover:text-slate-900"
                }`}
              >
                Clear all
              </button>
            </div>
          )}
          {pendingFiles.map((pf, idx) => (
            <div
              key={`${pf.fileName}__${pf.file.size}__${idx}`}
              className={`flex items-center justify-between gap-3 rounded-xl border p-3 ${
                isDark
                  ? "border-slate-700 bg-slate-900"
                  : "border-slate-200 bg-slate-100"
              }`}
            >
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-500/15 text-xl">
                  📄
                </div>

                <div className="min-w-0">
                  <p
                    className={`truncate text-sm font-medium ${
                      isDark
                        ? "text-slate-100"
                        : "text-slate-900"
                    }`}
                    title={pf.fileName}
                  >
                    {pf.fileName}
                  </p>
                  <p className="text-xs text-slate-500">
                    PDF · {pf.fileSize}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => removePendingFileAt(idx)}
                disabled={isBusy}
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-lg transition disabled:opacity-50 ${
                  isDark
                    ? "text-slate-400 hover:bg-slate-800 hover:text-white"
                    : "text-slate-500 hover:bg-slate-200 hover:text-slate-900"
                }`}
                title="Remove PDF"
                aria-label={`Remove ${pf.fileName}`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Upload progress banner */}
      {uploadProgress && (
        <div
          className={`mb-2 flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${
            isDark
              ? "border-blue-500/30 bg-blue-500/10 text-blue-300"
              : "border-blue-200 bg-blue-50 text-blue-700"
          }`}
        >
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          <span>
            Uploading PDF {uploadProgress.current} of{" "}
            {uploadProgress.total}
            {uploadProgress.total <= 5
              ? `: ${uploadProgress.fileName}`
              : "..."}
          </span>
        </div>
      )}

      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <input
          type="file"
          id="fileUpload"
          hidden
          onChange={uploadFile}
          accept=".pdf,image/*"
          multiple
          disabled={isBusy}
        />

        {/* Attachment */}
        <label
          htmlFor="fileUpload"
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg transition sm:h-11 sm:w-11 ${
            isBusy
              ? "cursor-not-allowed opacity-50"
              : "cursor-pointer"
          } ${
            isDark
              ? "bg-slate-800 hover:bg-slate-700"
              : "bg-slate-200 hover:bg-slate-300"
          }`}
          title="Attach PDF or image"
        >
          📎
        </label>

        {/* Text input */}
        <input
          type="text"
          className={`h-10 min-w-0 flex-1 rounded-xl border px-3 text-sm outline-none transition focus:border-blue-500 sm:h-11 sm:px-4 sm:text-base ${
            isDark
              ? "border-slate-700 bg-slate-900 text-white placeholder:text-slate-500"
              : "border-slate-300 bg-slate-50 text-slate-900 placeholder:text-slate-400"
          }`}
          placeholder={
            pendingFiles.length > 0
              ? "Ask something about these PDFs..."
              : "Ask anything..."
          }
          value={input}
          onChange={(event) =>
            setInput(event.target.value)
          }
          onKeyDown={handleKeyDown}
          disabled={isBusy}
        />

        {/* Microphone */}
        <button
          type="button"
          onClick={
            listening ? stopListening : startListening
          }
          disabled={isBusy}
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg text-white transition disabled:cursor-not-allowed disabled:opacity-50 sm:h-11 sm:w-11 ${
            listening
              ? "animate-pulse bg-red-600 hover:bg-red-700"
              : "bg-purple-600 hover:bg-purple-700"
          }`}
          title={
            listening
              ? "Stop listening"
              : "Start voice input"
          }
          aria-label={
            listening
              ? "Stop listening"
              : "Start voice input"
          }
        >
          {listening ? "🔴" : "🎤"}
        </button>

        {/* Send */}
        <button
          type="button"
          onClick={sendMessage}
          disabled={!canSend}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-green-600 text-lg font-bold text-white transition hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50 sm:h-11 sm:w-11"
          title="Send message"
          aria-label="Send message"
        >
          ➤
        </button>
      </div>
    </div>
  );
}

export default MessageInput;