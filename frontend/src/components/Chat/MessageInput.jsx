import { useRef, useState } from "react";

function MessageInput({
  input,
  setInput,
  sendMessage,
  loading,
  uploadingPdf,
  uploadFile,
  pendingFile,
  removePendingFile,
  theme = "dark",
}) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);

  const isDark = theme === "dark";
  const canSend =
    !loading && (input.trim() || pendingFile);

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
      {/* Send करण्यापूर्वी निवडलेली PDF */}
      {pendingFile && (
        <div
          className={`mb-2 flex items-center justify-between gap-3 rounded-xl border p-3 ${
            isDark
              ? "border-slate-700 bg-slate-900"
              : "border-slate-200 bg-slate-100"
          }`}
        >
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-red-500/15 text-2xl">
              📄
            </div>

            <div className="min-w-0">
              <p
                className={`truncate text-sm font-medium ${
                  isDark
                    ? "text-slate-100"
                    : "text-slate-900"
                }`}
                title={pendingFile.fileName}
              >
                {pendingFile.fileName}
              </p>

              <p className="mt-1 text-xs text-slate-500">
                PDF · {pendingFile.fileSize}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={removePendingFile}
            disabled={loading}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-lg transition ${
              isDark
                ? "text-slate-400 hover:bg-slate-800 hover:text-white"
                : "text-slate-500 hover:bg-slate-200 hover:text-slate-900"
            }`}
            title="Remove PDF"
            aria-label="Remove PDF"
          >
            ✕
          </button>
        </div>
      )}

      {uploadingPdf && (
        <div
          className={`mb-2 flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${
            isDark
              ? "border-blue-500/30 bg-blue-500/10 text-blue-300"
              : "border-blue-200 bg-blue-50 text-blue-700"
          }`}
        >
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />

          <span>
            Uploading and processing PDF...
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
          disabled={loading}
        />

        {/* Attachment */}
        <label
          htmlFor="fileUpload"
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg transition sm:h-11 sm:w-11 ${
            loading
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
            pendingFile
              ? "Ask something about this PDF..."
              : "Ask anything..."
          }
          value={input}
          onChange={(event) =>
            setInput(event.target.value)
          }
          onKeyDown={handleKeyDown}
          disabled={loading}
        />

        {/* Microphone */}
        <button
          type="button"
          onClick={
            listening ? stopListening : startListening
          }
          disabled={loading}
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