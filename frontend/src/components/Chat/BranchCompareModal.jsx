import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  getBranchParentComparison,
} from "../../services/chatService";


const PAGE_SIZE = 20;
const SHOW_ALL_LIMIT = 200;

const initialVisibleLimits = {
  common: PAGE_SIZE,
  parentOnly: PAGE_SIZE,
  branchOnly: PAGE_SIZE,
};

const unavailableMessages = {
  detached_branch:
    "This chat is no longer attached to a parent, so there is no exact comparison available.",
  parent_missing:
    "The immediate parent chat could not be found.",
  parent_boundary_missing:
    "The original parent-side branch boundary is unavailable.",
  branch_boundary_missing:
    "The copied branch-side boundary is unavailable for this legacy or detached branch.",
  parent_source_message_missing:
    "The exact source message no longer exists in the immediate parent chat.",
  branch_source_message_missing:
    "The exact copied source message no longer exists in this branch.",
};


function toPositiveId(value) {
  const numericId = Number(value);

  return Number.isInteger(numericId) &&
    numericId > 0
    ? numericId
    : null;
}


function timestampDetails(value) {
  if (!value) {
    return {
      dateTime: null,
      label: "Timestamp unavailable",
    };
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return {
      dateTime: null,
      label: "Invalid timestamp",
    };
  }

  return {
    dateTime: String(value),
    label: new Intl.DateTimeFormat(
      "en-IN",
      {
        dateStyle: "medium",
        timeStyle: "short",
      }
    ).format(date),
  };
}


function isCancellation(error, signal) {
  return Boolean(
    signal?.aborted ||
    error?.code === "ERR_CANCELED" ||
    error?.name === "CanceledError" ||
    error?.name === "AbortError"
  );
}


function ComparisonMessageCard({
  message,
  isDark,
  accent = "slate",
}) {
  const timestamp = timestampDetails(
    message?.created_at
  );
  const role = String(
    message?.role || "unknown"
  );
  const roleLabel =
    role.charAt(0).toUpperCase() +
    role.slice(1);
  const content = String(
    message?.content || ""
  );

  const accentClasses = {
    blue: isDark
      ? "border-blue-500/40 bg-blue-500/10"
      : "border-blue-200 bg-blue-50",
    emerald: isDark
      ? "border-emerald-500/40 bg-emerald-500/10"
      : "border-emerald-200 bg-emerald-50",
    slate: isDark
      ? "border-slate-700 bg-slate-900"
      : "border-slate-200 bg-white",
  };

  return (
    <article
      className={`rounded-xl border p-3 ${
        accentClasses[accent] ||
        accentClasses.slate
      }`}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${
            isDark
              ? "bg-slate-800 text-slate-300"
              : "bg-slate-100 text-slate-700"
          }`}
        >
          {roleLabel}
        </span>

        {timestamp.dateTime ? (
          <time
            dateTime={timestamp.dateTime}
            className={
              isDark
                ? "text-[11px] text-slate-400"
                : "text-[11px] text-slate-500"
            }
          >
            {timestamp.label}
          </time>
        ) : (
          <span
            className={
              isDark
                ? "text-[11px] text-slate-500"
                : "text-[11px] text-slate-500"
            }
          >
            {timestamp.label}
          </span>
        )}
      </div>

      <p
        className={`max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-relaxed ${
          isDark
            ? "text-slate-200"
            : "text-slate-800"
        }`}
      >
        {content || "No message content."}
      </p>
    </article>
  );
}


function ComparisonSection({
  title,
  description,
  messages = [],
  totalCount,
  visibleCount,
  onShowMore,
  onShowAll,
  emptyMessage,
  isDark,
}) {
  const visibleMessages = messages.slice(
    0,
    visibleCount
  );
  const hasMore =
    visibleMessages.length < messages.length;
  const canShowAll =
    hasMore && messages.length <= SHOW_ALL_LIMIT;

  return (
    <section
      className={`min-w-0 rounded-xl border p-3 ${
        isDark
          ? "border-slate-700 bg-slate-900/70"
          : "border-slate-200 bg-slate-50"
      }`}
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="text-sm font-semibold">
            {title}
          </h4>

          {description && (
            <p
              className={`mt-1 text-xs ${
                isDark
                  ? "text-slate-400"
                  : "text-slate-600"
              }`}
            >
              {description}
            </p>
          )}
        </div>

        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
            isDark
              ? "bg-slate-800 text-slate-300"
              : "bg-white text-slate-700"
          }`}
          title={`${totalCount} total messages`}
        >
          {totalCount}
        </span>
      </div>

      {visibleMessages.length > 0 ? (
        <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
          {visibleMessages.map(
            (message) => (
              <ComparisonMessageCard
                key={message.id}
                message={message}
                isDark={isDark}
              />
            )
          )}
        </div>
      ) : (
        <p
          className={`rounded-lg border border-dashed px-3 py-4 text-center text-sm ${
            isDark
              ? "border-slate-700 text-slate-400"
              : "border-slate-300 text-slate-600"
          }`}
        >
          {emptyMessage}
        </p>
      )}

      {hasMore && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onShowMore}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              isDark
                ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                : "bg-white text-slate-700 hover:bg-slate-100"
            }`}
          >
            Show next {Math.min(
              PAGE_SIZE,
              messages.length -
                visibleMessages.length
            )}
          </button>

          {canShowAll && (
            <button
              type="button"
              onClick={onShowAll}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                isDark
                  ? "text-blue-300 hover:bg-blue-500/10"
                  : "text-blue-700 hover:bg-blue-50"
              }`}
            >
              Show all
            </button>
          )}
        </div>
      )}
    </section>
  );
}


