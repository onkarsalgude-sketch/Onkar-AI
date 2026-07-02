import ReactMarkdown from "react-markdown";

function Message({ role, content }) {
  const isUser = role === "user";

  function speak() {
    const speech = new SpeechSynthesisUtterance(content);
    speech.lang = "en-IN";
    speech.rate = 1;
    speech.pitch = 1;

    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(speech);
  }

  return (
    <div className={`flex mb-5 ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-3xl px-5 py-4 rounded-2xl leading-relaxed ${
          isUser
            ? "bg-blue-600 text-white rounded-br-md"
            : "bg-slate-800 text-slate-100 rounded-bl-md"
        }`}
      >
        <ReactMarkdown>{content}</ReactMarkdown>

        {!isUser && (
          <button
            onClick={speak}
            className="mt-3 text-sm bg-purple-600 px-3 py-1 rounded-lg"
          >
            🔊 Speak
          </button>
        )}
      </div>
    </div>
  );
}

export default Message;