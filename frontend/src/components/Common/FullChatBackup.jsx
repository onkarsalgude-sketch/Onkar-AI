import {
  useRef,
  useState,
} from "react";

import {
  exportFullChatBackup,
} from "../../services/chatService";


const MAX_ZIP_SIZE_BYTES =
  50 * 1024 * 1024;


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


function formatFileSize(size) {
  if (!Number.isFinite(size)) {
    return "Unknown size";
  }

  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(
      size / 1024
    ).toFixed(1)} KB`;
  }

  return `${(
    size /
    (1024 * 1024)
  ).toFixed(1)} MB`;
}


function FullChatBackup({
  activeChat = null,
  restoreFullChatBackup,
  theme = "dark",
}) {
  const isDark = theme === "dark";

  const fileInputRef = useRef(null);

  const [selectedFile, setSelectedFile] =
    useState(null);

  const [exporting, setExporting] =
    useState(false);

  const [importing, setImporting] =
    useState(false);

  const [error, setError] =
    useState("");

  const [importResult, setImportResult] =
    useState(null);

  const activeChatId =
    activeChat?.id ?? null;

  const activeChatTitle =
    String(
      activeChat?.title ||
        "Onkar AI Chat"
    ).trim() ||
    "Onkar AI Chat";


  function resetSelection() {
    setSelectedFile(null);
    setError("");

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }


  async function handleExport() {
    if (!activeChatId || exporting) {
      return;
    }

    setExporting(true);
    setError("");
    setImportResult(null);

    try {
      const response =
        await exportFullChatBackup(
          activeChatId
        );

      const blob =
        response?.data;

      if (!(blob instanceof Blob)) {
        throw new Error(
          "The backup download was invalid."
        );
      }

      const now = new Date()
        .toISOString()
        .slice(0, 19)
        .replace("T", "-")
        .replaceAll(":", "-");

      const downloadName =
        `${sanitizeFileName(
          activeChatTitle
        )}-${now}-full-backup.zip`;

      const downloadUrl =
        URL.createObjectURL(blob);

      const link =
        document.createElement("a");

      link.href = downloadUrl;
      link.download = downloadName;

      document.body.appendChild(link);
      link.click();
      link.remove();

      URL.revokeObjectURL(
        downloadUrl
      );
    } catch (exportError) {
      console.error(
        "Full backup export failed:",
        exportError
      );

      setError(
        exportError?.response?.data?.detail ||
          exportError?.message ||
          "Unable to export the full chat backup."
      );
    } finally {
      setExporting(false);
    }
  }


  function handleFileChange(event) {
    const file =
      event.target.files?.[0];

    setSelectedFile(null);
    setImportResult(null);
    setError("");

    if (!file) {
      return;
    }

    if (
      !file.name
        .toLowerCase()
        .endsWith(".zip")
    ) {
      setError(
        "Please select an Onkar AI .zip backup file."
      );

      event.target.value = "";
      return;
    }

    if (
      file.size >
      MAX_ZIP_SIZE_BYTES
    ) {
      setError(
        "The ZIP backup is larger than the 50 MB limit."
      );

      event.target.value = "";
      return;
    }

    setSelectedFile(file);
  }


  async function handleImport() {
    if (
      !selectedFile ||
      importing
    ) {
      return;
    }

    if (
      typeof restoreFullChatBackup
      !== "function"
    ) {
      setError(
        "Full backup restore is not connected yet."
      );

      return;
    }

    setImporting(true);
    setError("");
    setImportResult(null);

    try {
      const result =
        await restoreFullChatBackup(
          selectedFile
        );

      if (!result) {
        setError(
          "The full chat backup could not be restored."
        );

        return;
      }

      setImportResult(result);
      resetSelection();
    } catch (importError) {
      console.error(
        "Full backup restore failed:",
        importError
      );

      setError(
        importError?.response?.data?.detail ||
          importError?.message ||
          "The full chat backup could not be restored."
      );
    } finally {
      setImporting(false);
    }
  }


  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">
          🗃 Full ZIP Backup
        </h3>

        <span
          className={`text-xs ${
            isDark
              ? "text-slate-400"
              : "text-slate-500"
          }`}
        >
          Chat + PDFs + RAG restore
        </span>
      </div>

      <div
        className={`rounded-xl border p-4 ${
          isDark
            ? "border-slate-700 bg-slate-800/70"
            : "border-slate-200 bg-slate-50"
        }`}
      >
        <button
          type="button"
          onClick={handleExport}
          disabled={
            !activeChatId ||
            exporting
          }
          className="w-full rounded-xl bg-blue-600 px-4 py-3 text-left text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <p className="font-semibold">
            {exporting
              ? "Creating ZIP backup..."
              : "Download Full ZIP Backup"}
          </p>

          <p className="mt-1 text-xs text-blue-100">
            Includes messages and ready PDF files from the active chat.
          </p>
        </button>

        {!activeChatId && (
          <p className="mt-2 text-xs text-slate-500">
            Open a saved chat before exporting a full backup.
          </p>
        )}

        <div
          className={`my-4 border-t ${
            isDark
              ? "border-slate-700"
              : "border-slate-200"
          }`}
        />

        <input
          ref={fileInputRef}
          type="file"
          accept=".zip,application/zip"
          onChange={handleFileChange}
          disabled={importing}
          className="hidden"
        />

        <button
          type="button"
          onClick={() =>
            fileInputRef.current?.click()
          }
          disabled={importing}
          className={`w-full rounded-xl border border-dashed p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
            isDark
              ? "border-slate-600 hover:border-blue-500 hover:bg-slate-700/50"
              : "border-slate-300 hover:border-blue-500 hover:bg-white"
          }`}
        >
          <div className="text-2xl">
            📦
          </div>

          <p className="mt-2 text-sm font-semibold">
            Choose Full ZIP Backup
          </p>

          <p className="mt-1 text-xs text-slate-500">
            Restore messages, PDFs and searchable RAG data into a new chat.
          </p>
        </button>

        {selectedFile && (
          <div
            className={`mt-3 rounded-xl border p-3 ${
              isDark
                ? "border-slate-700 bg-slate-900"
                : "border-slate-200 bg-white"
            }`}
          >
            <p className="break-all text-sm font-semibold">
              {selectedFile.name}
            </p>

            <p className="mt-1 text-xs text-slate-500">
              {formatFileSize(
                selectedFile.size
              )}
            </p>

            <div
              className={`mt-3 rounded-lg p-3 text-xs ${
                isDark
                  ? "bg-amber-500/10 text-amber-300"
                  : "bg-amber-50 text-amber-700"
              }`}
            >
              A new chat will be created. Existing chats and files will not be overwritten.
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleImport}
                disabled={importing}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {importing
                  ? "Restoring and indexing..."
                  : "Restore Full Backup"}
              </button>

              <button
                type="button"
                onClick={resetSelection}
                disabled={importing}
                className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
                  isDark
                    ? "bg-slate-700 text-slate-200 hover:bg-slate-600"
                    : "bg-slate-200 text-slate-700 hover:bg-slate-300"
                } disabled:cursor-not-allowed disabled:opacity-50`}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {error && (
          <div
            className={`mt-3 rounded-lg border p-3 text-xs ${
              isDark
                ? "border-red-500/40 bg-red-500/10 text-red-300"
                : "border-red-300 bg-red-50 text-red-700"
            }`}
            role="alert"
          >
            {error}
          </div>
        )}

        {importResult && (
          <div
            className={`mt-3 rounded-xl border p-3 text-sm ${
              isDark
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                : "border-emerald-300 bg-emerald-50 text-emerald-800"
            }`}
            role="status"
          >
            <p className="font-semibold">
              Full backup restored successfully
            </p>

            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
              <p>
                Messages:{" "}
                {
                  importResult.message_count
                }
              </p>

              <p>
                PDFs:{" "}
                {
                  importResult.document_count
                }
              </p>

              <p>
                Pages:{" "}
                {
                  importResult.total_pages
                }
              </p>

              <p>
                RAG chunks:{" "}
                {
                  importResult.total_chunks
                }
              </p>
            </div>

            {Array.isArray(
              importResult.warnings
            ) &&
              importResult.warnings.length >
                0 && (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
                  {importResult.warnings.map(
                    (warning, index) => (
                      <li
                        key={`${warning}-${index}`}
                      >
                        {warning}
                      </li>
                    )
                  )}
                </ul>
              )}
          </div>
        )}
      </div>
    </section>
  );
}


export default FullChatBackup;
