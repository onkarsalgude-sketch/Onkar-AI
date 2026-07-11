import { useRef, useState } from "react";

function MessageInput({
  input,
  setInput,
  sendMessage,
  loading,
  uploadFile,
}) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);

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
      !loading &&
      input.trim()
    ) {
      event.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="flex w-full min-w-0 items-center gap-2 rounded-2xl border border-slate-800 bg-slate-950 p-2 sm:gap-3 sm:p-3">
      <input
        type="file"
        id="fileUpload"
        hidden
        onChange={uploadFile}
        accept=".pdf,image/*"
      />

      {/* Attachment */}
      <label
        htmlFor="fileUpload"
        className="flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-xl bg-slate-800 text-lg transition hover:bg-slate-700 sm:h-11 sm:w-11"
        title="Upload PDF or image"
      >
        📎
      </label>

      {/* Message input */}
      <input
        type="text"
        className="h-10 min-w-0 flex-1 rounded-xl border border-slate-700 bg-slate-900 px-3 text-sm text-white outline-none transition focus:border-blue-500 sm:h-11 sm:px-4 sm:text-base"
        placeholder="Ask anything..."
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
        disabled={loading || !input.trim()}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-green-600 text-lg font-bold text-white transition hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50 sm:h-11 sm:w-11"
        title="Send message"
        aria-label="Send message"
      >
        ➤
      </button>
    </div>
  );
}

export default MessageInput;