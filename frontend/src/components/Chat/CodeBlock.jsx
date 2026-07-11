import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneDark,
  oneLight,
} from "react-syntax-highlighter/dist/esm/styles/prism";

const languageDetails = {
  python: {
    icon: "🐍",
    label: "Python",
  },
  javascript: {
    icon: "🟨",
    label: "JavaScript",
  },
  typescript: {
    icon: "🔷",
    label: "TypeScript",
  },
  jsx: {
    icon: "⚛️",
    label: "React JSX",
  },
  tsx: {
    icon: "⚛️",
    label: "React TSX",
  },
  react: {
    icon: "⚛️",
    label: "React",
  },
  java: {
    icon: "☕",
    label: "Java",
  },
  c: {
    icon: "🔵",
    label: "C",
  },
  cpp: {
    icon: "🔷",
    label: "C++",
  },
  csharp: {
    icon: "🟣",
    label: "C#",
  },
  html: {
    icon: "🌐",
    label: "HTML",
  },
  css: {
    icon: "🎨",
    label: "CSS",
  },
  sql: {
    icon: "🗄️",
    label: "SQL",
  },
  bash: {
    icon: "💻",
    label: "Bash",
  },
  powershell: {
    icon: "💠",
    label: "PowerShell",
  },
  json: {
    icon: "🧩",
    label: "JSON",
  },
  markdown: {
    icon: "📝",
    label: "Markdown",
  },
  yaml: {
    icon: "⚙️",
    label: "YAML",
  },
  text: {
    icon: "📄",
    label: "Text",
  },
};

const languageAliases = {
  js: "javascript",
  ts: "typescript",
  py: "python",
  sh: "bash",
  shell: "bash",
  ps1: "powershell",
  md: "markdown",
  yml: "yaml",
  "c++": "cpp",
  cs: "csharp",
  plaintext: "text",
};

function normalizeLanguage(language) {
  const cleanedLanguage = String(
    language || "text"
  )
    .trim()
    .toLowerCase();

  return (
    languageAliases[cleanedLanguage] ||
    cleanedLanguage ||
    "text"
  );
}

function CodeBlock({
  language = "text",
  value = "",
  theme = "dark",
}) {
  const [copyStatus, setCopyStatus] =
    useState("idle");

  const isDark = theme === "dark";
  const normalizedLanguage =
    normalizeLanguage(language);

  const languageInfo =
    languageDetails[normalizedLanguage] || {
      icon: "💻",
      label:
        normalizedLanguage === "text"
          ? "Text"
          : normalizedLanguage.toUpperCase(),
    };

  const codeValue = String(value || "");
  const lineCount = codeValue
    ? codeValue.split("\n").length
    : 0;

  async function copyCode() {
    if (!codeValue) return;

    try {
      await navigator.clipboard.writeText(
        codeValue
      );

      setCopyStatus("copied");

      window.setTimeout(() => {
        setCopyStatus("idle");
      }, 2000);
    } catch (error) {
      console.error(
        "Copy code failed:",
        error
      );

      setCopyStatus("error");

      window.setTimeout(() => {
        setCopyStatus("idle");
      }, 2000);
    }
  }

  function getCopyButtonText() {
    if (copyStatus === "copied") {
      return "✅ Copied";
    }

    if (copyStatus === "error") {
      return "❌ Failed";
    }

    return "📋 Copy code";
  }

  return (
    <div
      className={`my-4 overflow-hidden rounded-xl border shadow-lg ${
        isDark
          ? "border-slate-700 bg-slate-950"
          : "border-slate-300 bg-slate-50"
      }`}
    >
      {/* Code header */}
      <div
        className={`flex items-center justify-between gap-3 border-b px-4 py-2.5 ${
          isDark
            ? "border-slate-700 bg-slate-900"
            : "border-slate-300 bg-slate-100"
        }`}
      >
        <div className="flex min-w-0 items-center gap-2">
          <span aria-hidden="true">
            {languageInfo.icon}
          </span>

          <span
            className={`truncate text-xs font-semibold uppercase tracking-wide ${
              isDark
                ? "text-slate-300"
                : "text-slate-700"
            }`}
          >
            {languageInfo.label}
          </span>

          {lineCount > 0 && (
            <span
              className={`hidden text-xs sm:inline ${
                isDark
                  ? "text-slate-500"
                  : "text-slate-500"
              }`}
            >
              {lineCount}{" "}
              {lineCount === 1
                ? "line"
                : "lines"}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={copyCode}
          disabled={!codeValue}
          className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
            copyStatus === "copied"
              ? "bg-emerald-600 text-white"
              : copyStatus === "error"
                ? "bg-red-600 text-white"
                : isDark
                  ? "bg-slate-700 text-slate-200 hover:bg-slate-600"
                  : "bg-white text-slate-700 shadow-sm hover:bg-slate-200"
          }`}
          aria-label={`Copy ${languageInfo.label} code`}
        >
          {getCopyButtonText()}
        </button>
      </div>

      {/* Highlighted code */}
      <div className="overflow-x-auto">
        <SyntaxHighlighter
          language={normalizedLanguage}
          style={
            isDark ? oneDark : oneLight
          }
          showLineNumbers={lineCount > 1}
          wrapLongLines={false}
          customStyle={{
            margin: 0,
            padding: "18px",
            background: "transparent",
            fontSize: "14px",
            lineHeight: "1.6",
            minWidth: "100%",
          }}
          codeTagProps={{
            style: {
              fontFamily:
                "'Consolas', 'Monaco', 'Courier New', monospace",
            },
          }}
          lineNumberStyle={{
            minWidth: "2.5em",
            paddingRight: "1em",
            opacity: 0.5,
            userSelect: "none",
          }}
        >
          {codeValue}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

export default CodeBlock;