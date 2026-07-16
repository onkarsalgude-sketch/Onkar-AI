import {
  useRef,
  useState,
} from "react";

const MAX_BACKUP_SIZE_BYTES =
  2 * 1024 * 1024;

function validateBackupData(data) {
  if (
    !data ||
    typeof data !== "object" ||
    Array.isArray(data)
  ) {
    throw new Error(
      "The selected file does not contain a valid JSON object."
    );
  }

  if (data.schema_version !== 1) {
    throw new Error(
      "Unsupported backup version. Only schema version 1 is supported."
    );
  }

  if (
    String(data.application || "")
      .trim()
      .toLowerCase() !== "onkar ai"
  ) {
    throw new Error(
      "This backup was not created by Onkar AI."
    );
  }

  if (
    !data.chat ||
    typeof data.chat !== "object" ||
    Array.isArray(data.chat)
  ) {
    throw new Error(
      "The backup is missing chat information."
    );
  }

  if (
    !Array.isArray(data.messages) ||
    data.messages.length === 0
  ) {
    throw new Error(
      "The backup does not contain any messages."
    );
  }

  if (data.messages.length > 1000) {
    throw new Error(
      "This backup contains more than 1000 messages and cannot be imported."
    );
  }

  data.messages.forEach(
    (message, index) => {
      if (
        !message ||
        typeof message !== "object" ||
        Array.isArray(message)
      ) {
        throw new Error(
          `Message ${index + 1} is invalid.`
        );
      }

      if (
        message.role !== "user" &&
        message.role !== "assistant"
      ) {
        throw new Error(
          `Message ${index + 1} has an unsupported role.`
        );
      }

      if (
        typeof message.content !==
        "string"
      ) {
        throw new Error(
          `Message ${index + 1} has invalid content.`
        );
      }
    }
  );

  return data;
}

function ChatBackupImport({
  restoreChatBackup,
  theme = "dark",
}) {
  const isDark = theme === "dark";

  const fileInputRef = useRef(null);

  const [selectedFileName, setSelectedFileName] =
    useState("");

  const [backupPreview, setBackupPreview] =
    useState(null);

  const [parsedBackup, setParsedBackup] =
    useState(null);

  const [error, setError] =
    useState("");

  const [importing, setImporting] =
    useState(false);

  const [importResult, setImportResult] =
    useState(null);

  function resetSelection() {
    setSelectedFileName("");
    setBackupPreview(null);
    setParsedBackup(null);
    setError("");

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function handleFileChange(
    event
  ) {
    const file =
      event.target.files?.[0];

    setImportResult(null);
    setError("");
    setBackupPreview(null);
    setParsedBackup(null);
    setSelectedFileName("");

    if (!file) {
      return;
    }

    if (
      !file.name
        .toLowerCase()
        .endsWith(".json")
    ) {
      setError(
        "Please select an Onkar AI .json backup file."
      );

      event.target.value = "";
      return;
    }

    if (
      file.size >
      MAX_BACKUP_SIZE_BYTES
    ) {
      setError(
        "The backup file is too large. The maximum size is 2 MB."
      );

      event.target.value = "";
      return;
    }

    try {
      const text =
        await file.text();

      const parsed =
        JSON.parse(text);

      const validated =
        validateBackupData(parsed);

      const sourceCount =
        validated.messages.reduce(
          (count, message) =>
            count +
            (Array.isArray(
              message.sources
            )
              ? message.sources.length
              : 0),
          0
        );

      const attachmentCount =
        validated.messages.filter(
          (message) =>
            Boolean(
              message.attachment
            )
        ).length;

      setSelectedFileName(
        file.name
      );

      setParsedBackup(validated);

      setBackupPreview({
        title:
          String(
            validated.chat?.title ||
              "Imported Chat"
          ).trim() ||
          "Imported Chat",

        messageCount:
          validated.messages.length,

        sourceCount,

        attachmentCount,

        exportedAt:
          validated.exported_at ||
          null,
      });
    } catch (fileError) {
      console.error(
        "Backup file validation failed:",
        fileError
      );

      setError(
        fileError?.message ||
          "The selected JSON backup is invalid or corrupted."
      );

      event.target.value = "";
    }
  }

  async function handleImport() {
    if (
      !parsedBackup ||
      importing ||
      typeof restoreChatBackup !==
        "function"
    ) {
      return;
    }

    setImporting(true);
    setError("");
    setImportResult(null);

    try {
      const result =
        await restoreChatBackup(
          parsedBackup
        );

      if (!result) {
        setError(
          "The chat backup could not be imported."
        );
        return;
      }

      setImportResult(result);
      resetSelection();
    } catch (importError) {
      console.error(
        "Chat backup import failed:",
        importError
      );

      setError(
        importError?.message ||
          "The chat backup could not be imported."
      );
    } finally {
      setImporting(false);
    }
  }

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">
          📥 Import Chat Backup
        </h3>

        <span
          className={`text-xs ${
            isDark
              ? "text-slate-400"
              : "text-slate-500"
          }`}
        >
          JSON • Max 2 MB
        </span>
      </div>

      <div
        className={`rounded-xl border p-4 ${
          isDark
            ? "border-slate-700 bg-slate-800/70"
            : "border-slate-200 bg-slate-50"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,application/json"
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
            📂
          </div>

          <p className="mt-2 text-sm font-semibold">
            Choose JSON backup
          </p>

          <p className="mt-1 text-xs text-slate-500">
            A new chat will be created. Existing chats will not be overwritten.
          </p>
        </button>

        {selectedFileName && (
          <p className="mt-3 break-all text-xs text-slate-500">
            Selected:{" "}
            {selectedFileName}
          </p>
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

        {backupPreview && (
          <div
            className={`mt-3 rounded-xl border p-3 text-sm ${
              isDark
                ? "border-slate-700 bg-slate-900"
                : "border-slate-200 bg-white"
            }`}
          >
            <p className="font-semibold">
              {backupPreview.title}
            </p>

            <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-500">
              <p>
                Messages:{" "}
                {
                  backupPreview.messageCount
                }
              </p>

              <p>
                Sources:{" "}
                {
                  backupPreview.sourceCount
                }
              </p>

              <p>
                Attachments:{" "}
                {
                  backupPreview.attachmentCount
                }
              </p>

              <p>
                Exported:{" "}
                {backupPreview.exportedAt
                  ? new Date(
                      backupPreview.exportedAt
                    ).toLocaleString()
                  : "Unknown"}
              </p>
            </div>

            <div
              className={`mt-3 rounded-lg p-3 text-xs ${
                isDark
                  ? "bg-amber-500/10 text-amber-300"
                  : "bg-amber-50 text-amber-700"
              }`}
            >
              PDF and image files are not stored inside the JSON backup. Their names and source metadata may be restored, but the original files and PDF RAG data must be uploaded again.
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={handleImport}
                disabled={
                  importing ||
                  !parsedBackup
                }
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {importing
                  ? "Importing..."
                  : "Import as New Chat"}
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
              Chat imported successfully
            </p>

            <p className="mt-1 text-xs">
              {importResult.title} •{" "}
              {
                importResult.message_count
              }{" "}
              messages
            </p>

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

export default ChatBackupImport;
