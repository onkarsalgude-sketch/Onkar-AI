import ReactMarkdown from "react-markdown";
import { useState } from "react";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import CodeBlock from "./CodeBlock";
import SourcesCard from "./SourcesCard";

function Message({
  role,
  content,
  imageUrl,
  fileName,
  sources = [],
  regenerateResponse,
  isLast,
}) {
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
       {imageUrl && (
  <div className="mb-3">
    <img
      src={imageUrl}
      alt={fileName}
      className="rounded-xl max-h-80 max-w-full border border-slate-700"
    />

    <p className="text-xs text-slate-400 mt-2">
      📷 {fileName}
    </p>
  </div>
)}
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            code({ inline, className, children, ...props }) {
              const match = /language-(\w+)/.exec(className || "");

              return !inline && match ? (
                <CodeBlock
                  language={match[1]}
                  value={String(children).replace(/\n$/, "")}
                />
              ) : (
                <code className="bg-slate-900 px-1 py-0.5 rounded">
                  {children}
                </code>
              );
            },
          }}
        >
          {content}
        </ReactMarkdown>
        {!isUser && <SourcesCard sources={sources} />}

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
            {isLast && (
  <button
    onClick={regenerateResponse}
    className="bg-blue-600 hover:bg-blue-500 px-3 py-1 rounded-lg text-sm"
  >
    🔄 Regenerate
  </button>
)}

          </div>
        )}
      </div>
    </div>
  );
}

export default Message;