function BranchCompareModal({
  open,
  branchChatId,
  onClose,
  theme = "dark",
}) {
  const [comparison, setComparison] =
    useState(null);
  const [loading, setLoading] =
    useState(false);
  const [error, setError] =
    useState(null);
  const [retryKey, setRetryKey] =
    useState(0);
  const [visibleLimits, setVisibleLimits] =
    useState(initialVisibleLimits);
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);
  const requestIdRef = useRef(0);
  const isDark = theme === "dark";

  useEffect(() => {
    if (!open) return undefined;

    const previousOverflow =
      document.body.style.overflow;

    document.body.style.overflow = "hidden";

    const focusTimer = window.setTimeout(
      () => {
        closeButtonRef.current?.focus();
      },
      0
    );

    return () => {
      window.clearTimeout(focusTimer);
      document.body.style.overflow =
        previousOverflow;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;

    const numericBranchChatId =
      toPositiveId(branchChatId);

    if (numericBranchChatId === null) {
      setComparison(null);
      setLoading(false);
      setError(
        "A valid branch chat is required for comparison."
      );
      return undefined;
    }

    const controller = new AbortController();
    const requestId =
      requestIdRef.current + 1;

    requestIdRef.current = requestId;
    setComparison(null);
    setError(null);
    setLoading(true);
    setVisibleLimits(initialVisibleLimits);

    getBranchParentComparison(
      numericBranchChatId,
      {
        signal: controller.signal,
      }
    )
      .then((response) => {
        if (
          controller.signal.aborted ||
          requestIdRef.current !== requestId
        ) {
          return;
        }

        setComparison(response?.data || null);
        setVisibleLimits(initialVisibleLimits);
      })
      .catch((requestError) => {
        if (
          isCancellation(
            requestError,
            controller.signal
          ) ||
          requestIdRef.current !== requestId
        ) {
          return;
        }

        setError(
          requestError?.response?.data?.detail ||
            requestError?.message ||
            "Unable to load the branch comparison."
        );
      })
      .finally(() => {
        if (
          !controller.signal.aborted &&
          requestIdRef.current === requestId
        ) {
          setLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [
    open,
    branchChatId,
    retryKey,
  ]);

  if (!open) return null;

  function handleDialogKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose?.();
      return;
    }

    if (event.key !== "Tab") return;

    const focusableElements = Array.from(
      dialogRef.current?.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      ) || []
    ).filter(
      (element) =>
        !element.hasAttribute("hidden")
    );

    if (focusableElements.length === 0) {
      event.preventDefault();
      dialogRef.current?.focus();
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement =
      focusableElements[
        focusableElements.length - 1
      ];
    const activeElement =
      document.activeElement;

    if (
      event.shiftKey &&
      (
        activeElement === firstElement ||
        activeElement === dialogRef.current
      )
    ) {
      event.preventDefault();
      lastElement.focus();
    } else if (
      !event.shiftKey &&
      activeElement === lastElement
    ) {
      event.preventDefault();
      firstElement.focus();
    }
  }

  function increaseLimit(groupName) {
    setVisibleLimits((current) => ({
      ...current,
      [groupName]:
        current[groupName] + PAGE_SIZE,
    }));
  }

  function showAll(groupName, messages) {
    setVisibleLimits((current) => ({
      ...current,
      [groupName]: messages.length,
    }));
  }

  const parentTitle =
    comparison?.parent_chat?.title ||
    "Parent unavailable";
  const branchTitle =
    comparison?.branch_chat?.title ||
    "Branch chat";
  const unavailableMessage =
    unavailableMessages[comparison?.reason] ||
    "This branch cannot be compared exactly because its branch metadata is incomplete.";

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-2 backdrop-blur-sm sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose?.();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="branch-compare-title"
        aria-busy={loading}
        tabIndex={-1}
        onKeyDown={handleDialogKeyDown}
        onMouseDown={(event) =>
          event.stopPropagation()
        }
        className={`flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border shadow-2xl ${
          isDark
            ? "border-slate-700 bg-slate-950 text-white"
            : "border-slate-200 bg-white text-slate-900"
        }`}
      >
        <header
          className={`flex shrink-0 items-start justify-between gap-4 border-b px-4 py-3 sm:px-5 ${
            isDark
              ? "border-slate-800"
              : "border-slate-200"
          }`}
        >
          <div className="min-w-0">
            <h2
              id="branch-compare-title"
              className="text-lg font-bold"
            >
              Branch Compare
            </h2>

            <div
              className={`mt-1 flex min-w-0 flex-wrap items-center gap-2 text-xs ${
                isDark
                  ? "text-slate-400"
                  : "text-slate-600"
              }`}
            >
              <span
                className="max-w-[40vw] truncate sm:max-w-xs"
                title={parentTitle}
              >
                Parent: {parentTitle}
              </span>
              <span aria-hidden="true">/</span>
              <span
                className="max-w-[40vw] truncate sm:max-w-xs"
                title={branchTitle}
              >
                Branch: {branchTitle}
              </span>
            </div>
          </div>

          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-lg transition ${
              isDark
                ? "hover:bg-slate-800"
                : "hover:bg-slate-100"
            }`}
            aria-label="Close Branch Compare"
          >
            ×
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-3 sm:p-5">
          {loading && (
            <div
              className={`rounded-xl border px-4 py-8 text-center ${
                isDark
                  ? "border-slate-700 bg-slate-900 text-slate-300"
                  : "border-slate-200 bg-slate-50 text-slate-700"
              }`}
            >
              Loading the exact parent and branch comparison…
            </div>
          )}

          {!loading && error && (
            <div
              role="alert"
              className={`rounded-xl border p-4 ${
                isDark
                  ? "border-red-500/40 bg-red-500/10 text-red-200"
                  : "border-red-200 bg-red-50 text-red-800"
              }`}
            >
              <h3 className="font-semibold">
                Comparison could not be loaded
              </h3>
              <p className="mt-1 break-words text-sm">
                {error}
              </p>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() =>
                    setRetryKey(
                      (current) => current + 1
                    )
                  }
                  className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-blue-700"
                >
                  Retry
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
                    isDark
                      ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                      : "bg-white text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  Close
                </button>
              </div>
            </div>
          )}

          {!loading &&
            !error &&
            comparison &&
            !comparison.comparable && (
              <div
                className={`rounded-xl border p-4 ${
                  isDark
                    ? "border-amber-500/40 bg-amber-500/10"
                    : "border-amber-200 bg-amber-50"
                }`}
              >
                <h3 className="font-semibold">
                  Exact comparison unavailable
                </h3>
                <p
                  className={`mt-2 text-sm ${
                    isDark
                      ? "text-slate-300"
                      : "text-slate-700"
                  }`}
                >
                  {unavailableMessage}
                </p>
                <p
                  className={`mt-2 text-xs ${
                    isDark
                      ? "text-slate-400"
                      : "text-slate-600"
                  }`}
                >
                  No divergence point or message counts were guessed.
                </p>
                <button
                  type="button"
                  onClick={onClose}
                  className="mt-4 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-blue-700"
                >
                  Close
                </button>
              </div>
            )}

          {!loading &&
            !error &&
            comparison?.comparable && (
              <div className="space-y-4">
                <section
                  aria-label="Comparison summary"
                  className="grid grid-cols-1 gap-2 sm:grid-cols-3"
                >
                  {[
                    [
                      "Common",
                      comparison.counts?.common,
                    ],
                    [
                      "Parent only",
                      comparison.counts
                        ?.parent_only,
                    ],
                    [
                      "Branch only",
                      comparison.counts
                        ?.branch_only,
                    ],
                  ].map(([label, count]) => (
                    <div
                      key={label}
                      className={`rounded-xl border px-3 py-2 ${
                        isDark
                          ? "border-slate-700 bg-slate-900"
                          : "border-slate-200 bg-slate-50"
                      }`}
                    >
                      <p
                        className={
                          isDark
                            ? "text-xs text-slate-400"
                            : "text-xs text-slate-600"
                        }
                      >
                        {label}
                      </p>
                      <p className="mt-1 text-xl font-bold">
                        {count ?? 0}
                      </p>
                    </div>
                  ))}
                </section>

                <section
                  className={`rounded-xl border p-3 ${
                    isDark
                      ? "border-violet-500/40 bg-violet-500/10"
                      : "border-violet-200 bg-violet-50"
                  }`}
                >
                  <div className="mb-3">
                    <h3 className="font-semibold">
                      Exact divergence point
                    </h3>
                    <p
                      className={`mt-1 text-xs ${
                        isDark
                          ? "text-slate-400"
                          : "text-slate-600"
                      }`}
                    >
                      The original parent message and its copied branch equivalent.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    <div className="min-w-0">
                      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-blue-500">
                        Parent source message
                      </h4>
                      <ComparisonMessageCard
                        message={
                          comparison.parent_source_message
                        }
                        isDark={isDark}
                        accent="blue"
                      />
                    </div>

                    <div className="min-w-0">
                      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-500">
                        Copied branch source message
                      </h4>
                      <ComparisonMessageCard
                        message={
                          comparison.branch_source_message
                        }
                        isDark={isDark}
                        accent="emerald"
                      />
                    </div>
                  </div>
                </section>

                <ComparisonSection
                  title="Common copied history"
                  description="Branch-side copied messages through the exact divergence point."
                  messages={
                    comparison.common_messages || []
                  }
                  totalCount={
                    comparison.counts?.common ?? 0
                  }
                  visibleCount={
                    visibleLimits.common
                  }
                  onShowMore={() =>
                    increaseLimit("common")
                  }
                  onShowAll={() =>
                    showAll(
                      "common",
                      comparison.common_messages ||
                        []
                    )
                  }
                  emptyMessage="No common copied messages are available."
                  isDark={isDark}
                />

                <section>
                  <div className="mb-2">
                    <h3 className="font-semibold">
                      Divergent continuation
                    </h3>
                    <p
                      className={`mt-1 text-xs ${
                        isDark
                          ? "text-slate-400"
                          : "text-slate-600"
                      }`}
                    >
                      Messages created after the exact branch point on each side.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                    <ComparisonSection
                      title="Parent-only messages"
                      messages={
                        comparison.parent_only_messages ||
                        []
                      }
                      totalCount={
                        comparison.counts
                          ?.parent_only ?? 0
                      }
                      visibleCount={
                        visibleLimits.parentOnly
                      }
                      onShowMore={() =>
                        increaseLimit(
                          "parentOnly"
                        )
                      }
                      onShowAll={() =>
                        showAll(
                          "parentOnly",
                          comparison.parent_only_messages ||
                            []
                        )
                      }
                      emptyMessage="Parent has no messages after the branch point."
                      isDark={isDark}
                    />

                    <ComparisonSection
                      title="Branch-only messages"
                      messages={
                        comparison.branch_only_messages ||
                        []
                      }
                      totalCount={
                        comparison.counts
                          ?.branch_only ?? 0
                      }
                      visibleCount={
                        visibleLimits.branchOnly
                      }
                      onShowMore={() =>
                        increaseLimit(
                          "branchOnly"
                        )
                      }
                      onShowAll={() =>
                        showAll(
                          "branchOnly",
                          comparison.branch_only_messages ||
                            []
                        )
                      }
                      emptyMessage="Branch has no messages after the branch point."
                      isDark={isDark}
                    />
                  </div>
                </section>
              </div>
            )}
        </div>
      </div>
    </div>
  );
}


export default BranchCompareModal;
