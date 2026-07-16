import { jsPDF } from "jspdf";
import ChatBackupImport from "./ChatBackupImport";

function SettingsModal({
  open,
  onClose,
  theme = "dark",
  onThemeChange,
  messages = [],
  activeChat = null,
  restoreChatBackup,

  models = [],
  defaultModel = "",
  selectedModel = "",
  onModelChange,
}) {
  if (!open) return null;

  const isDark = theme === "dark";

  const activeModelId =
    selectedModel || defaultModel || "";

  const activeModel = models.find(
    (model) => model.id === activeModelId
  );

const activeChatTitle =
  String(
    activeChat?.title ||
      "Onkar AI Chat"
  ).trim() || "Onkar AI Chat";

  const exportableMessages = messages.filter(
    (message) =>
      message?.content?.trim() ||
      message?.fileName
  );

  const hasMessages =
    exportableMessages.length > 0;

  function handleModelChange(event) {
    const modelId = event.target.value;

    if (!modelId) return;

    onModelChange?.(modelId);
  }

 function sanitizeFileName(value) {
  return String(
    value || "onkar-ai-chat"
  )
    .trim()
    .replace(
      /[<>:"/\\|?*\u0000-\u001F]/g,
      "-"
    )
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80) ||
    "onkar-ai-chat";
}

function getFileName() {
  const now = new Date();

  const date = now
    .toISOString()
    .slice(0, 19)
    .replace("T", "-")
    .replaceAll(":", "-");

  return `${sanitizeFileName(
    activeChatTitle
  )}-${date}`;
}

  function getRoleName(role) {
    return role === "user"
      ? "You"
      : "Onkar AI";
  }

  function getSourceText(source) {
    if (typeof source === "string") {
      return source;
    }

    if (source?.filename) {
      return `${source.filename}${
        source.page
          ? ` — Page ${source.page}`
          : ""
      }`;
    }

    if (source?.url) {
      return `${
        source.title ||
        source.domain ||
        "Web source"
      } — ${source.url}`;
    }

    return source?.title || "Source";
  }

  function createMarkdown() {
    const lines = [
      "# Onkar AI Chat Export",
      "",
      `Exported: ${new Date().toLocaleString()}`,
      "",
      "---",
      "",
    ];

    exportableMessages.forEach(
      (message) => {
        lines.push(
          `## ${getRoleName(message.role)}`,
          ""
        );

        if (message.fileName) {
          lines.push(
            `**Attachment:** ${message.fileName}${
              message.fileSize
                ? ` (${message.fileSize})`
                : ""
            }`,
            ""
          );
        }

        if (message.content?.trim()) {
          lines.push(
            message.content.trim(),
            ""
          );
        }

        if (
          Array.isArray(message.sources) &&
          message.sources.length > 0
        ) {
          lines.push("### Sources", "");

          message.sources.forEach(
            (source) => {
              if (
                typeof source !== "string" &&
                source?.url
              ) {
                lines.push(
                  `- [${
                    source.title ||
                    source.domain ||
                    "Web source"
                  }](${source.url})`
                );
              } else {
                lines.push(
                  `- ${getSourceText(source)}`
                );
              }
            }
          );

          lines.push("");
        }

        lines.push("---", "");
      }
    );

    return lines.join("\n");
  }

  function exportMarkdown() {
    if (!hasMessages) {
      alert("There is no chat to export.");
      return;
    }

    const markdown = createMarkdown();

    const blob = new Blob([markdown], {
      type: "text/markdown;charset=utf-8",
    });

    const downloadUrl =
      URL.createObjectURL(blob);

    const link =
      document.createElement("a");

    link.href = downloadUrl;
    link.download = `${getFileName()}.md`;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(downloadUrl);
  }

  function normalizeBackupSource(source) {
  if (typeof source === "string") {
    return {
      type: "internet",
      title: source,
      url: source,
    };
  }

  if (
    !source ||
    typeof source !== "object"
  ) {
    return null;
  }

  const parsedPage = Number.parseInt(
    String(source.page ?? ""),
    10
  );

  return {
    type:
      source.type ||
      (source.filename
        ? "pdf"
        : source.url
        ? "internet"
        : "unknown"),

    title: source.title || null,
    filename:
      source.filename || null,

    page:
      Number.isFinite(parsedPage) &&
      parsedPage >= 1
        ? parsedPage
        : null,

    url: source.url || null,
    domain: source.domain || null,
    chat_id:
      source.chat_id ??
      source.chatId ??
      null,
  };
}

function createJsonBackup() {
  return {
    schema_version: 1,
    application: "Onkar AI",
    exported_at:
      new Date().toISOString(),

    chat: {
      id: activeChat?.id ?? null,
      title: activeChatTitle,
      created_at:
        activeChat?.created_at ||
        null,
      is_pinned: Boolean(
        activeChat?.is_pinned
      ),
      folder_id:
        activeChat?.folder_id ??
        null,
      folder_name:
        activeChat?.folder_name ||
        null,
    },

    model: {
      selected_id:
        activeModelId || null,
      selected_name:
        activeModel?.name || null,
      default_id:
        defaultModel || null,
    },

    messages:
      exportableMessages.map(
        (message, index) => ({
          index: index + 1,
          role: message.role,
          content:
            message.content || "",
          model_id:
            message.modelId ||
            message.model_id ||
            null,
          created_at:
            message.created_at ||
            null,

          attachment:
            message.fileName
              ? {
                  filename:
                    message.fileName,
                  type:
                    message.fileType ||
                    null,
                  size:
                    message.fileSize ||
                    null,
                }
              : null,

          sources: Array.isArray(
            message.sources
          )
            ? message.sources
                .map(
                  normalizeBackupSource
                )
                .filter(Boolean)
            : [],
        })
      ),
  };
}

function exportJSON() {
  if (!hasMessages) {
    alert(
      "There is no chat to export."
    );
    return;
  }

  const backup =
    createJsonBackup();

  const blob = new Blob(
    [
      JSON.stringify(
        backup,
        null,
        2
      ),
    ],
    {
      type: "application/json;charset=utf-8",
    }
  );

  const downloadUrl =
    URL.createObjectURL(blob);

  const link =
    document.createElement("a");

  link.href = downloadUrl;
  link.download = `${getFileName()}.json`;

  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(
    downloadUrl
  );
}

  function cleanTextForPDF(text) {
    return String(text || "")
      .replace(
        /```[\w-]*\n?([\s\S]*?)```/g,
        "$1"
      )
      .replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        "$1 ($2)"
      )
      .replace(/`([^`]+)`/g, "$1")
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/[*_~]/g, "")
      .replace(/\r/g, "");
  }

  function exportPDF() {
    if (!hasMessages) {
      alert("There is no chat to export.");
      return;
    }

    const pdf = new jsPDF({
      orientation: "portrait",
      unit: "mm",
      format: "a4",
      compress: true,
    });

    const pageWidth =
      pdf.internal.pageSize.getWidth();

    const pageHeight =
      pdf.internal.pageSize.getHeight();

    const margin = 15;
    const usableWidth =
      pageWidth - margin * 2;

    let yPosition = 18;

    function addNewPage() {
      pdf.addPage();
      yPosition = margin;
    }

    function ensureSpace(
      requiredHeight = 8
    ) {
      if (
        yPosition + requiredHeight >
        pageHeight - margin
      ) {
        addNewPage();
      }
    }

    function addWrappedText(
      text,
      {
        fontSize = 10,
        fontStyle = "normal",
        color = [30, 41, 59],
        lineHeight = 5,
        spaceAfter = 3,
      } = {}
    ) {
      const cleanedText =
        cleanTextForPDF(text);

      if (!cleanedText.trim()) return;

      pdf.setFont(
        "helvetica",
        fontStyle
      );

      pdf.setFontSize(fontSize);
      pdf.setTextColor(...color);

      const lines = pdf.splitTextToSize(
        cleanedText,
        usableWidth
      );

      lines.forEach((line) => {
        ensureSpace(lineHeight);

        pdf.text(
          String(line),
          margin,
          yPosition
        );

        yPosition += lineHeight;
      });

      yPosition += spaceAfter;
    }

    pdf.setProperties({
      title: "Onkar AI Chat Export",
      subject:
        "Exported conversation from Onkar AI",
      author: "Onkar AI",
      creator: "Onkar AI",
    });

    addWrappedText(
      "Onkar AI Chat Export",
      {
        fontSize: 18,
        fontStyle: "bold",
        color: [37, 99, 235],
        lineHeight: 8,
        spaceAfter: 2,
      }
    );

    addWrappedText(
      `Exported: ${new Date().toLocaleString()}`,
      {
        fontSize: 9,
        color: [100, 116, 139],
        spaceAfter: 7,
      }
    );

    exportableMessages.forEach(
      (message) => {
        ensureSpace(15);

        const isUser =
          message.role === "user";

        addWrappedText(
          getRoleName(message.role),
          {
            fontSize: 11,
            fontStyle: "bold",
            color: isUser
              ? [37, 99, 235]
              : [79, 70, 229],
            lineHeight: 6,
            spaceAfter: 1,
          }
        );

        if (message.fileName) {
          addWrappedText(
            `Attachment: ${
              message.fileName
            }${
              message.fileSize
                ? ` (${message.fileSize})`
                : ""
            }`,
            {
              fontSize: 9,
              color: [100, 116, 139],
              spaceAfter: 3,
            }
          );
        }

        if (message.content?.trim()) {
          addWrappedText(
            message.content.trim(),
            {
              fontSize: 10,
              color: [30, 41, 59],
              lineHeight: 5,
              spaceAfter: 4,
            }
          );
        }

        if (
          Array.isArray(
            message.sources
          ) &&
          message.sources.length > 0
        ) {
          addWrappedText("Sources:", {
            fontSize: 9,
            fontStyle: "bold",
            color: [71, 85, 105],
            spaceAfter: 1,
          });

          message.sources.forEach(
            (source) => {
              addWrappedText(
                `- ${getSourceText(source)}`,
                {
                  fontSize: 8,
                  color: [
                    100,
                    116,
                    139,
                  ],
                  lineHeight: 4.5,
                  spaceAfter: 1,
                }
              );
            }
          );
        }

        ensureSpace(8);

        pdf.setDrawColor(
          203,
          213,
          225
        );

        pdf.setLineWidth(0.2);

        pdf.line(
          margin,
          yPosition,
          pageWidth - margin,
          yPosition
        );

        yPosition += 7;
      }
    );

    pdf.save(`${getFileName()}.pdf`);
  }

  function handleOverlayClick(event) {
    if (
      event.target ===
      event.currentTarget
    ) {
      onClose();
    }
  }

  return (
    <div
      onClick={handleOverlayClick}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm"
    >
      <div
        className={`w-full max-w-md rounded-2xl border shadow-2xl ${
          isDark
            ? "border-slate-700 bg-slate-900 text-white"
            : "border-slate-200 bg-white text-slate-900"
        }`}
      >
        {/* Header */}
        <div
          className={`flex items-center justify-between border-b p-5 ${
            isDark
              ? "border-slate-700"
              : "border-slate-200"
          }`}
        >
          <div>
            <h2 className="text-xl font-bold">
              ⚙ Settings
            </h2>

            <p
              className={`mt-1 text-sm ${
                isDark
                  ? "text-slate-400"
                  : "text-slate-500"
              }`}
            >
              Customize your Onkar AI
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className={`rounded-lg p-2 text-xl transition ${
              isDark
                ? "text-slate-400 hover:bg-slate-800 hover:text-white"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            }`}
            aria-label="Close settings"
          >
            ✕
          </button>
        </div>

        <div className="max-h-[75vh] space-y-5 overflow-y-auto p-5">
          {/* Appearance */}
          <section>
            <h3 className="mb-3 text-sm font-semibold">
              🎨 Appearance
            </h3>

           <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <button
                type="button"
                onClick={() =>
                  onThemeChange?.("dark")
                }
                className={`rounded-xl border p-4 text-left transition ${
                  theme === "dark"
                    ? "border-blue-500 bg-blue-500/15"
                    : isDark
                      ? "border-slate-700 bg-slate-800 hover:bg-slate-700"
                      : "border-slate-200 bg-slate-50 hover:bg-slate-100"
                }`}
              >
                <div className="text-2xl">
                  🌙
                </div>

                <p className="mt-2 font-semibold">
                  Dark
                </p>
              </button>

              <button
                type="button"
                onClick={() =>
                  onThemeChange?.("light")
                }
                className={`rounded-xl border p-4 text-left transition ${
                  theme === "light"
                    ? "border-blue-500 bg-blue-500/15"
                    : isDark
                      ? "border-slate-700 bg-slate-800 hover:bg-slate-700"
                      : "border-slate-200 bg-slate-50 hover:bg-slate-100"
                }`}
              >
                <div className="text-2xl">
                  ☀️
                </div>

                <p className="mt-2 font-semibold">
                  Light
                </p>
              </button>
            </div>
          </section>

          {/* Model selector */}
          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold">
                🤖 AI Model
              </h3>

              {activeModelId ===
                defaultModel &&
                defaultModel && (
                  <span className="rounded-full bg-blue-500/15 px-2 py-1 text-xs text-blue-500">
                    Default
                  </span>
                )}
            </div>

            <select
              value={activeModelId}
              onChange={handleModelChange}
              disabled={models.length === 0}
              className={`w-full rounded-xl border px-3 py-3 text-sm outline-none transition focus:border-blue-500 disabled:cursor-not-allowed disabled:opacity-50 ${
                isDark
                  ? "border-slate-700 bg-slate-800 text-white"
                  : "border-slate-300 bg-slate-50 text-slate-900"
              }`}
            >
              {models.length === 0 && (
                <option value="">
                  Loading models...
                </option>
              )}

              {models.map((model) => (
                <option
                  key={model.id}
                  value={model.id}
                >
                  {model.name}
                  {model.id === defaultModel
                    ? " — Default"
                    : ""}
                </option>
              ))}
            </select>

            <div
              className={`mt-3 rounded-xl border p-3 ${
                isDark
                  ? "border-slate-700 bg-slate-800/70"
                  : "border-slate-200 bg-slate-50"
              }`}
            >
              <p className="text-sm font-semibold">
                {activeModel?.name ||
                  "No model selected"}
              </p>

              <p
                className={`mt-1 text-xs ${
                  isDark
                    ? "text-slate-400"
                    : "text-slate-500"
                }`}
              >
                {activeModel?.description ||
                  "Select an AI model for chat responses."}
              </p>

              {activeModelId && (
                <p
                  className={`mt-2 break-all text-[11px] ${
                    isDark
                      ? "text-slate-500"
                      : "text-slate-400"
                  }`}
                >
                  Model ID: {activeModelId}
                </p>
              )}
            </div>
          </section>

          {/* Export */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold">
                📤 Export Current Chat
              </h3>

              <span
                className={`text-xs ${
                  isDark
                    ? "text-slate-400"
                    : "text-slate-500"
                }`}
              >
                {exportableMessages.length} messages
              </span>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
  <button
    type="button"
    onClick={exportMarkdown}
    disabled={!hasMessages}
    className={`rounded-xl border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${
      isDark
        ? "border-slate-700 bg-slate-800 hover:bg-slate-700"
        : "border-slate-200 bg-slate-100 hover:bg-slate-200"
    }`}
  >
    <div className="text-2xl">
      📝
    </div>

    <p className="mt-2 font-semibold">
      Markdown
    </p>

    <p className="mt-1 text-xs text-slate-500">
      Editable .md file
    </p>
  </button>

  <button
    type="button"
    onClick={exportPDF}
    disabled={!hasMessages}
    className={`rounded-xl border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${
      isDark
        ? "border-slate-700 bg-slate-800 hover:bg-slate-700"
        : "border-slate-200 bg-slate-100 hover:bg-slate-200"
    }`}
  >
    <div className="text-2xl">
      📄
    </div>

    <p className="mt-2 font-semibold">
      PDF
    </p>

    <p className="mt-1 text-xs text-slate-500">
      Multi-page document
    </p>
  </button>

  <button
    type="button"
    onClick={exportJSON}
    disabled={!hasMessages}
    className={`rounded-xl border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${
      isDark
        ? "border-slate-700 bg-slate-800 hover:bg-slate-700"
        : "border-slate-200 bg-slate-100 hover:bg-slate-200"
    }`}
  >
    <div className="text-2xl">
      💾
    </div>

    <p className="mt-2 font-semibold">
      JSON Backup
    </p>

    <p className="mt-1 text-xs text-slate-500">
      Structured chat data
    </p>
  </button>
</div>
          </section>

          <ChatBackupImport
  restoreChatBackup={
    restoreChatBackup
  }
  theme={theme}
/>

          {/* Other options */}
          <section className="space-y-2">
            <button
              type="button"
              onClick={() =>
                alert(
                  "Clear Memory feature will be added next."
                )
              }
              className={`w-full rounded-xl p-4 text-left transition ${
                isDark
                  ? "bg-slate-800 hover:bg-slate-700"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              🧹 Clear Memory
            </button>

            <button
              type="button"
              onClick={() =>
                alert(
                  "Onkar AI — Personal AI Assistant"
                )
              }
              className={`w-full rounded-xl p-4 text-left transition ${
                isDark
                  ? "bg-slate-800 hover:bg-slate-700"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              ℹ About
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}

export default SettingsModal;