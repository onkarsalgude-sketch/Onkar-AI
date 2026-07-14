import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  deleteDocumentApi,
  getDocuments,
  updateDocumentSelection,
} from "../../services/documentService";


function DocumentLibrary({
  activeChatId,
  refreshKey = 0,
  theme = "dark",
}) {
  const [documents, setDocuments] =
    useState([]);

  const [loading, setLoading] =
    useState(false);

  const [actionId, setActionId] =
    useState(null);

  const [error, setError] =
    useState("");

  const isDark = theme === "dark";


  const loadDocuments = useCallback(
    async () => {
      if (!activeChatId) {
        setDocuments([]);
        return;
      }

      setLoading(true);
      setError("");

      try {
        const response = await getDocuments(
          activeChatId
        );

        setDocuments(
          response?.data?.documents || []
        );
      } catch (requestError) {
        console.error(
          "Failed to load documents:",
          requestError
        );

        setError(
          "Unable to load PDF documents."
        );
      } finally {
        setLoading(false);
      }
    },
    [activeChatId]
  );


  useEffect(() => {
    loadDocuments();
  }, [loadDocuments, refreshKey]);


  async function handleSelectionChange(
    document
  ) {
    setActionId(document.document_id);
    setError("");

    const newSelectedValue =
      !document.is_selected;

    try {
      const response =
        await updateDocumentSelection(
          document.document_id,
          activeChatId,
          newSelectedValue
        );

      const updatedDocument =
        response?.data?.document;

      setDocuments((currentDocuments) =>
        currentDocuments.map((item) =>
          item.document_id ===
          document.document_id
            ? updatedDocument
            : item
        )
      );
    } catch (requestError) {
      console.error(
        "Failed to update selection:",
        requestError
      );

      setError(
        "Unable to update PDF selection."
      );
    } finally {
      setActionId(null);
    }
  }


  async function handleDelete(document) {
    const confirmed = window.confirm(
      `Delete "${document.filename}"?`
    );

    if (!confirmed) {
      return;
    }

    setActionId(document.document_id);
    setError("");

    try {
      await deleteDocumentApi(
        document.filename,
        activeChatId
      );

      setDocuments((currentDocuments) =>
        currentDocuments.filter(
          (item) =>
            item.document_id !==
            document.document_id
        )
      );
    } catch (requestError) {
      console.error(
        "Failed to delete document:",
        requestError
      );

      setError(
        "Unable to delete the PDF."
      );
    } finally {
      setActionId(null);
    }
  }


  if (!activeChatId) {
    return null;
  }


  return (
    <section
      className={`border-b px-3 py-3 sm:px-5 md:px-8 ${
        isDark
          ? "border-slate-800 bg-slate-950/70"
          : "border-slate-200 bg-white"
      }`}
    >
      <div className="mx-auto max-w-5xl">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">
              PDF Documents
            </h3>

            <p className="text-xs text-slate-500">
              Select the PDFs that the AI
              should use.
            </p>
          </div>

          <button
            type="button"
            onClick={loadDocuments}
            disabled={loading}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
              isDark
                ? "border-slate-700 hover:bg-slate-800"
                : "border-slate-300 hover:bg-slate-100"
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        {error && (
          <p className="mt-3 text-xs text-red-500">
            {error}
          </p>
        )}

        {!loading &&
          documents.length === 0 && (
            <p className="mt-3 text-xs text-slate-500">
              No PDF is uploaded in this
              chat.
            </p>
          )}

        {documents.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {documents.map((document) => {
              const isBusy =
                actionId ===
                document.document_id;

              return (
                <div
                  key={document.document_id}
                  className={`flex max-w-full items-center gap-2 rounded-xl border px-3 py-2 ${
                    isDark
                      ? "border-slate-700 bg-slate-900"
                      : "border-slate-200 bg-slate-50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={
                      document.is_selected
                    }
                    disabled={isBusy}
                    onChange={() =>
                      handleSelectionChange(
                        document
                      )
                    }
                    aria-label={`Select ${document.filename}`}
                    className="h-4 w-4 cursor-pointer accent-emerald-500"
                  />

                  <div className="min-w-0">
                    <p
                      className="max-w-52 truncate text-xs font-medium sm:max-w-72"
                      title={
                        document.filename
                      }
                    >
                      {document.filename}
                    </p>

                    <p className="text-[11px] text-slate-500">
                      {document.page_count} page
                      {document.page_count === 1
                        ? ""
                        : "s"}
                      {" • "}
                      {document.size_kb} KB
                      {" • "}
                      {document.status}
                    </p>
                  </div>

                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() =>
                      handleDelete(document)
                    }
                    className="ml-1 rounded-md px-2 py-1 text-xs text-red-500 transition hover:bg-red-500/10 disabled:opacity-50"
                  >
                    Delete
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}


export default DocumentLibrary;