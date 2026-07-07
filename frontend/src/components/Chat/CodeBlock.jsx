import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

function CodeBlock({ language, value }) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    await navigator.clipboard.writeText(value);

    setCopied(true);

    setTimeout(() => {
      setCopied(false);
    }, 2000);
  }

  return (
    <div className="relative my-3">

      <div className="absolute top-2 right-2 flex gap-2">

        <span className="text-xs bg-slate-700 px-2 py-1 rounded">
          {language}
        </span>

        <button
          onClick={copyCode}
          className="bg-slate-700 hover:bg-slate-600 text-xs px-2 py-1 rounded"
        >
          {copied ? "✅ Copied" : "📋 Copy"}
        </button>

      </div>

      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          borderRadius: "12px",
          paddingTop: "45px",
        }}
      >
        {value}
      </SyntaxHighlighter>

    </div>
  );
}

export default CodeBlock;