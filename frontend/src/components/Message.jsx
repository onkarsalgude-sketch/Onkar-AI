import ReactMarkdown from "react-markdown";
import { useState } from "react";

function Message({ role, content }) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);

  function speak() {
    const speech = new SpeechSynthesisUtterance(content);
    speech.lang = "en-IN";
    speech.rate = 1;
    speech.pitch = 1;

    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(speech);
  }

  async function copyText() {
    await navigator.clipboard.writeText(content);
    setCopied(true);

    setTimeout(() => {
      setCopied(false);
    }, 2000);
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
          <div className="flex gap-2 mt-4">

            <button
              onClick={copyText}
              className="bg-slate-700 hover:bg-slate-600 px-3 py-1 rounded-lg text-sm"
            >
              {copied ? "✅ Copied" : "📋 Copy"}
            </button>

            <button
              onClick={speak}
              className="bg-purple-600 hover:bg-purple-500 px-3 py-1 rounded-lg text-sm"
            >
              🔊 Speak
            </button>

            <button
              className="bg-slate-700 hover:bg-slate-600 px-3 py-1 rounded-lg"
            >
              👍
            </button>

            <button
              className="bg-slate-700 hover:bg-slate-600 px-3 py-1 rounded-lg"
            >
              👎
            </button>

          </div>
        )}
      </div>
    </div>
  );
}

export default Message;