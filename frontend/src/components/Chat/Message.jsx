import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import CodeBlock from "./CodeBlock";
import SourcesCard from "./SourcesCard";

function Message({
  role,
  content = "",
  imageUrl,
  fileName,
  fileType,
  fileSize,
  sources = [],
  regenerateResponse,
  isLast,
  theme = "dark",
}) {
  const isUser = role === "user";
  const isDark = theme === "dark";

  const [copied, setCopied] = useState(false);

  function speak() {
    if (!content.trim()) return;

    const speech = new SpeechSynthesisUtterance(content);

    speech.lang = "en-IN";
    speech.rate = 1;
    speech.pitch = 1;

    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(speech);
  }

  async function copyText() {
    if (!content.trim()) return;

    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);

      setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch (error) {
      console.error("Copy failed:", error);
    }
  }

  return (
    <div
      className={`mb-5 flex ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      <div
        className={`max-w-[90%] rounded-2xl px-4 py-3 leading-relaxed sm:max-w-3xl sm:px-5 sm:py-4 ${
          isUser
            ? "rounded-br-md bg-blue-600 text-white"
            : isDark
              ? "rounded-bl-md border border-slate-700 bg-slate-800 text-slate-100"
              : "rounded-bl-md border border-slate-200 bg-white text-slate-900 shadow-sm"
        }`}
      >
        {/* Image preview */}
        {imageUrl && (
          <div className="mb-3">
            <img
              src={imageUrl}
              alt={fileName || "Uploaded image"}
              className={`max-h-80 max-w-full rounded-xl border ${
                isDark
                  ? "border-slate-700"
                  : "border-slate-200"
              }`}
            />

            <p
              className={`mt-2 text-xs ${
                isUser
                  ? "text-blue-100"
                  : isDark
                    ? "text-slate-400"
                    : "text-slate-500"
              }`}
            >
              📷 {fileName || "Uploaded image"}
            </p>
          </div>
        )}

        {/* PDF preview */}
        {fileType === "pdf" && (
          <div
            className={`mb-3 flex items-center gap-3 rounded-xl border p-3 ${
              isUser
                ? "border-blue-400/50 bg-blue-700/40"
                : isDark
                  ? "border-slate-600 bg-slate-900"
                  : "border-slate-200 bg-slate-100"
            }`}
          >
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-red-500/20 text-2xl">
              📄
            </div>

            <div className="min-w-0">
              <p
                className={`max-w-64 truncate font-medium ${
                  isUser
                    ? "text-white"
                    : isDark
                      ? "text-slate-100"
                      : "text-slate-900"
                }`}
              >
                {fileName || "Uploaded PDF"}
              </p>

              <p
                className={`text-xs ${
                  isUser
                    ? "text-blue-100"
                    : isDark
                      ? "text-slate-400"
                      : "text-slate-500"
                }`}
              >
                PDF document
                {fileSize ? ` • ${fileSize}` : ""}
              </p>
            </div>
          </div>
        )}

        {/* Message content */}
        {content && (
          <div className="break-words">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({
                  inline,
                  className,
                  children,
                  ...props
                }) {
                  const match = /language-(\w+)/.exec(
                    className || ""
                  );

                  return !inline && match ? (
                    <CodeBlock
  language={match[1]}
  value={String(children).replace(
    /\n$/,
    ""
  )}
  theme={theme}
/>
                  ) : (
                    <code
                      className={`rounded px-1 py-0.5 ${
                        isUser
                          ? "bg-blue-800/50"
                          : isDark
                            ? "bg-slate-950"
                            : "bg-slate-200"
                      }`}
                      {...props}
                    >
                      {children}
                    </code>
                  );
                },

                a({ children, href }) {
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={
                        isUser
                          ? "text-white underline"
                          : "text-blue-500 underline"
                      }
                    >
                      {children}
                    </a>
                  );
                },
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        )}

        {!isUser && (
          <SourcesCard
            sources={sources}
            theme={theme}
          />
        )}

        {/* Assistant actions */}
        {!isUser && content && (
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={copyText}
              className={`rounded-lg px-3 py-1 text-sm transition ${
                isDark
                  ? "bg-slate-700 hover:bg-slate-600"
                  : "bg-slate-200 hover:bg-slate-300"
              }`}
            >
              {copied ? "✅ Copied" : "📋 Copy"}
            </button>

            <button
              type="button"
              onClick={speak}
              className="rounded-lg bg-purple-600 px-3 py-1 text-sm text-white transition hover:bg-purple-500"
            >
              🔊 Speak
            </button>

            <button
              type="button"
              className={`rounded-lg px-3 py-1 transition ${
                isDark
                  ? "bg-slate-700 hover:bg-slate-600"
                  : "bg-slate-200 hover:bg-slate-300"
              }`}
              title="Helpful"
            >
              👍
            </button>

            <button
              type="button"
              className={`rounded-lg px-3 py-1 transition ${
                isDark
                  ? "bg-slate-700 hover:bg-slate-600"
                  : "bg-slate-200 hover:bg-slate-300"
              }`}
              title="Not helpful"
            >
              👎
            </button>

            {isLast && (
              <button
                type="button"
                onClick={regenerateResponse}
                className="rounded-lg bg-blue-600 px-3 py-1 text-sm text-white transition hover:bg-blue-500"
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