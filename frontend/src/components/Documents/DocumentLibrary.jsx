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


const PAGE_SIZE = 6;

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

  const [bulkAction, setBulkAction] =
    useState(null);

  const [searchQuery, setSearchQuery] =
    useState("");

  const [sortOption, setSortOption] =
    useState(() => {
      try {
        return (
          localStorage.getItem(
            "onkar-ai-document-sort"
          ) || "newest"
        );
      } catch {
        return "newest";
      }
    });

  const [currentPage, setCurrentPage] =
    useState(1);

  const [isCollapsed, setIsCollapsed] =
    useState(() => {
      try {
        return localStorage.getItem(
          "onkar-ai-document-library-collapsed"
        ) === "true";
      } catch {
        return false;
      }
    });

  const isDark = theme === "dark";

  const selectedDocumentCount =
    documents.filter(
      (document) => document.is_selected
    ).length;

  function sortDocuments(docs) {
    const sorted = [...docs];
    if (sortOption === "name-asc") {
      sorted.sort((a, b) =>
        a.filename.localeCompare(b.filename)
      );
    } else if (sortOption === "name-desc") {
      sorted.sort((a, b) =>
        b.filename.localeCompare(a.filename)
      );
    } else if (sortOption === "selected") {
      sorted.sort((a, b) =>
        b.is_selected - a.is_selected
      );
    } else {
      // newest: parse uploaded_at, fall back to filename
      sorted.sort((a, b) => {
        const ta = a.uploaded_at
          ? new Date(a.uploaded_at).getTime()
          : NaN;
        const tb = b.uploaded_at
          ? new Date(b.uploaded_at).getTime()
          : NaN;
        const validA = !isNaN(ta);
        const validB = !isNaN(tb);
        if (validA && validB) return tb - ta;
        if (validA) return -1;
        if (validB) return 1;
        return a.filename.localeCompare(b.filename);
      });
    }
    return sorted;
  }

  const filteredDocuments = sortDocuments(
    documents.filter((doc) =>
      doc.filename
        .toLowerCase()
        .includes(searchQuery.toLowerCase())
    )
  );

  const totalPages = Math.max(
    1,
    Math.ceil(filteredDocuments.length / PAGE_SIZE)
  );

  // Clamp currentPage whenever filteredDocuments shrinks
  const safePage = Math.min(currentPage, totalPages);

  const pagedDocuments = filteredDocuments.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE
  );

  const showPagination =
    filteredDocuments.length > PAGE_SIZE;


  const loadDocuments = useCallback(
    async () => {
      if (!activeChatId) {
        setDocuments([]);
        return;
      }

      setLoading(true);
      setError("");
      setSearchQuery("");
      setCurrentPage(1);

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

  // Reset to page 1 when search or sort changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, sortOption]);


  async function handleSelectionChange(
    document
  ) {
    if (bulkAction !== null) return;
    setActionId(document.document_id);
    setError("");

    const newSelectedValue =
      !document.is_selected;

    // Optimistically update selection state immediately
    setDocuments((currentDocuments) =>
      currentDocuments.map((item) =>
        item.document_id === document.document_id
          ? { ...item, is_selected: newSelectedValue }
          : item
      )
    );

    try {
      const response =
        await updateDocumentSelection(
          document.document_id,
          activeChatId,
          newSelectedValue
        );

      const updatedDocument =
        response?.data?.document;

      if (updatedDocument) {
        setDocuments((currentDocuments) =>
          currentDocuments.map((item) =>
            item.document_id ===
            document.document_id
              ? updatedDocument
              : item
          )
        );
      }
    } catch (requestError) {
      console.error(
        "Failed to update selection:",
        requestError
      );

      // Revert optimistic update on failure
      setDocuments((currentDocuments) =>
        currentDocuments.map((item) =>
          item.document_id === document.document_id
            ? { ...item, is_selected: !newSelectedValue }
            : item
        )
      );

      setError(
        "Unable to update PDF selection."
      );
    } finally {
      setActionId(null);
    }
  }


  async function handleDelete(document) {
    if (bulkAction !== null) return;
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

  async function handleBulkSelection() {
    if (
      loading ||
      actionId !== null ||
      bulkAction !== null ||
      documents.length === 0
    ) {
      return;
    }

    const currentChatId = activeChatId;
    const allSelected = documents.every(
      (doc) => doc.is_selected
    );
    const targetValue = !allSelected;
    const nextBulkAction = targetValue
      ? "selecting"
      : "deselecting";

    setBulkAction(nextBulkAction);
    setError("");

    const docsToUpdate = documents.filter(
      (doc) => doc.is_selected !== targetValue
    );

    if (docsToUpdate.length === 0) {
      setBulkAction(null);
      return;
    }

    const previousDocuments = documents;

    setDocuments((currentDocuments) =>
      currentDocuments.map((item) => ({
        ...item,
        is_selected: targetValue,
      }))
    );

    try {
      const promises = docsToUpdate.map((doc) =>
        updateDocumentSelection(
          doc.document_id,
          currentChatId,
          targetValue
        )
      );

      const results = await Promise.allSettled(promises);

      const failedDocs = [];
      const succeededDocs = [];
      const updatedDocsMap = {};

      results.forEach((result, idx) => {
        const doc = docsToUpdate[idx];
        if (result.status === "fulfilled") {
          succeededDocs.push(doc);
          const updatedDoc = result.value?.data?.document;
          if (updatedDoc) {
            updatedDocsMap[updatedDoc.document_id] = updatedDoc;
          }
        } else {
          failedDocs.push(doc);
        }
      });

      if (failedDocs.length > 0) {
        let rollbackSucceeded = true;

        if (succeededDocs.length > 0) {
          try {
            const rollbackPromises = succeededDocs.map((doc) =>
              updateDocumentSelection(
                doc.document_id,
                currentChatId,
                !targetValue
              )
            );
            const rollbackResults = await Promise.allSettled(rollbackPromises);
            const anyRollbackFailed = rollbackResults.some(
              (r) => r.status === "rejected"
            );
            if (anyRollbackFailed) {
              rollbackSucceeded = false;
            }
          } catch (rollbackError) {
            console.error(
              "Failed to rollback some backend updates:",
              rollbackError
            );
            rollbackSucceeded = false;
          }
        }

        if (rollbackSucceeded) {
          setDocuments(previousDocuments);
          setError("Unable to update all PDF selections. Changes were restored.");
        } else {
          await loadDocuments();
          setError("Some PDF selections could not be restored. The current server state was refreshed.");
        }
      } else {
        setDocuments((currentDocuments) =>
          currentDocuments.map((item) =>
            updatedDocsMap[item.document_id] || item
          )
        );
      }
    } catch (requestError) {
      console.error(
        "Bulk selection update failed:",
        requestError
      );
      setDocuments(previousDocuments);
      setError("Unable to update bulk selection.");
    } finally {
      setBulkAction(null);
    }
  }


  if (!activeChatId) {
    return null;
  }


  function toggleCollapsed() {
    setIsCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(
          "onkar-ai-document-library-collapsed",
          String(next)
        );
      } catch {
        // ignore storage errors
      }
      return next;
    });
  }

  return (
    <section
      className={`border-b px-3 py-3 sm:px-5 md:px-8 ${
        isDark
          ? "border-slate-800 bg-slate-950/70"
          : "border-slate-200 bg-white"
      }`}
    >
      <div className="mx-auto max-w-5xl overflow-hidden">
        {/* Header row — always visible */}
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold">
              PDF Documents
            </h3>

            <p className="text-xs text-slate-500">
              {documents.length > 0
                ? `${selectedDocumentCount} of ${documents.length} selected`
                : "Select the PDFs that the AI should use."}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {/* Bulk selection and Refresh — hidden when collapsed */}
            {!isCollapsed && documents.length > 0 && (
              <button
                type="button"
                onClick={handleBulkSelection}
                disabled={
                  loading ||
                  actionId !== null ||
                  bulkAction !== null
                }
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                  isDark
                    ? "border-slate-700 hover:bg-slate-800"
                    : "border-slate-300 hover:bg-slate-100"
                } disabled:cursor-not-allowed disabled:opacity-50`}
              >
                {bulkAction === "selecting"
                  ? "Selecting..."
                  : bulkAction === "deselecting"
                  ? "Deselecting..."
                  : documents.every(
                      (doc) => doc.is_selected
                    )
                  ? "Deselect All"
                  : "Select All"}
              </button>
            )}

            {!isCollapsed && (
              <button
                type="button"
                onClick={loadDocuments}
                disabled={
                  loading || bulkAction !== null
                }
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                  isDark
                    ? "border-slate-700 hover:bg-slate-800"
                    : "border-slate-300 hover:bg-slate-100"
                } disabled:cursor-not-allowed disabled:opacity-50`}
              >
                {loading ? "Loading..." : "Refresh"}
              </button>
            )}

            {/* Collapse / Expand — always visible */}
            <button
              type="button"
              onClick={toggleCollapsed}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                isDark
                  ? "border-slate-700 hover:bg-slate-800"
                  : "border-slate-300 hover:bg-slate-100"
              }`}
            >
              {isCollapsed ? "Expand" : "Collapse"}
            </button>
          </div>
        </div>

        {/* Collapsible body */}
        {!isCollapsed && (
          <>
            {documents.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {/* Search input */}
                <div className="relative flex items-center">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search PDFs..."
                    disabled={loading || bulkAction !== null}
                    className={`w-44 rounded-lg border px-3 py-1.5 pr-8 text-xs outline-none transition sm:w-56 ${
                      isDark
                        ? "border-slate-800 bg-slate-900 text-slate-100 placeholder-slate-500 focus:border-slate-700"
                        : "border-slate-200 bg-slate-50 text-slate-800 placeholder-slate-400 focus:border-slate-300"
                    }`}
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => setSearchQuery("")}
                      disabled={loading || bulkAction !== null}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-slate-400 hover:text-slate-600 focus:outline-none"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-3.5 w-3.5"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M6 18L18 6M6 6l12 12"
                        />
                      </svg>
                    </button>
                  )}
                </div>

                {/* Sort dropdown */}
                <select
                  value={sortOption}
                  onChange={(e) => {
                    const val = e.target.value;
                    setSortOption(val);
                    try {
                      localStorage.setItem(
                        "onkar-ai-document-sort",
                        val
                      );
                    } catch {
                      // ignore storage errors
                    }
                  }}
                  disabled={loading || bulkAction !== null}
                  className={`rounded-lg border px-2 py-1.5 text-xs outline-none transition disabled:cursor-not-allowed disabled:opacity-50 ${
                    isDark
                      ? "border-slate-800 bg-slate-900 text-slate-100 focus:border-slate-700"
                      : "border-slate-200 bg-slate-50 text-slate-800 focus:border-slate-300"
                  }`}
                >
                  <option value="newest">Newest first</option>
                  <option value="name-asc">Name A–Z</option>
                  <option value="name-desc">Name Z–A</option>
                  <option value="selected">Selected first</option>
                </select>
              </div>
            )}

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

            {!loading &&
              documents.length > 0 &&
              filteredDocuments.length === 0 && (
                <p className="mt-3 text-xs text-slate-500">
                  No PDFs match your search.
                </p>
              )}

            {documents.length > 0 && filteredDocuments.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {pagedDocuments.map((document) => {
                  const isBusy =
                    actionId ===
                    document.document_id ||
                    bulkAction !== null;

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

            {/* Pagination controls */}
            {!loading && showPagination && (
              <div className="mt-3 flex items-center gap-3">
                <button
                  type="button"
                  onClick={() =>
                    setCurrentPage((p) => Math.max(1, p - 1))
                  }
                  disabled={safePage === 1 || bulkAction !== null}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                    isDark
                      ? "border-slate-700 hover:bg-slate-800"
                      : "border-slate-300 hover:bg-slate-100"
                  } disabled:cursor-not-allowed disabled:opacity-40`}
                >
                  Previous
                </button>

                <span className="text-xs text-slate-500">
                  Page {safePage} of {totalPages}
                </span>

                <button
                  type="button"
                  onClick={() =>
                    setCurrentPage((p) =>
                      Math.min(totalPages, p + 1)
                    )
                  }
                  disabled={
                    safePage === totalPages ||
                    bulkAction !== null
                  }
                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                    isDark
                      ? "border-slate-700 hover:bg-slate-800"
                      : "border-slate-300 hover:bg-slate-100"
                  } disabled:cursor-not-allowed disabled:opacity-40`}
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}


export default DocumentLibrary;