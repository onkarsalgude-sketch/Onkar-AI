import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  buildPdfPreviewUrls,
  deleteDocumentApi,
  getDocuments,
  updateDocumentSelection,
} from "../../services/documentService";

import PdfPreviewModal from "./PdfPreviewModal";

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

  const [previewSource, setPreviewSource] =
    useState(null);

  const [deleteMode, setDeleteMode] =
    useState(false);

  const [bulkDeleteIds, setBulkDeleteIds] =
    useState([]);

  const [deleteSummary, setDeleteSummary] =
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
        return (
          localStorage.getItem(
            "onkar-ai-document-library-collapsed"
          ) === "true"
        );
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
      sorted.sort(
        (a, b) =>
          Number(b.is_selected) -
          Number(a.is_selected)
      );
    } else {
      sorted.sort((a, b) => {
        const timeA = a.uploaded_at
          ? new Date(
              a.uploaded_at
            ).getTime()
          : Number.NaN;

        const timeB = b.uploaded_at
          ? new Date(
              b.uploaded_at
            ).getTime()
          : Number.NaN;

        const validA =
          !Number.isNaN(timeA);

        const validB =
          !Number.isNaN(timeB);

        if (validA && validB) {
          return timeB - timeA;
        }

        if (validA) {
          return -1;
        }

        if (validB) {
          return 1;
        }

        return a.filename.localeCompare(
          b.filename
        );
      });
    }

    return sorted;
  }

  const filteredDocuments = sortDocuments(
    documents.filter((document) =>
      document.filename
        .toLowerCase()
        .includes(
          searchQuery
            .trim()
            .toLowerCase()
        )
    )
  );

  const filteredDeleteIds =
    filteredDocuments.map(
      (document) => document.document_id
    );

  const allFilteredMarkedForDelete =
    filteredDeleteIds.length > 0 &&
    filteredDeleteIds.every((id) =>
      bulkDeleteIds.includes(id)
    );

  const totalPages = Math.max(
    1,
    Math.ceil(
      filteredDocuments.length / PAGE_SIZE
    )
  );

  const safePage = Math.min(
    currentPage,
    totalPages
  );

  const pagedDocuments =
    filteredDocuments.slice(
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
      setDeleteMode(false);
      setBulkDeleteIds([]);
      setDeleteSummary(null);
      setPreviewSource(null);

      try {
        const response =
          await getDocuments(activeChatId);

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

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, sortOption]);

  async function handleSelectionChange(
    document
  ) {
    if (
      deleteMode ||
      bulkAction !== null
    ) {
      return;
    }

    setActionId(document.document_id);
    setError("");

    const newSelectedValue =
      !document.is_selected;

    setDocuments((currentDocuments) =>
      currentDocuments.map((item) =>
        item.document_id ===
        document.document_id
          ? {
              ...item,
              is_selected:
                newSelectedValue,
            }
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
        setDocuments(
          (currentDocuments) =>
            currentDocuments.map(
              (item) =>
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

      setDocuments(
        (currentDocuments) =>
          currentDocuments.map(
            (item) =>
              item.document_id ===
              document.document_id
                ? {
                    ...item,
                    is_selected:
                      !newSelectedValue,
                  }
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
    if (
      deleteMode ||
      bulkAction !== null
    ) {
      return;
    }

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

      setDocuments(
        (currentDocuments) =>
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
      deleteMode ||
      loading ||
      actionId !== null ||
      bulkAction !== null ||
      documents.length === 0
    ) {
      return;
    }

    const currentChatId =
      activeChatId;

    const allSelected =
      documents.every(
        (document) =>
          document.is_selected
      );

    const targetValue = !allSelected;

    setBulkAction(
      targetValue
        ? "selecting"
        : "deselecting"
    );

    setError("");

    const documentsToUpdate =
      documents.filter(
        (document) =>
          document.is_selected !==
          targetValue
      );

    if (
      documentsToUpdate.length === 0
    ) {
      setBulkAction(null);
      return;
    }

    const previousDocuments =
      documents;

    setDocuments(
      (currentDocuments) =>
        currentDocuments.map(
          (item) => ({
            ...item,
            is_selected: targetValue,
          })
        )
    );

    try {
      const results =
        await Promise.allSettled(
          documentsToUpdate.map(
            (document) =>
              updateDocumentSelection(
                document.document_id,
                currentChatId,
                targetValue
              )
          )
        );

      const succeededDocuments = [];
      const failedDocuments = [];
      const updatedDocumentsMap = {};

      results.forEach(
        (result, index) => {
          const document =
            documentsToUpdate[index];

          if (
            result.status === "fulfilled"
          ) {
            succeededDocuments.push(
              document
            );

            const updatedDocument =
              result.value?.data?.document;

            if (updatedDocument) {
              updatedDocumentsMap[
                updatedDocument.document_id
              ] = updatedDocument;
            }
          } else {
            failedDocuments.push(
              document
            );
          }
        }
      );

      if (
        failedDocuments.length > 0
      ) {
        let rollbackSucceeded = true;

        if (
          succeededDocuments.length > 0
        ) {
          const rollbackResults =
            await Promise.allSettled(
              succeededDocuments.map(
                (document) =>
                  updateDocumentSelection(
                    document.document_id,
                    currentChatId,
                    !targetValue
                  )
              )
            );

          rollbackSucceeded =
            rollbackResults.every(
              (result) =>
                result.status ===
                "fulfilled"
            );
        }

        if (rollbackSucceeded) {
          setDocuments(
            previousDocuments
          );

          setError(
            "Unable to update all PDF selections. Changes were restored."
          );
        } else {
          await loadDocuments();

          setError(
            "Some PDF selections could not be restored. The server state was refreshed."
          );
        }
      } else {
        setDocuments(
          (currentDocuments) =>
            currentDocuments.map(
              (item) =>
                updatedDocumentsMap[
                  item.document_id
                ] || item
            )
        );
      }
    } catch (requestError) {
      console.error(
        "Bulk selection failed:",
        requestError
      );

      setDocuments(previousDocuments);

      setError(
        "Unable to update bulk selection."
      );
    } finally {
      setBulkAction(null);
    }
  }

  function toggleBulkDeleteMode() {
    if (
      loading ||
      actionId !== null ||
      bulkAction !== null
    ) {
      return;
    }

    setDeleteMode(
      (currentMode) => {
        const nextMode =
          !currentMode;

        if (!nextMode) {
          setBulkDeleteIds([]);
        }

        return nextMode;
      }
    );

    setDeleteSummary(null);
    setError("");
  }

  function toggleDeleteCandidate(
    documentId
  ) {
    if (
      loading ||
      bulkAction !== null
    ) {
      return;
    }

    setBulkDeleteIds((currentIds) =>
      currentIds.includes(documentId)
        ? currentIds.filter(
            (id) => id !== documentId
          )
        : [...currentIds, documentId]
    );
  }

  function toggleAllDeleteCandidates() {
    if (
      loading ||
      bulkAction !== null ||
      filteredDocuments.length === 0
    ) {
      return;
    }

    const allFilteredSelected =
      filteredDeleteIds.every((id) =>
        bulkDeleteIds.includes(id)
      );

    setBulkDeleteIds(
      (currentIds) => {
        if (allFilteredSelected) {
          return currentIds.filter(
            (id) =>
              !filteredDeleteIds.includes(
                id
              )
          );
        }

        return Array.from(
          new Set([
            ...currentIds,
            ...filteredDeleteIds,
          ])
        );
      }
    );
  }

  async function handleBulkDelete() {
    if (
      loading ||
      actionId !== null ||
      bulkAction !== null ||
      bulkDeleteIds.length === 0
    ) {
      return;
    }

    const documentsToDelete =
      documents.filter((document) =>
        bulkDeleteIds.includes(
          document.document_id
        )
      );

    if (
      documentsToDelete.length === 0
    ) {
      setBulkDeleteIds([]);
      return;
    }

    const filenamePreview =
      documentsToDelete
        .slice(0, 5)
        .map(
          (document) =>
            `• ${document.filename}`
        )
        .join("\n");

    const remainingCount =
      documentsToDelete.length - 5;

    const confirmed = window.confirm(
      `Permanently delete ${
        documentsToDelete.length
      } PDF${
        documentsToDelete.length === 1
          ? ""
          : "s"
      }?\n\n${filenamePreview}${
        remainingCount > 0
          ? `\n• and ${remainingCount} more`
          : ""
      }\n\nThis action cannot be undone.`
    );

    if (!confirmed) {
      return;
    }

    const currentChatId =
      activeChatId;

    setBulkAction("deleting");
    setError("");
    setDeleteSummary(null);

    try {
      const results =
        await Promise.allSettled(
          documentsToDelete.map(
            (document) =>
              deleteDocumentApi(
                document.filename,
                currentChatId
              )
          )
        );

      const deletedDocuments = [];
      const failedDocuments = [];

      results.forEach(
        (result, index) => {
          const document =
            documentsToDelete[index];

          if (
            result.status ===
            "fulfilled"
          ) {
            deletedDocuments.push(
              document
            );
          } else {
            failedDocuments.push(
              document
            );
          }
        }
      );

      const deletedIds = new Set(
        deletedDocuments.map(
          (document) =>
            document.document_id
        )
      );

      setDocuments(
        (currentDocuments) =>
          currentDocuments.filter(
            (document) =>
              !deletedIds.has(
                document.document_id
              )
          )
      );

      setBulkDeleteIds(
        failedDocuments.map(
          (document) =>
            document.document_id
        )
      );

      setDeleteSummary({
        deleted:
          deletedDocuments.map(
            (document) =>
              document.filename
          ),
        failed:
          failedDocuments.map(
            (document) =>
              document.filename
          ),
      });

      if (
        failedDocuments.length === 0
      ) {
        setDeleteMode(false);
      } else {
        setError(
          `${failedDocuments.length} PDF${
            failedDocuments.length === 1
              ? ""
              : "s"
          } could not be deleted.`
        );
      }
    } catch (requestError) {
      console.error(
        "Bulk PDF deletion failed:",
        requestError
      );

      setError(
        "Unable to complete the bulk delete operation."
      );
    } finally {
      setBulkAction(null);
    }
  }

  function toggleCollapsed() {
    setIsCollapsed((previous) => {
      const next = !previous;

      try {
        localStorage.setItem(
          "onkar-ai-document-library-collapsed",
          String(next)
        );
      } catch {
        // Ignore storage errors.
      }

      return next;
    });
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
      <div className="mx-auto max-w-5xl overflow-hidden">
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
            {!isCollapsed &&
              !deleteMode &&
              documents.length > 0 && (
                <button
                  type="button"
                  onClick={
                    handleBulkSelection
                  }
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
                  {bulkAction ===
                  "selecting"
                    ? "Selecting..."
                    : bulkAction ===
                      "deselecting"
                    ? "Deselecting..."
                    : documents.every(
                        (document) =>
                          document.is_selected
                      )
                    ? "Deselect All"
                    : "Select All"}
                </button>
              )}

            {!isCollapsed &&
              documents.length > 0 && (
                <>
                  <button
                    type="button"
                    onClick={
                      toggleBulkDeleteMode
                    }
                    disabled={
                      loading ||
                      actionId !== null ||
                      bulkAction !== null
                    }
                    className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                      deleteMode
                        ? "border-red-500 bg-red-500/10 text-red-500"
                        : isDark
                        ? "border-slate-700 hover:bg-slate-800"
                        : "border-slate-300 hover:bg-slate-100"
                    } disabled:cursor-not-allowed disabled:opacity-50`}
                  >
                    {deleteMode
                      ? "Cancel Delete"
                      : "Bulk Delete"}
                  </button>

                  {deleteMode && (
                    <button
                      type="button"
                      onClick={
                        handleBulkDelete
                      }
                      disabled={
                        loading ||
                        bulkAction !==
                          null ||
                        bulkDeleteIds.length ===
                          0
                      }
                      className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {bulkAction ===
                      "deleting"
                        ? "Deleting..."
                        : `Delete Selected (${bulkDeleteIds.length})`}
                    </button>
                  )}
                </>
              )}

            {!isCollapsed && (
              <button
                type="button"
                onClick={loadDocuments}
                disabled={
                  loading ||
                  bulkAction !== null
                }
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                  isDark
                    ? "border-slate-700 hover:bg-slate-800"
                    : "border-slate-300 hover:bg-slate-100"
                } disabled:cursor-not-allowed disabled:opacity-50`}
              >
                {loading
                  ? "Loading..."
                  : "Refresh"}
              </button>
            )}

            <button
              type="button"
              onClick={toggleCollapsed}
              disabled={
                bulkAction === "deleting"
              }
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                isDark
                  ? "border-slate-700 hover:bg-slate-800"
                  : "border-slate-300 hover:bg-slate-100"
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              {isCollapsed
                ? "Expand"
                : "Collapse"}
            </button>
          </div>
        </div>

        {!isCollapsed && (
          <>
            {documents.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <div className="relative flex items-center">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(event) =>
                      setSearchQuery(
                        event.target.value
                      )
                    }
                    placeholder="Search PDFs..."
                    disabled={
                      loading ||
                      bulkAction !== null
                    }
                    className={`w-44 rounded-lg border px-3 py-1.5 pr-8 text-xs outline-none transition sm:w-56 ${
                      isDark
                        ? "border-slate-800 bg-slate-900 text-slate-100 placeholder-slate-500 focus:border-slate-700"
                        : "border-slate-200 bg-slate-50 text-slate-800 placeholder-slate-400 focus:border-slate-300"
                    }`}
                  />

                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() =>
                        setSearchQuery("")
                      }
                      disabled={
                        loading ||
                        bulkAction !== null
                      }
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-slate-400 hover:text-slate-600"
                      aria-label="Clear PDF search"
                    >
                      ✕
                    </button>
                  )}
                </div>

                <select
                  value={sortOption}
                  onChange={(event) => {
                    const value =
                      event.target.value;

                    setSortOption(value);

                    try {
                      localStorage.setItem(
                        "onkar-ai-document-sort",
                        value
                      );
                    } catch {
                      // Ignore storage errors.
                    }
                  }}
                  disabled={
                    loading ||
                    bulkAction !== null
                  }
                  className={`rounded-lg border px-2 py-1.5 text-xs outline-none transition disabled:cursor-not-allowed disabled:opacity-50 ${
                    isDark
                      ? "border-slate-800 bg-slate-900 text-slate-100 focus:border-slate-700"
                      : "border-slate-200 bg-slate-50 text-slate-800 focus:border-slate-300"
                  }`}
                >
                  <option value="newest">
                    Newest first
                  </option>

                  <option value="name-asc">
                    Name A–Z
                  </option>

                  <option value="name-desc">
                    Name Z–A
                  </option>

                  <option value="selected">
                    Selected first
                  </option>
                </select>

                {deleteMode && (
                  <>
                    <button
                      type="button"
                      onClick={
                        toggleAllDeleteCandidates
                      }
                      disabled={
                        loading ||
                        bulkAction !==
                          null ||
                        filteredDocuments.length ===
                          0
                      }
                      className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                        isDark
                          ? "border-red-500/60 text-red-400 hover:bg-red-500/10"
                          : "border-red-300 text-red-600 hover:bg-red-50"
                      } disabled:cursor-not-allowed disabled:opacity-50`}
                    >
                      {allFilteredMarkedForDelete
                        ? "Clear Delete Selection"
                        : "Select Filtered PDFs"}
                    </button>

                    <span className="text-xs text-red-500">
                      {
                        bulkDeleteIds.length
                      }{" "}
                      marked for deletion
                    </span>
                  </>
                )}
              </div>
            )}

            {error && (
              <p className="mt-3 text-xs text-red-500">
                {error}
              </p>
            )}

            {deleteSummary && (
              <div
                className={`mt-3 rounded-xl border p-3 text-xs ${
                  isDark
                    ? "border-slate-700 bg-slate-900"
                    : "border-slate-200 bg-slate-50"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold">
                      Bulk delete result
                    </p>

                    {deleteSummary.deleted
                      .length > 0 && (
                      <p className="mt-2 break-words text-emerald-500">
                        Deleted:{" "}
                        {deleteSummary.deleted.join(
                          ", "
                        )}
                      </p>
                    )}

                    {deleteSummary.failed
                      .length > 0 && (
                      <p className="mt-2 break-words text-red-500">
                        Failed:{" "}
                        {deleteSummary.failed.join(
                          ", "
                        )}
                      </p>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() =>
                      setDeleteSummary(null)
                    }
                    className="shrink-0 rounded-md px-2 py-1 text-slate-500 hover:bg-slate-500/10"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}

            {!loading &&
              documents.length === 0 && (
                <p className="mt-3 text-xs text-slate-500">
                  No PDF is uploaded in
                  this chat.
                </p>
              )}

            {!loading &&
              documents.length > 0 &&
              filteredDocuments.length ===
                0 && (
                <p className="mt-3 text-xs text-slate-500">
                  No PDFs match your
                  search.
                </p>
              )}

            {documents.length > 0 &&
              filteredDocuments.length >
                0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {pagedDocuments.map(
                    (document) => {
                      const isBusy =
                        actionId ===
                          document.document_id ||
                        bulkAction !== null;

                      const previewUrls =
                        buildPdfPreviewUrls({
                          filename:
                            document.filename,
                          chatId:
                            activeChatId,
                          page: 1,
                        });

                      const markedForDelete =
                        bulkDeleteIds.includes(
                          document.document_id
                        );

                      return (
                        <div
                          key={
                            document.document_id
                          }
                          className={`flex max-w-full items-center gap-2 rounded-xl border px-3 py-2 ${
                            deleteMode &&
                            markedForDelete
                              ? "border-red-500 bg-red-500/10"
                              : isDark
                              ? "border-slate-700 bg-slate-900"
                              : "border-slate-200 bg-slate-50"
                          }`}
                        >
                          {deleteMode ? (
                            <input
                              type="checkbox"
                              checked={
                                markedForDelete
                              }
                              disabled={
                                isBusy
                              }
                              onChange={() =>
                                toggleDeleteCandidate(
                                  document.document_id
                                )
                              }
                              aria-label={`Mark ${document.filename} for deletion`}
                              className="h-4 w-4 cursor-pointer accent-red-500"
                            />
                          ) : (
                            <input
                              type="checkbox"
                              checked={
                                document.is_selected
                              }
                              disabled={
                                isBusy
                              }
                              onChange={() =>
                                handleSelectionChange(
                                  document
                                )
                              }
                              aria-label={`Select ${document.filename}`}
                              className="h-4 w-4 cursor-pointer accent-emerald-500"
                            />
                          )}

                          <div className="min-w-0 flex-1">
                            <p
                              className="max-w-52 truncate text-xs font-medium sm:max-w-72"
                              title={
                                document.filename
                              }
                            >
                              {
                                document.filename
                              }
                            </p>

                            <p className="text-[11px] text-slate-500">
                              {
                                document.page_count
                              }{" "}
                              page
                              {document.page_count ===
                              1
                                ? ""
                                : "s"}
                              {" • "}
                              {document.size_kb}{" "}
                              KB
                              {" • "}
                              {document.status}
                            </p>
                          </div>

                          <button
                            type="button"
                            disabled={
                              isBusy ||
                              !previewUrls
                            }
                            onClick={() =>
                              setPreviewSource({
                                filename:
                                  document.filename,
                                chat_id:
                                  activeChatId,
                                page: 1,
                              })
                            }
                            className={`rounded-md px-2 py-1 text-xs transition ${
                              isDark
                                ? "text-blue-400 hover:bg-blue-500/10"
                                : "text-blue-600 hover:bg-blue-500/10"
                            } disabled:cursor-not-allowed disabled:opacity-50`}
                          >
                            Preview
                          </button>

                          {previewUrls && (
                            <a
                              href={
                                previewUrls.viewerUrl
                              }
                              target="_blank"
                              rel="noopener noreferrer"
                              className={`rounded-md px-2 py-1 text-xs transition ${
                                isBusy
                                  ? "pointer-events-none opacity-50"
                                  : ""
                              } ${
                                isDark
                                  ? "text-slate-300 hover:bg-slate-800"
                                  : "text-slate-600 hover:bg-slate-200"
                              }`}
                            >
                              Open ↗
                            </a>
                          )}

                          {!deleteMode && (
                            <button
                              type="button"
                              disabled={
                                isBusy
                              }
                              onClick={() =>
                                handleDelete(
                                  document
                                )
                              }
                              className="rounded-md px-2 py-1 text-xs text-red-500 transition hover:bg-red-500/10 disabled:opacity-50"
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      );
                    }
                  )}
                </div>
              )}

            {!loading &&
              showPagination && (
                <div className="mt-3 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() =>
                      setCurrentPage(
                        (page) =>
                          Math.max(
                            1,
                            page - 1
                          )
                      )
                    }
                    disabled={
                      safePage === 1 ||
                      bulkAction !== null
                    }
                    className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                      isDark
                        ? "border-slate-700 hover:bg-slate-800"
                        : "border-slate-300 hover:bg-slate-100"
                    } disabled:cursor-not-allowed disabled:opacity-40`}
                  >
                    Previous
                  </button>

                  <span className="text-xs text-slate-500">
                    Page {safePage} of{" "}
                    {totalPages}
                  </span>

                  <button
                    type="button"
                    onClick={() =>
                      setCurrentPage(
                        (page) =>
                          Math.min(
                            totalPages,
                            page + 1
                          )
                      )
                    }
                    disabled={
                      safePage ===
                        totalPages ||
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

      {previewSource && (
        <PdfPreviewModal
          source={previewSource}
          onClose={() =>
            setPreviewSource(null)
          }
        />
      )}
    </section>
  );
}

export default DocumentLibrary;