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
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert("Speech recognition या browser मध्ये support नाही.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-IN";
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => setListening(true);

    recognition.onresult = (event) => {
      const text = event.results[0][0].transcript;
      setInput(text);
    };

    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    recognition.start();
  }

  function stopListening() {
    recognitionRef.current?.stop();
    setListening(false);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !loading) {
      sendMessage();
    }
  }

  return (
    <div className="p-5 border-t border-slate-800 bg-slate-950 flex gap-3">
      <input
        type="file"
        id="fileUpload"
        hidden
        onChange={uploadFile}
        accept=".pdf,image/*"
      />

      <label
        htmlFor="fileUpload"
        className="bg-slate-800 hover:bg-slate-700 px-4 rounded-xl cursor-pointer flex items-center justify-center"
        title="Upload PDF or image"
      >
        📎
      </label>

      <input
        className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white outline-none"
        placeholder="Ask anything..."
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={loading}
      />

      <button
        type="button"
        onClick={listening ? stopListening : startListening}
        className={`px-4 rounded-xl text-white font-bold ${
          listening ? "bg-red-600" : "bg-purple-600"
        }`}
      >
        {listening ? "🔴 Listening..." : "🎤"}
      </button>

      <button
        type="button"
        onClick={sendMessage}
        disabled={loading || !input.trim()}
        className="bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed px-5 rounded-xl text-white font-bold"
      >
        ➤
      </button>
    </div>
  );
}

export default MessageInput;