import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  buildPdfPreviewUrls,
  validatePdfPreviewUrl,
} from "../../services/documentService";

function PdfPreviewModal({
  source,
  onClose,
}) {
 const previewUrls = useMemo(
  () =>
    buildPdfPreviewUrls({
      filename:
        source?.filename ||
        source?.title,
      chatId:
        source?.chat_id ??
        source?.chatId,
      page: source?.page,
    }),
  [
    source?.filename,
    source?.title,
    source?.chat_id,
    source?.chatId,
    source?.page,
  ]
);

  const [status, setStatus] =
    useState("validating");

  const [errorMessage, setErrorMessage] =
    useState("");

  const displayFilename =
    previewUrls?.filename ||
    source?.filename ||
    source?.title ||
    "PDF document";

  const displayPage =
    previewUrls?.page ?? 1;

  const validate = useCallback(async () => {
    if (!previewUrls) {
      setStatus("error");
      setErrorMessage(
        "Missing or invalid PDF source details."
      );
      return;
    }

    setStatus("validating");
    setErrorMessage("");

    try {
      await validatePdfPreviewUrl(
        previewUrls.validationUrl
      );
      setStatus("ready");
    } catch (error) {
      setStatus("error");
      setErrorMessage(
        error?.message ||
          "Unable to load PDF preview."
      );
    }
  }, [previewUrls]);

  useEffect(() => {
    validate();
  }, [validate]);

  useEffect(() => {
    const previousOverflow =
      document.body.style.overflow;

    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow =
        previousOverflow;
    };
  }, []);

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose?.();
      }
    }

    document.addEventListener(
      "keydown",
      handleKeyDown
    );

    return () => {
      document.removeEventListener(
        "keydown",
        handleKeyDown
      );
    };
  }, [onClose]);

  function handleOverlayClick(event) {
    if (
      event.target ===
      event.currentTarget
    ) {
      onClose?.();
    }
  }

  return (
    <div
      onClick={handleOverlayClick}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 px-3 py-4 backdrop-blur-sm sm:px-4"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`PDF preview: ${displayFilename}, page ${displayPage}`}
        className="flex h-[min(92vh,900px)] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 text-white shadow-2xl"
        onClick={(event) =>
          event.stopPropagation()
        }
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-700 p-4 sm:p-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span
                className="text-xl"
                aria-hidden="true"
              >
                📄
              </span>

              <h2
                className="truncate text-base font-semibold sm:text-lg"
                title={displayFilename}
              >
                {displayFilename}
              </h2>
            </div>

            <p className="mt-1 text-sm text-slate-400">
              Page {displayPage}
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg p-2 text-xl text-slate-400 transition hover:bg-slate-800 hover:text-white"
            aria-label="Close PDF preview"
          >
            ✕
          </button>
        </div>

        <div className="relative min-h-0 flex-1 bg-slate-950">
          {status === "validating" && (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <div
                className="h-10 w-10 animate-spin rounded-full border-4 border-slate-700 border-t-blue-500"
                aria-hidden="true"
              />

              <p className="text-sm text-slate-300">
                Validating PDF preview...
              </p>
            </div>
          )}

          {status === "error" && (
            <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
              <div
                className="text-4xl"
                aria-hidden="true"
              >
                ⚠️
              </div>

              <div>
                <p className="text-base font-semibold text-slate-100">
                  Unable to preview PDF
                </p>

                <p className="mt-2 max-w-md text-sm text-slate-400">
                  {errorMessage}
                </p>
              </div>

              <div className="flex flex-wrap items-center justify-center gap-3">
                <button
                  type="button"
                  onClick={validate}
                  className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-500"
                >
                  Retry
                </button>

                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-700"
                >
                  Close
                </button>
              </div>
            </div>
          )}

          {status === "ready" &&
            previewUrls && (
              <iframe
                title={`${displayFilename} — page ${displayPage}`}
                src={previewUrls.viewerUrl}
                className="h-full w-full border-0 bg-white"
              />
            )}
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-3 border-t border-slate-700 p-4 sm:p-5">
          {previewUrls && (
            <a
              href={previewUrls.viewerUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-700"
            >
              Open in new tab
            </a>
          )}

          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default PdfPreviewModal;
