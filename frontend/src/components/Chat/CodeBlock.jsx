import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

const languageIcons = {
  python: "🐍",
  javascript: "🟨",
  js: "🟨",
  jsx: "⚛️",
  react: "⚛️",
  java: "☕",
  html: "🌐",
  css: "🎨",
  sql: "🗄️",
  bash: "💻",
  json: "🧩",
};

function CodeBlock({ language = "text", value }) {
  const [copied, setCopied] = useState(false);

  const lang = language.toLowerCase();
  const icon = languageIcons[lang] || "💻";

  async function copyCode() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="my-4 rounded-xl overflow-hidden border border-slate-700 bg-slate-950 shadow-lg">
      <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-700">
        <span className="text-xs font-semibold text-slate-300 uppercase">
          {icon} {language}
        </span>

        <button
          onClick={copyCode}
          className={`text-xs px-3 py-1 rounded-lg transition ${
            copied
              ? "bg-emerald-600 text-white"
              : "bg-slate-700 hover:bg-slate-600 text-slate-200"
          }`}
        >
          {copied ? "✅ Copied" : "📋 Copy"}
        </button>
      </div>

      <div className="overflow-x-auto">
        <SyntaxHighlighter
          language={language}
          style={oneDark}
          showLineNumbers
          wrapLongLines
          customStyle={{
            margin: 0,
            padding: "18px",
            background: "transparent",
            fontSize: "14px",
          }}
        >
          {value}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

export default CodeBlock;