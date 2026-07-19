import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  getBranchParentComparison,
  mergeBranchIntoParent,
} from "../../services/chatService";
import {
  BRANCH_MERGE_PENDING_KEY,
  buildBranchMergeRequest,
  buildCanonicalMergeUnits,
  createPendingBranchMerge,
  evaluateCanonicalMergeSelection,
  getBranchMergeFailurePolicy,
  getMergedMessageNavigationTarget,
  isCompletedBranchMergeResponse,
  parsePendingBranchMerge,
  selectedKeysFromPending,
} from "../../utils/branchMerge";


const PAGE_SIZE = 20;
const SHOW_ALL_LIMIT = 200;

const unavailableMessages = {
  detached_branch:
    "This chat is no longer attached to a parent, so an exact merge preview is unavailable.",
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


function createVisibleLimits() {
  return {
    common: PAGE_SIZE,
    parentOnly: PAGE_SIZE,
    turns: PAGE_SIZE,
    selected: PAGE_SIZE,
  };
}


function toPositiveId(value) {
  const numericId = Number(value);

  return Number.isInteger(numericId) &&
    numericId > 0
    ? numericId
    : null;
}


function normalizeRole(value) {
  return [
    "user",
    "assistant",
    "system",
  ].includes(value)
    ? value
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


function buildConversationUnits(comparison) {
  if (comparison?.merge_preview) {
    return buildCanonicalMergeUnits(comparison);
  }

  const sourceMessage =
    comparison?.branch_source_message || null;
  const sourceId = toPositiveId(
    comparison?.branch_message_id
  );
  const sourceRole = normalizeRole(
    sourceMessage?.role
  );
  const sourceAnchorId = toPositiveId(
    sourceMessage?.id
  );
  const hasExactSourceAnchor =
    sourceId !== null &&
    sourceRole === "user" &&
    sourceAnchorId === sourceId;
  const rawMessages = Array.isArray(
    comparison?.branch_only_messages
  )
    ? comparison.branch_only_messages
    : [];
  const messagesById = new Map();
  let invalidIdCount = 0;

  for (const rawMessage of rawMessages) {
    const id = toPositiveId(rawMessage?.id);

    if (id === null) {
      invalidIdCount += 1;
      continue;
    }

    const records =
      messagesById.get(id) || [];

    records.push({
      ...rawMessage,
      id,
    });
    messagesById.set(id, records);
  }

  const orderedEntries = Array.from(
    messagesById.entries()
  )
    .sort(([leftId], [rightId]) =>
      leftId - rightId
    )
    .map(([id, records]) => {
      if (records.length > 1) {
        return {
          kind: "duplicate",
          id,
          messages: records,
        };
      }

      const message = records[0];
      const role = normalizeRole(
        message?.role
      );

      if (role === null) {
        return {
          kind: "unknown",
          id,
          messages: [message],
        };
      }

      return {
        kind: "message",
        id,
        message: {
          ...message,
          role,
        },
      };
    });

  const units = [];
  let currentTurn = null;
  let sourceContinuation = null;
  let orphanGroup = null;
  let isLeadingContinuation = true;

  function flushCurrentTurn() {
    if (currentTurn) {
      units.push(currentTurn);
      currentTurn = null;
    }
  }

  function flushSourceContinuation() {
    if (
      sourceContinuation &&
      sourceContinuation.messages.length > 0
    ) {
      units.push(sourceContinuation);
    }

    sourceContinuation = null;
  }

  function flushOrphanGroup() {
    if (
      orphanGroup &&
      orphanGroup.messages.length > 0
    ) {
      units.push(orphanGroup);
    }

    orphanGroup = null;
  }

  function flushOpenUnits() {
    flushCurrentTurn();
    flushSourceContinuation();
    flushOrphanGroup();
  }

  for (const entry of orderedEntries) {
    if (entry.kind !== "message") {
      flushOpenUnits();

      units.push({
        key:
          entry.kind === "duplicate"
            ? "duplicate:" + entry.id
            : "unknown:" + entry.id,
        type: "locked",
        selectable: false,
        anchor: null,
        messages:
          entry.kind === "duplicate"
            ? []
            : entry.messages,
        invalidRecordCount:
          entry.kind === "duplicate"
            ? entry.messages.length
            : 0,
        reason:
          entry.kind === "duplicate"
            ? "Multiple branch records share this message ID, so no safe identity can be chosen."
            : "This record has an unknown role and cannot be grouped safely.",
      });

      isLeadingContinuation = false;
      continue;
    }

    const message = entry.message;

    if (message.role === "user") {
      flushOpenUnits();

      currentTurn = {
        key: "user:" + message.id,
        type: "turn",
        selectable: true,
        anchor: message,
        messages: [message],
        reason: null,
      };

      isLeadingContinuation = false;
      continue;
    }

    if (
      isLeadingContinuation &&
      hasExactSourceAnchor
    ) {
      flushOrphanGroup();

      if (!sourceContinuation) {
        sourceContinuation = {
          key: "source:" + sourceId,
          type: "source",
          selectable: true,
          anchor: {
            ...sourceMessage,
            id: sourceId,
            role: "user",
          },
          messages: [],
          reason: null,
        };
      }

      sourceContinuation.messages.push(
        message
      );
      continue;
    }

    if (currentTurn) {
      currentTurn.messages.push(message);
      continue;
    }

    flushSourceContinuation();

    if (!orphanGroup) {
      orphanGroup = {
        key: "orphan:" + message.id,
        type: "orphan",
        selectable: false,
        anchor: null,
        messages: [],
        reason:
          "These assistant or system messages have no exact user prompt anchor and cannot be selected safely.",
      };
    }

    orphanGroup.messages.push(message);
  }

  flushOpenUnits();

  if (invalidIdCount > 0) {
    units.push({
      key: "invalid-records",
      type: "locked",
      selectable: false,
      anchor: null,
      messages: [],
      invalidRecordCount: invalidIdCount,
      reason:
        invalidIdCount +
        " branch record(s) have a missing or nonpositive message ID and cannot be identified safely.",
    });
  }

  return units.map((unit) => ({
    ...unit,
    selectable: false,
    reason:
      "A fresh server-provided canonical merge unit is unavailable. This local grouping is read-only.",
  }));
}


function MessageCard({
  message,
  isDark,
  accent = "slate",
  showMetadata = true,
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
    message?.content ?? ""
  );
  const messageId = toPositiveId(
    message?.id
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
      className={
        "rounded-xl border p-3 " +
        (
          accentClasses[accent] ||
          accentClasses.slate
        )
      }
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={
              "rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide " +
              (
                isDark
                  ? "bg-slate-800 text-slate-300"
                  : "bg-slate-100 text-slate-700"
              )
            }
          >
            {roleLabel}
          </span>

          {messageId !== null && (
            <span
              className={
                isDark
                  ? "text-[11px] text-slate-500"
                  : "text-[11px] text-slate-500"
              }
            >
              Message #{messageId}
            </span>
          )}
        </div>

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
        className={
          "max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-relaxed " +
          (
            isDark
              ? "text-slate-200"
              : "text-slate-800"
          )
        }
      >
        {content || "No message content."}
      </p>

      {showMetadata &&
        (
          message?.has_attachment_metadata ===
            true ||
          message?.has_source_metadata === true
        ) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message
              ?.has_attachment_metadata ===
              true && (
              <span
                className={
                  "rounded px-2 py-0.5 text-[11px] font-semibold " +
                  (
                    isDark
                      ? "bg-amber-500/15 text-amber-300"
                      : "bg-amber-100 text-amber-800"
                  )
                }
              >
                Attachment metadata
              </span>
            )}

            {message
              ?.has_source_metadata ===
              true && (
              <span
                className={
                  "rounded px-2 py-0.5 text-[11px] font-semibold " +
                  (
                    isDark
                      ? "bg-cyan-500/15 text-cyan-300"
                      : "bg-cyan-100 text-cyan-800"
                  )
                }
              >
                Source metadata
              </span>
            )}
          </div>
        )}
    </article>
  );
}


function IncrementalControls({
  visibleCount,
  totalCount,
  onShowMore,
  onShowAll,
  isDark,
  itemLabel,
}) {
  if (visibleCount >= totalCount) {
    return null;
  }

  const remaining =
    totalCount - visibleCount;
  const canShowAll =
    totalCount <= SHOW_ALL_LIMIT;

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <button
        type="button"
        onClick={onShowMore}
        className={
          "rounded-lg px-3 py-1.5 text-xs font-semibold transition " +
          (
            isDark
              ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
              : "bg-white text-slate-700 hover:bg-slate-100"
          )
        }
      >
        Show next{" "}
        {Math.min(PAGE_SIZE, remaining)}{" "}
        {itemLabel}
      </button>

      {canShowAll && (
        <button
          type="button"
          onClick={onShowAll}
          className={
            "rounded-lg px-3 py-1.5 text-xs font-semibold transition " +
            (
              isDark
                ? "text-blue-300 hover:bg-blue-500/10"
                : "text-blue-700 hover:bg-blue-50"
            )
          }
        >
          Show all
        </button>
      )}
    </div>
  );
}


function MessageSection({
  title,
  description,
  messages,
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

  return (
    <section
      className={
        "min-w-0 rounded-xl border p-3 " +
        (
          isDark
            ? "border-slate-700 bg-slate-900/70"
            : "border-slate-200 bg-slate-50"
        )
      }
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">
            {title}
          </h3>

          {description && (
            <p
              className={
                "mt-1 text-xs " +
                (
                  isDark
                    ? "text-slate-400"
                    : "text-slate-600"
                )
              }
            >
              {description}
            </p>
          )}
        </div>

        <span
          className={
            "shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold " +
            (
              isDark
                ? "bg-slate-800 text-slate-300"
                : "bg-white text-slate-700"
            )
          }
          title={totalCount + " total messages"}
        >
          {totalCount}
        </span>
      </div>

      {visibleMessages.length > 0 ? (
        <div className="space-y-2">
          {visibleMessages.map(
            (message) => (
              <MessageCard
                key={message.id}
                message={message}
                isDark={isDark}
              />
            )
          )}
        </div>
      ) : (
        <p
          className={
            "rounded-lg border border-dashed px-3 py-4 text-center text-sm " +
            (
              isDark
                ? "border-slate-700 text-slate-400"
                : "border-slate-300 text-slate-600"
            )
          }
        >
          {emptyMessage}
        </p>
      )}

      <IncrementalControls
        visibleCount={
          visibleMessages.length
        }
        totalCount={messages.length}
        onShowMore={onShowMore}
        onShowAll={onShowAll}
        isDark={isDark}
        itemLabel="messages"
      />
    </section>
  );
}


function TurnUnitCard({
  unit,
  selected,
  onToggle,
  isDark,
  disabled = false,
}) {
  const checkboxId =
    "merge-preview-" +
    unit.key.replace(/[^a-zA-Z0-9_-]/g, "-");
  const typeLabel = {
    source: "Source-anchored continuation",
    turn: "Conversation turn",
    orphan: "Locked orphan messages",
    locked: "Locked unsafe records",
  }[unit.type] || "Conversation unit";

  return (
    <article
      className={
        "rounded-xl border p-3 " +
        (
          selected
            ? isDark
              ? "border-emerald-500/60 bg-emerald-500/10"
              : "border-emerald-300 bg-emerald-50"
            : unit.selectable
              ? isDark
                ? "border-slate-700 bg-slate-900"
                : "border-slate-200 bg-white"
              : isDark
                ? "border-amber-500/40 bg-amber-500/10"
                : "border-amber-200 bg-amber-50"
        )
      }
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold">
            {typeLabel}
          </p>
          <p
            className={
              "mt-1 text-xs " +
              (
                isDark
                  ? "text-slate-400"
                  : "text-slate-600"
              )
            }
          >
            {unit.messages.length} payload{" "}
            {unit.messages.length === 1
              ? "message"
              : "messages"}
          </p>
        </div>

        {unit.selectable ? (
          <div className="flex shrink-0 items-center gap-2">
            <input
              id={checkboxId}
              type="checkbox"
              checked={selected}
              disabled={disabled}
              onChange={() =>
                onToggle(unit.key)
              }
              className="h-4 w-4 rounded border-slate-400 text-emerald-600 focus:ring-emerald-500"
            />
            <label
              htmlFor={checkboxId}
              className="cursor-pointer text-sm font-semibold"
            >
              Select turn
            </label>
          </div>
        ) : (
          <span
            className={
              "shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold " +
              (
                isDark
                  ? "bg-amber-500/15 text-amber-300"
                  : "bg-amber-100 text-amber-800"
              )
            }
          >
            Locked
          </span>
        )}
      </div>

      {unit.reason && (
        <p
          className={
            "mb-3 rounded-lg border px-3 py-2 text-xs " +
            (
              isDark
                ? "border-amber-500/30 text-amber-200"
                : "border-amber-200 text-amber-900"
            )
          }
        >
          {unit.reason}
        </p>
      )}

      {unit.type === "source" &&
        unit.anchor && (
          <div className="mb-3">
            <p
              className={
                "mb-2 text-xs font-semibold uppercase tracking-wide " +
                (
                  isDark
                    ? "text-blue-300"
                    : "text-blue-700"
                )
              }
            >
              Existing source prompt — context only
            </p>
            <MessageCard
              message={unit.anchor}
              isDark={isDark}
              accent="blue"
              showMetadata={false}
            />
            <p
              className={
                "mt-2 text-xs " +
                (
                  isDark
                    ? "text-slate-400"
                    : "text-slate-600"
                )
              }
            >
              This prompt already has an exact
              equivalent in the parent and is not
              part of the selected payload.
            </p>
          </div>
        )}

      {unit.type === "turn" &&
        unit.anchor && (
          <p
            className={
              "mb-2 text-xs font-semibold uppercase tracking-wide " +
              (
                isDark
                  ? "text-emerald-300"
                  : "text-emerald-700"
              )
            }
          >
            User prompt and continuation
          </p>
        )}

      {unit.messages.length > 0 ? (
        <div className="space-y-2">
          {unit.messages.map(
            (message) => (
              <MessageCard
                key={
                  unit.key +
                  ":" +
                  String(message.id)
                }
                message={message}
                isDark={isDark}
              />
            )
          )}
        </div>
      ) : (
        <p
          className={
            isDark
              ? "text-sm text-slate-400"
              : "text-sm text-slate-600"
          }
        >
          No safely identifiable messages are
          available in this locked group.
        </p>
      )}
    </article>
  );
}


function IssueGroup({
  title,
  issues,
  severity,
  isDark,
}) {
  const classes = {
    blocking: isDark
      ? "border-red-500/40 bg-red-500/10 text-red-100"
      : "border-red-200 bg-red-50 text-red-900",
    warning: isDark
      ? "border-amber-500/40 bg-amber-500/10 text-amber-100"
      : "border-amber-200 bg-amber-50 text-amber-900",
    information: isDark
      ? "border-blue-500/40 bg-blue-500/10 text-blue-100"
      : "border-blue-200 bg-blue-50 text-blue-900",
  };

  return (
    <section
      className={
        "rounded-xl border p-3 " +
        classes[severity]
      }
    >
      <h4 className="text-sm font-semibold">
        {title} ({issues.length})
      </h4>
      {issues.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
          {issues.map((issue) => (
            <li key={issue.id}>
              {issue.message}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs">
          None detected.
        </p>
      )}
    </section>
  );
}


function BranchMergePreviewModal({
  open,
  branchChatId,
  onClose,
  onSelectChat,
  onMergeCompleted,
  mergeCredential = "",
  hasMergeCredential = false,
  onRememberMergeCredential,
  onForgetMergeCredential,
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
  const [
    selectedUnitKeys,
    setSelectedUnitKeys,
  ] = useState(() => new Set());
  const [visibleLimits, setVisibleLimits] =
    useState(createVisibleLimits);
  const [isCommonExpanded, setIsCommonExpanded] =
    useState(false);
  const [step, setStep] = useState("preview");
  const [acknowledged, setAcknowledged] =
    useState(false);
  const [credentialInput, setCredentialInput] =
    useState("");
  const [pendingMerge, setPendingMerge] =
    useState(null);
  const [resumeAvailable, setResumeAvailable] =
    useState(false);
  const [submitting, setSubmitting] =
    useState(false);
  const [submissionError, setSubmissionError] =
    useState(null);
  const [success, setSuccess] = useState(null);
  const [previewNotice, setPreviewNotice] =
    useState(null);
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);
  const confirmationHeadingRef = useRef(null);
  const credentialErrorRef = useRef(null);
  const successHeadingRef = useRef(null);
  const requestIdRef = useRef(0);
  const submissionRequestIdRef = useRef(0);
  const submissionControllerRef = useRef(null);
  const submittingRef = useRef(false);
  const reloadNoticeRef = useRef(null);
  const isDark = theme === "dark";

  function readPendingStorage() {
    try {
      return window.sessionStorage.getItem(
        BRANCH_MERGE_PENDING_KEY
      );
    } catch {
      return null;
    }
  }

  function removePendingStorage() {
    try {
      window.sessionStorage.removeItem(
        BRANCH_MERGE_PENDING_KEY
      );
    } catch {
      // The in-memory copy is still cleared below.
    }

    setPendingMerge(null);
    setResumeAvailable(false);
  }

  function savePendingStorage(pending) {
    try {
      window.sessionStorage.setItem(
        BRANCH_MERGE_PENDING_KEY,
        JSON.stringify(pending)
      );
      return true;
    } catch {
      return false;
    }
  }

  function discardLocalState() {
    requestIdRef.current += 1;
    submissionRequestIdRef.current += 1;
    submissionControllerRef.current?.abort();
    submissionControllerRef.current = null;
    submittingRef.current = false;
    setComparison(null);
    setLoading(false);
    setError(null);
    setSelectedUnitKeys(new Set());
    setVisibleLimits(createVisibleLimits());
    setIsCommonExpanded(false);
    setStep("preview");
    setAcknowledged(false);
    setCredentialInput("");
    setPendingMerge(null);
    setResumeAvailable(false);
    setSubmitting(false);
    setSubmissionError(null);
    setSuccess(null);
    setPreviewNotice(null);
  }

  function requestClose() {
    discardLocalState();
    onClose?.();
  }

  useEffect(() => {
    if (open) return;

    requestIdRef.current += 1;
    submissionRequestIdRef.current += 1;
    submissionControllerRef.current?.abort();
    submissionControllerRef.current = null;
    submittingRef.current = false;
    setComparison(null);
    setLoading(false);
    setError(null);
    setSelectedUnitKeys(new Set());
    setVisibleLimits(createVisibleLimits());
    setIsCommonExpanded(false);
    setStep("preview");
    setAcknowledged(false);
    setCredentialInput("");
    setPendingMerge(null);
    setResumeAvailable(false);
    setSubmitting(false);
    setSubmissionError(null);
    setSuccess(null);
    setPreviewNotice(null);
  }, [open]);

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

    setComparison(null);
    setError(null);
    setSelectedUnitKeys(new Set());
    setVisibleLimits(createVisibleLimits());
    setIsCommonExpanded(false);
    setStep("preview");
    setAcknowledged(false);
    setCredentialInput("");
    setPendingMerge(null);
    setResumeAvailable(false);
    setSubmissionError(null);
    setSuccess(null);

    if (numericBranchChatId === null) {
      setLoading(false);
      setError(
        "A valid branch chat is required for merge preview."
      );
      return undefined;
    }

    const controller = new AbortController();
    const requestId =
      requestIdRef.current + 1;

    requestIdRef.current = requestId;
    setLoading(true);

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

        setSelectedUnitKeys(new Set());
        setVisibleLimits(
          createVisibleLimits()
        );
        setIsCommonExpanded(false);
        const loadedComparison =
          response?.data || null;
        const serializedPending =
          readPendingStorage();
        const restoredPending =
          parsePendingBranchMerge(
            serializedPending,
            numericBranchChatId,
            loadedComparison
          );

        const pendingWasDiscarded =
          serializedPending &&
          !restoredPending;

        if (pendingWasDiscarded) {
          removePendingStorage();
        }

        setPendingMerge(restoredPending);
        setResumeAvailable(
          Boolean(restoredPending)
        );
        setPreviewNotice(
          reloadNoticeRef.current ||
            (pendingWasDiscarded
              ? "A saved pending request no longer matched this branch preview and was discarded. Fresh selection and confirmation are required."
              : null)
        );
        reloadNoticeRef.current = null;
        setComparison(loadedComparison);
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
            "Unable to load the branch merge preview."
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

  const selectionEvaluation = useMemo(
    () =>
      evaluateCanonicalMergeSelection(
        comparison,
        selectedUnitKeys
      ),
    [comparison, selectedUnitKeys]
  );

  const turnUnits = useMemo(() => {
    if (!comparison?.comparable) return [];

    return comparison.merge_preview
      ? selectionEvaluation.units
      : buildConversationUnits(comparison);
  }, [comparison, selectionEvaluation.units]);

  const selectableUnits = useMemo(
    () =>
      turnUnits.filter(
        (unit) => unit.selectable
      ),
    [turnUnits]
  );

  const selectedUnits =
    selectionEvaluation.selectedUnits;
  const selectedMessages =
    selectionEvaluation.selectedMessages;

  useEffect(() => {
    setVisibleLimits((current) => ({
      ...current,
      selected: PAGE_SIZE,
    }));
  }, [selectedUnitKeys]);

  const issues = useMemo(() => {
    const blocking = [
      ...selectionEvaluation.blocking,
    ];
    const warning = [
      ...selectionEvaluation.warning,
    ];
    const information = [
      {
        id: "append-only",
        message:
          "Execution is append-only and still requires a separate acknowledged confirmation.",
      },
    ];

    let previousValidTimestamp = null;
    let hasTimestampInversion = false;

    for (const message of selectedMessages) {
      const timestamp = Date.parse(
        message?.created_at
      );

      if (Number.isNaN(timestamp)) {
        continue;
      }

      if (
        previousValidTimestamp !== null &&
        timestamp < previousValidTimestamp
      ) {
        hasTimestampInversion = true;
        break;
      }

      previousValidTimestamp = timestamp;
    }

    if (hasTimestampInversion) {
      warning.push({
        id: "timestamp-order",
        message:
          "Selected timestamps decrease while messages remain in authoritative message-ID order. No timestamp reordering was applied.",
      });
    }

    const attachmentCount =
      selectedMessages.filter(
        (message) =>
          message
            ?.has_attachment_metadata ===
          true
      ).length;

    if (attachmentCount > 0) {
      warning.push({
        id: "attachment-metadata",
        message:
          attachmentCount +
          " selected message(s) contain attachment metadata, but no physical attachment file would be included.",
      });
    }

    const sourceCount =
      selectedMessages.filter(
        (message) =>
          message?.has_source_metadata ===
          true
      ).length;

    if (sourceCount > 0) {
      warning.push({
        id: "source-metadata",
        message:
          sourceCount +
          " selected message(s) contain source or citation metadata, but no document or RAG data would be included.",
      });
    }

    if (
      selectedUnits.some(
        (unit) => unit.type === "source"
      )
    ) {
      information.push({
        id: "source-anchor",
        message:
          "The source-anchored continuation uses the existing exact parent source prompt and does not add that prompt again.",
      });
    }

    const unansweredTurnCount =
      selectedUnits.filter(
        (unit) =>
          unit.type === "turn" &&
          !unit.messages.some(
            (message) =>
              message.role === "assistant"
          )
      ).length;

    if (unansweredTurnCount > 0) {
      information.push({
        id: "unanswered-turns",
        message:
          unansweredTurnCount +
          " selected user turn(s) have no following assistant response.",
      });
    }

    return {
      blocking,
      warning,
      information,
    };
  }, [
    selectionEvaluation,
    selectedMessages,
    selectedUnits,
  ]);

  if (!open) return null;

  const canEnterConfirmation =
    selectionEvaluation.canEnterConfirmation &&
    issues.blocking.length === 0 &&
    !submitting &&
    !resumeAvailable;

  function focusSoon(ref) {
    window.requestAnimationFrame(() => {
      ref.current?.focus();
    });
  }

  function enterConfirmation() {
    if (!canEnterConfirmation) return;

    setAcknowledged(false);
    setSubmissionError(null);
    setStep("confirm");
    focusSoon(confirmationHeadingRef);
  }

  function returnToPreview() {
    if (submitting) return;

    setAcknowledged(false);
    setCredentialInput("");
    setSubmissionError(null);
    setResumeAvailable(
      Boolean(pendingMerge)
    );
    setStep("preview");
  }

  function resumePendingRequest() {
    if (!pendingMerge || submitting) return;

    setSelectedUnitKeys(
      selectedKeysFromPending(pendingMerge)
    );
    setResumeAvailable(false);
    setAcknowledged(false);
    setSubmissionError(null);
    setStep("confirm");
    focusSoon(confirmationHeadingRef);
  }

  function discardPendingRequest() {
    if (submitting) return;

    removePendingStorage();
    setPreviewNotice(
      "The previous pending request was discarded. Make a fresh selection and confirmation."
    );
  }

  function safeDismiss() {
    if (step === "confirm" && !submitting) {
      returnToPreview();
      return;
    }

    requestClose();
  }

  async function submitMergeRequest() {
    if (
      submitting ||
      submittingRef.current ||
      !acknowledged ||
      !comparison?.merge_preview
    ) {
      return;
    }

    const credentialToUse = hasMergeCredential
      ? mergeCredential
      : credentialInput;

    if (!credentialToUse) {
      setSubmissionError({
        code: "MERGE_AUTH_REQUIRED",
        message:
          "Enter the runtime merge authorization credential.",
        retrySame: Boolean(pendingMerge),
      });
      focusSoon(credentialErrorRef);
      return;
    }

    let pendingToSubmit = pendingMerge;

    if (!pendingToSubmit) {
      try {
        const immutableRequest =
          buildBranchMergeRequest({
            comparison,
            selectedTurnKeys: selectedUnitKeys,
          });

        pendingToSubmit =
          createPendingBranchMerge({
            branchChatId,
            request: immutableRequest,
            selectedTurnCount:
              selectedUnits.length,
            selectedMessageCount:
              selectedMessages.length,
          });
      } catch (requestError) {
        setSubmissionError({
          code: "INVALID_MERGE_REQUEST",
          message:
            requestError?.message ||
            "A safe merge request could not be built.",
          retrySame: false,
        });
        return;
      }

      if (!savePendingStorage(pendingToSubmit)) {
        setSubmissionError({
          code: "PENDING_STORAGE_UNAVAILABLE",
          message:
            "The exact pending request could not be saved for safe retry. No merge request was sent.",
          retrySame: false,
        });
        return;
      }

      setPendingMerge(pendingToSubmit);
    }

    if (!hasMergeCredential) {
      onRememberMergeCredential?.(
        credentialToUse
      );
      setCredentialInput("");
    }

    const controller = new AbortController();
    const submissionRequestId =
      submissionRequestIdRef.current + 1;

    submissionRequestIdRef.current =
      submissionRequestId;
    submissionControllerRef.current =
      controller;
    submittingRef.current = true;
    setSubmitting(true);
    setSubmissionError(null);

    try {
      const result = await mergeBranchIntoParent(
        branchChatId,
        pendingToSubmit.request,
        credentialToUse,
        {
          signal: controller.signal,
        }
      );

      if (
        controller.signal.aborted ||
        submissionRequestIdRef.current !==
          submissionRequestId
      ) {
        return;
      }

      if (!isCompletedBranchMergeResponse(result)) {
        throw new Error(
          "The merge result is uncertain because the completion response was invalid."
        );
      }

      removePendingStorage();
      setSuccess(result);
      setAcknowledged(false);
      setStep("success");
      onMergeCompleted?.(branchChatId);
      focusSoon(successHeadingRef);
    } catch (requestError) {
      if (
        controller.signal.aborted ||
        submissionRequestIdRef.current !==
          submissionRequestId
      ) {
        return;
      }

      const status = requestError?.status;
      const code = requestError?.code;
      const operationId =
        requestError?.operation_id || null;
      const retryAfter =
        requestError?.retry_after || null;
      const safeMessage =
        requestError?.message ||
        "The merge result is uncertain. Retry the same request.";
      const failurePolicy =
        getBranchMergeFailurePolicy(
          requestError
        );

      if (status === 401) {
        onForgetMergeCredential?.();
        setCredentialInput("");
        setSubmissionError({
          code,
          message:
            "The merge credential was rejected and cleared from memory. Enter it again to retry the same request.",
          retrySame: true,
        });
        focusSoon(credentialErrorRef);
      } else if (
        status === 409 &&
        code === "STALE_PREVIEW"
      ) {
        removePendingStorage();
        setSelectedUnitKeys(new Set());
        reloadNoticeRef.current =
          "STALE_PREVIEW: The preview became stale. Select again from the freshly loaded canonical preview.";
        retryRequest();
      } else if (
        status === 409 &&
        code === "IDEMPOTENCY_KEY_REUSED"
      ) {
        removePendingStorage();
        setSelectedUnitKeys(new Set());
        reloadNoticeRef.current =
          "IDEMPOTENCY_KEY_REUSED: The key belongs to another request. A fresh preview and confirmation are required.";
        retryRequest();
      } else if (
        status === 409 &&
        code === "MERGE_ALREADY_COMPLETED"
      ) {
        removePendingStorage();
        setSelectedUnitKeys(new Set());
        reloadNoticeRef.current =
          "MERGE_ALREADY_COMPLETED: The selected messages were already merged" +
          (operationId
            ? ` by operation ${operationId}.`
            : ".") +
          " No automatic resubmission occurred.";
        onMergeCompleted?.(branchChatId);
        retryRequest();
      } else if (
        failurePolicy.keepPending
      ) {
        setSubmissionError({
          code,
          message:
            status === 429 && retryAfter
              ? `${safeMessage} Retry-After: ${retryAfter} seconds.`
              : safeMessage,
          retrySame: true,
          operationId,
        });
      } else {
        removePendingStorage();
        setSelectedUnitKeys(new Set());
        setAcknowledged(false);
        setStep("preview");
        setPreviewNotice(
          `${code ? `${code}: ` : ""}${safeMessage} The invalid pending request was cleared; review the current preview before trying again.`
        );
      }
    } finally {
      if (
        submissionRequestIdRef.current ===
        submissionRequestId
      ) {
        setSubmitting(false);
        submittingRef.current = false;
        submissionControllerRef.current = null;
      }
    }
  }

  function openMergedParent() {
    if (!success) return;

    const parentChatId = toPositiveId(
      success.parent_chat_id
    );
    const targetMessageId =
      getMergedMessageNavigationTarget(
        success
      );

    if (parentChatId === null) return;

    requestClose();
    onSelectChat?.(
      parentChatId,
      targetMessageId,
      {
        missingTargetBehavior: "silent",
      }
    );
  }

  function handleDialogKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      safeDismiss();
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

  function toggleUnit(unitKey) {
    if (submitting || step !== "preview") {
      return;
    }

    setSelectedUnitKeys((current) => {
      const next = new Set(current);

      if (next.has(unitKey)) {
        next.delete(unitKey);
      } else {
        next.add(unitKey);
      }

      return next;
    });
  }

  function selectAllUnits() {
    if (submitting || step !== "preview") {
      return;
    }

    setSelectedUnitKeys(
      new Set(
        selectableUnits.map(
          (unit) => unit.key
        )
      )
    );
  }

  function clearSelection() {
    if (submitting || step !== "preview") {
      return;
    }

    setSelectedUnitKeys(new Set());
  }

  function showMore(sectionName) {
    setVisibleLimits((current) => ({
      ...current,
      [sectionName]:
        current[sectionName] + PAGE_SIZE,
    }));
  }

  function showAll(sectionName, totalCount) {
    setVisibleLimits((current) => ({
      ...current,
      [sectionName]: totalCount,
    }));
  }

  function retryRequest() {
    requestIdRef.current += 1;
    setComparison(null);
    setError(null);
    setLoading(true);
    setSelectedUnitKeys(new Set());
    setVisibleLimits(createVisibleLimits());
    setIsCommonExpanded(false);
    setStep("preview");
    setAcknowledged(false);
    setCredentialInput("");
    setPendingMerge(null);
    setResumeAvailable(false);
    setSubmitting(false);
    submittingRef.current = false;
    setSubmissionError(null);
    setSuccess(null);
    setPreviewNotice(null);
    setRetryKey(
      (current) => current + 1
    );
  }

  const isLoadingState =
    loading || (!comparison && !error);
  const parentTitle =
    comparison?.parent_chat?.title ||
    "Parent unavailable";
  const branchTitle =
    comparison?.branch_chat?.title ||
    "Branch chat";
  const unavailableMessage =
    unavailableMessages[comparison?.reason] ||
    "This branch cannot be previewed exactly because its branch metadata is incomplete.";
  const commonMessages =
    comparison?.common_messages || [];
  const parentOnlyMessages =
    comparison?.parent_only_messages || [];
  const visibleTurnUnits = turnUnits.slice(
    0,
    visibleLimits.turns
  );
  const visibleSelectedMessages =
    selectedMessages.slice(
      0,
      visibleLimits.selected
    );

  return (
    <div
      className="fixed inset-0 z-[75] flex items-center justify-center bg-black/70 p-2 backdrop-blur-sm sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          safeDismiss();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="branch-merge-preview-title"
        aria-describedby="branch-merge-preview-description"
        aria-busy={
          isLoadingState || submitting
        }
        tabIndex={-1}
        onKeyDown={handleDialogKeyDown}
        onMouseDown={(event) =>
          event.stopPropagation()
        }
        className={
          "flex max-h-[94vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl border shadow-2xl " +
          (
            isDark
              ? "border-slate-700 bg-slate-950 text-white"
              : "border-slate-200 bg-white text-slate-900"
          )
        }
      >
        <header
          className={
            "flex shrink-0 items-start justify-between gap-4 border-b px-4 py-3 sm:px-5 " +
            (
              isDark
                ? "border-slate-800"
                : "border-slate-200"
            )
          }
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2
                id="branch-merge-preview-title"
                ref={
                  step === "confirm"
                    ? confirmationHeadingRef
                    : step === "success"
                      ? successHeadingRef
                      : null
                }
                className="text-lg font-bold"
                tabIndex={-1}
              >
                {step === "confirm"
                  ? "Confirm Branch Merge"
                  : step === "success"
                    ? "Branch Merge Completed"
                    : "Branch Merge Preview"}
              </h2>
              <span
                className={
                  "rounded-full px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide " +
                  (
                    isDark
                      ? "bg-amber-500/15 text-amber-300"
                      : "bg-amber-100 text-amber-800"
                  )
                }
              >
                {step === "preview"
                  ? "Review"
                  : step === "confirm"
                    ? "Final confirmation"
                    : "Completed"}
              </span>
            </div>

            <p
              id="branch-merge-preview-description"
              className={
                "mt-1 text-xs " +
                (
                  isDark
                    ? "text-slate-400"
                    : "text-slate-600"
                )
              }
            >
              Parent: {parentTitle} / Branch:{" "}
              {branchTitle}
            </p>
          </div>

          <button
            ref={closeButtonRef}
            type="button"
            onClick={requestClose}
            className={
              "shrink-0 rounded-lg px-3 py-1.5 text-sm font-semibold transition " +
              (
                isDark
                  ? "hover:bg-slate-800"
                  : "hover:bg-slate-100"
              )
            }
            aria-label="Close Branch Merge Preview"
          >
            Close
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-3 sm:p-5">
          {isLoadingState && (
            <div
              className={
                "rounded-xl border px-4 py-8 text-center " +
                (
                  isDark
                    ? "border-slate-700 bg-slate-900 text-slate-300"
                    : "border-slate-200 bg-slate-50 text-slate-700"
                )
              }
            >
              Loading merge preview…
            </div>
          )}

          {!isLoadingState && error && (
            <div
              role="alert"
              className={
                "rounded-xl border p-4 " +
                (
                  isDark
                    ? "border-red-500/40 bg-red-500/10 text-red-200"
                    : "border-red-200 bg-red-50 text-red-800"
                )
              }
            >
              <h3 className="font-semibold">
                Merge preview could not be loaded
              </h3>
              <p className="mt-1 break-words text-sm">
                {error}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={retryRequest}
                  className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-blue-700"
                >
                  Retry
                </button>
                <button
                  type="button"
                  onClick={requestClose}
                  className={
                    "rounded-lg px-3 py-1.5 text-sm font-semibold transition " +
                    (
                      isDark
                        ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                        : "bg-white text-slate-700 hover:bg-slate-100"
                    )
                  }
                >
                  Close
                </button>
              </div>
            </div>
          )}

          {!isLoadingState &&
            !error &&
            comparison &&
            !comparison.comparable && (
              <div
                className={
                  "rounded-xl border p-4 " +
                  (
                    isDark
                      ? "border-amber-500/40 bg-amber-500/10"
                      : "border-amber-200 bg-amber-50"
                  )
                }
              >
                <h3 className="font-semibold">
                  Exact merge preview unavailable
                </h3>
                <p
                  className={
                    "mt-2 text-sm " +
                    (
                      isDark
                        ? "text-slate-300"
                        : "text-slate-700"
                    )
                  }
                >
                  {unavailableMessage}
                </p>
                <p
                  className={
                    "mt-2 text-xs " +
                    (
                      isDark
                        ? "text-slate-400"
                        : "text-slate-600"
                    )
                  }
                >
                  Parent: {parentTitle} / Branch:{" "}
                  {branchTitle}. No boundaries,
                  counts, or selectable units were
                  guessed.
                </p>
                <button
                  type="button"
                  onClick={requestClose}
                  className="mt-4 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-blue-700"
                >
                  Close
                </button>
              </div>
            )}

          {!isLoadingState &&
            !error &&
            comparison?.comparable &&
            step === "preview" && (
              <div className="space-y-4">
                {previewNotice && (
                  <section
                    role="status"
                    aria-live="polite"
                    className={
                      "rounded-xl border p-3 text-sm " +
                      (
                        isDark
                          ? "border-blue-500/40 bg-blue-500/10 text-blue-100"
                          : "border-blue-200 bg-blue-50 text-blue-900"
                      )
                    }
                  >
                    {previewNotice}
                  </section>
                )}

                {resumeAvailable &&
                  pendingMerge && (
                    <section
                      className={
                        "rounded-xl border p-4 " +
                        (
                          isDark
                            ? "border-amber-500/40 bg-amber-500/10"
                            : "border-amber-200 bg-amber-50"
                        )
                      }
                    >
                      <h3 className="font-semibold">
                        Pending merge request found
                      </h3>
                      <p className="mt-1 text-sm">
                        Its preview boundaries still
                        match this branch. Resume it
                        with the exact same request and
                        idempotency key, or discard it
                        before making a new request.
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={resumePendingRequest}
                          disabled={submitting}
                          className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Resume pending merge
                        </button>
                        <button
                          type="button"
                          onClick={discardPendingRequest}
                          disabled={submitting}
                          className={
                            "rounded-lg px-3 py-1.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 " +
                            (
                              isDark
                                ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                                : "bg-white text-slate-700 hover:bg-slate-100"
                            )
                          }
                        >
                          Discard pending request
                        </button>
                      </div>
                    </section>
                  )}

                {hasMergeCredential && (
                  <section
                    className={
                      "flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3 text-sm " +
                      (
                        isDark
                          ? "border-slate-700 bg-slate-900"
                          : "border-slate-200 bg-slate-50"
                      )
                    }
                  >
                    <p>
                      A merge credential is currently
                      held in page memory. Its value is
                      not displayed.
                    </p>
                    <button
                      type="button"
                      onClick={
                        onForgetMergeCredential
                      }
                      disabled={submitting}
                      className={
                        "rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 " +
                        (
                          isDark
                            ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                            : "bg-white text-slate-700 hover:bg-slate-100"
                        )
                      }
                    >
                      Forget merge credential
                    </button>
                  </section>
                )}

                {!comparison.merge_preview && (
                  <section
                    role="alert"
                    className={
                      "rounded-xl border p-4 " +
                      (
                        isDark
                          ? "border-amber-500/40 bg-amber-500/10 text-amber-100"
                          : "border-amber-200 bg-amber-50 text-amber-900"
                      )
                    }
                  >
                    <h3 className="font-semibold">
                      Fresh merge-capable preview unavailable
                    </h3>
                    <p className="mt-1 text-sm">
                      Read-only comparison data remains
                      available, but execution is
                      disabled because canonical server
                      turns are missing.
                    </p>
                  </section>
                )}

                <section
                  className={
                    "rounded-xl border p-4 " +
                    (
                      isDark
                        ? "border-emerald-500/40 bg-emerald-500/10"
                        : "border-emerald-200 bg-emerald-50"
                    )
                  }
                >
                  <h3 className="font-semibold">
                    Selected messages would be added
                    to: {parentTitle}
                  </h3>
                  <p
                    className={
                      "mt-1 text-sm " +
                      (
                        isDark
                          ? "text-slate-300"
                          : "text-slate-700"
                      )
                    }
                  >
                    Review the server-provided
                    canonical turns below. Nothing is
                    written until a separate final
                    confirmation is acknowledged.
                  </p>
                </section>

                <section
                  className={
                    "rounded-xl border p-3 " +
                    (
                      isDark
                        ? "border-violet-500/40 bg-violet-500/10"
                        : "border-violet-200 bg-violet-50"
                    )
                  }
                >
                  <div className="mb-3">
                    <h3 className="font-semibold">
                      Exact divergence point
                    </h3>
                    <p
                      className={
                        "mt-1 text-xs " +
                        (
                          isDark
                            ? "text-slate-400"
                            : "text-slate-600"
                        )
                      }
                    >
                      The original parent source and
                      its exact copied branch
                      equivalent.
                    </p>
                  </div>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    <div className="min-w-0">
                      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-blue-500">
                        Parent source message
                      </h4>
                      <MessageCard
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
                      <MessageCard
                        message={
                          comparison.branch_source_message
                        }
                        isDark={isDark}
                        accent="emerald"
                      />
                    </div>
                  </div>
                </section>

                <section
                  className={
                    "rounded-xl border p-3 " +
                    (
                      isDark
                        ? "border-slate-700 bg-slate-900/70"
                        : "border-slate-200 bg-slate-50"
                    )
                  }
                >
                  <button
                    type="button"
                    onClick={() =>
                      setIsCommonExpanded(
                        (current) => !current
                      )
                    }
                    aria-expanded={
                      isCommonExpanded
                    }
                    aria-controls="merge-preview-common-history"
                    className="flex w-full items-center justify-between gap-3 text-left"
                  >
                    <span>
                      <span className="block text-sm font-semibold">
                        Common copied history
                      </span>
                      <span
                        className={
                          "mt-1 block text-xs " +
                          (
                            isDark
                              ? "text-slate-400"
                              : "text-slate-600"
                          )
                        }
                      >
                        Collapsed by default because
                        these messages are not
                        selectable.
                      </span>
                    </span>
                    <span
                      className={
                        "shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold " +
                        (
                          isDark
                            ? "bg-slate-800 text-slate-300"
                            : "bg-white text-slate-700"
                        )
                      }
                    >
                      {comparison.counts?.common ??
                        commonMessages.length}
                      {" · "}
                      {isCommonExpanded
                        ? "Collapse"
                        : "Expand"}
                    </span>
                  </button>

                  {isCommonExpanded && (
                    <div
                      id="merge-preview-common-history"
                      className="mt-3"
                    >
                      {commonMessages.length > 0 ? (
                        <div className="space-y-2">
                          {commonMessages
                            .slice(
                              0,
                              visibleLimits.common
                            )
                            .map((message) => (
                              <MessageCard
                                key={message.id}
                                message={message}
                                isDark={isDark}
                              />
                            ))}
                        </div>
                      ) : (
                        <p
                          className={
                            isDark
                              ? "text-sm text-slate-400"
                              : "text-sm text-slate-600"
                          }
                        >
                          No common copied messages
                          are available.
                        </p>
                      )}
                      <IncrementalControls
                        visibleCount={Math.min(
                          visibleLimits.common,
                          commonMessages.length
                        )}
                        totalCount={
                          commonMessages.length
                        }
                        onShowMore={() =>
                          showMore("common")
                        }
                        onShowAll={() =>
                          showAll(
                            "common",
                            commonMessages.length
                          )
                        }
                        isDark={isDark}
                        itemLabel="messages"
                      />
                    </div>
                  )}
                </section>

                <MessageSection
                  title="Parent-only context"
                  description="Read-only messages in the immediate parent after the exact branch point."
                  messages={parentOnlyMessages}
                  totalCount={
                    comparison.counts
                      ?.parent_only ??
                    parentOnlyMessages.length
                  }
                  visibleCount={
                    visibleLimits.parentOnly
                  }
                  onShowMore={() =>
                    showMore("parentOnly")
                  }
                  onShowAll={() =>
                    showAll(
                      "parentOnly",
                      parentOnlyMessages.length
                    )
                  }
                  emptyMessage="Parent has no messages after the branch point."
                  isDark={isDark}
                />

                <fieldset
                  className={
                    "rounded-xl border p-3 " +
                    (
                      isDark
                        ? "border-slate-700 bg-slate-900/70"
                        : "border-slate-200 bg-slate-50"
                    )
                  }
                >
                  <legend className="px-1 text-sm font-semibold">
                    Branch-only conversation turns
                  </legend>

                  <div
                    className="mb-3 flex flex-wrap items-center justify-between gap-3"
                    aria-live="polite"
                  >
                    <div>
                      <p
                        className={
                          "text-xs " +
                          (
                            isDark
                              ? "text-slate-400"
                              : "text-slate-600"
                          )
                        }
                      >
                        Selection is atomic by
                        conversation turn. Individual
                        messages cannot be selected
                        independently.
                      </p>
                      <p className="mt-1 text-sm font-semibold">
                        {selectedUnits.length} selected{" "}
                        {selectedUnits.length === 1
                          ? "turn"
                          : "turns"}
                        {" · "}
                        {selectedMessages.length} selected{" "}
                        {selectedMessages.length === 1
                          ? "message"
                          : "messages"}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={selectAllUnits}
                        disabled={
                          submitting ||
                          selectableUnits.length === 0
                        }
                        className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Select All
                      </button>
                      <button
                        type="button"
                        onClick={clearSelection}
                        disabled={
                          submitting ||
                          selectedUnitKeys.size === 0
                        }
                        className={
                          "rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 " +
                          (
                            isDark
                              ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                              : "bg-white text-slate-700 hover:bg-slate-100"
                          )
                        }
                      >
                        Clear Selection
                      </button>
                    </div>
                  </div>

                  {turnUnits.length === 0 ? (
                    <p
                      className={
                        "rounded-lg border border-dashed px-3 py-4 text-center text-sm " +
                        (
                          isDark
                            ? "border-slate-700 text-slate-400"
                            : "border-slate-300 text-slate-600"
                        )
                      }
                    >
                      Branch has no messages available
                      for merge preview.
                    </p>
                  ) : (
                    <>
                      {selectableUnits.length === 0 && (
                        <p
                          className={
                            "mb-3 rounded-lg border px-3 py-2 text-sm " +
                            (
                              isDark
                                ? "border-amber-500/30 text-amber-200"
                                : "border-amber-200 text-amber-900"
                            )
                          }
                        >
                          No eligible turns are
                          available because only unsafe
                          orphan or malformed messages
                          are present.
                        </p>
                      )}
                      <div className="space-y-3">
                        {visibleTurnUnits.map(
                          (unit) => (
                            <TurnUnitCard
                              key={unit.key}
                              unit={unit}
                              selected={selectedUnitKeys.has(
                                unit.key
                              )}
                              onToggle={toggleUnit}
                              isDark={isDark}
                              disabled={submitting}
                            />
                          )
                        )}
                      </div>
                      <IncrementalControls
                        visibleCount={
                          visibleTurnUnits.length
                        }
                        totalCount={
                          turnUnits.length
                        }
                        onShowMore={() =>
                          showMore("turns")
                        }
                        onShowAll={() =>
                          showAll(
                            "turns",
                            turnUnits.length
                          )
                        }
                        isDark={isDark}
                        itemLabel="units"
                      />
                    </>
                  )}
                </fieldset>

                <section
                  aria-label="Merge preview issue summary"
                  aria-live="polite"
                >
                  <div className="mb-2">
                    <h3 className="font-semibold">
                      Preview issues and notes
                    </h3>
                    <p
                      className={
                        "mt-1 text-xs " +
                        (
                          isDark
                            ? "text-slate-400"
                            : "text-slate-600"
                        )
                      }
                    >
                      Detected issues are not resolved
                      and selected items are never
                      removed automatically.
                    </p>
                  </div>
                  <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                    <IssueGroup
                      title="Blocking"
                      issues={issues.blocking}
                      severity="blocking"
                      isDark={isDark}
                    />
                    <IssueGroup
                      title="Warnings"
                      issues={issues.warning}
                      severity="warning"
                      isDark={isDark}
                    />
                    <IssueGroup
                      title="Information"
                      issues={
                        issues.information
                      }
                      severity="information"
                      isDark={isDark}
                    />
                  </div>
                </section>

                <section
                  className={
                    "rounded-xl border p-3 " +
                    (
                      isDark
                        ? "border-slate-700 bg-slate-900/70"
                        : "border-slate-200 bg-slate-50"
                    )
                  }
                >
                  <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold">
                        Ordered selected preview
                      </h3>
                      <p
                        className={
                          "mt-1 text-xs " +
                          (
                            isDark
                              ? "text-slate-400"
                              : "text-slate-600"
                          )
                        }
                      >
                        Read-only payload ordered by
                        ascending original branch
                        message ID.
                      </p>
                    </div>
                    <span
                      className={
                        "rounded-full px-2 py-0.5 text-xs font-semibold " +
                        (
                          isDark
                            ? "bg-slate-800 text-slate-300"
                            : "bg-white text-slate-700"
                        )
                      }
                    >
                      {selectedMessages.length}{" "}
                      messages
                    </span>
                  </div>

                  {visibleSelectedMessages.length >
                  0 ? (
                    <div className="space-y-2">
                      {visibleSelectedMessages.map(
                        (message) => (
                          <MessageCard
                            key={message.id}
                            message={message}
                            isDark={isDark}
                          />
                        )
                      )}
                    </div>
                  ) : (
                    <p
                      className={
                        "rounded-lg border border-dashed px-3 py-4 text-center text-sm " +
                        (
                          isDark
                            ? "border-slate-700 text-slate-400"
                            : "border-slate-300 text-slate-600"
                        )
                      }
                    >
                      Select an eligible conversation
                      turn to preview its ordered
                      branch messages.
                    </p>
                  )}

                  <IncrementalControls
                    visibleCount={
                      visibleSelectedMessages.length
                    }
                    totalCount={
                      selectedMessages.length
                    }
                    onShowMore={() =>
                      showMore("selected")
                    }
                    onShowAll={() =>
                      showAll(
                        "selected",
                        selectedMessages.length
                      )
                    }
                    isDark={isDark}
                    itemLabel="messages"
                  />
                </section>
              </div>
            )}

          {!isLoadingState &&
            !error &&
            comparison?.comparable &&
            step === "confirm" && (
              <section
                aria-labelledby="branch-merge-confirmation-heading"
                aria-busy={submitting}
                className="mx-auto max-w-3xl space-y-4"
              >
                <div
                  className={
                    "rounded-xl border p-4 " +
                    (
                      isDark
                        ? "border-red-500/40 bg-red-500/10"
                        : "border-red-200 bg-red-50"
                    )
                  }
                >
                  <h3
                    id="branch-merge-confirmation-heading"
                    className="text-lg font-bold"
                  >
                    Final append confirmation
                  </h3>
                  <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide opacity-70">
                        Immediate destination
                      </dt>
                      <dd className="mt-1 break-words font-semibold">
                        {parentTitle}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide opacity-70">
                        Source branch
                      </dt>
                      <dd className="mt-1 break-words font-semibold">
                        {branchTitle}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide opacity-70">
                        Selected turns
                      </dt>
                      <dd className="mt-1 font-semibold">
                        {selectedUnits.length}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-semibold uppercase tracking-wide opacity-70">
                        Selected messages
                      </dt>
                      <dd className="mt-1 font-semibold">
                        {selectedMessages.length}
                      </dd>
                    </div>
                  </dl>

                  <ul className="mt-4 list-disc space-y-1 pl-5 text-sm">
                    <li>
                      Selected turns are appended to
                      the immediate parent only.
                    </li>
                    <li>
                      The source branch remains
                      unchanged and present.
                    </li>
                    <li>
                      Existing parent history remains
                      unchanged.
                    </li>
                    <li>
                      There is no Undo in v2.23.
                    </li>
                  </ul>
                </div>

                <div
                  className={
                    "rounded-xl border p-4 " +
                    (
                      isDark
                        ? "border-slate-700 bg-slate-900"
                        : "border-slate-200 bg-slate-50"
                    )
                  }
                >
                  <h3 className="font-semibold">
                    Excluded from the append
                  </h3>
                  <p className="mt-1 text-sm">
                    Attachments, physical files,
                    source/citation metadata, PDFs,
                    documents, bookmarks, RAG/Chroma
                    data, branch metadata, and model
                    metadata are not copied.
                  </p>
                </div>

                <div
                  className={
                    "rounded-xl border p-4 " +
                    (
                      isDark
                        ? "border-slate-700 bg-slate-900"
                        : "border-slate-200 bg-white"
                    )
                  }
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold">
                        Runtime merge credential
                      </h3>
                      <p className="mt-1 text-xs opacity-70">
                        Kept in browser memory only and
                        sent only with this merge POST.
                      </p>
                    </div>
                    {hasMergeCredential && (
                      <button
                        type="button"
                        onClick={() => {
                          onForgetMergeCredential?.();
                          setCredentialInput("");
                        }}
                        disabled={submitting}
                        className={
                          "rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 " +
                          (
                            isDark
                              ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                              : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                          )
                        }
                      >
                        Forget merge credential
                      </button>
                    )}
                  </div>

                  {hasMergeCredential ? (
                    <p
                      className="mt-3 text-sm text-emerald-500"
                      role="status"
                    >
                      A merge credential is available
                      in memory. Its value is not
                      displayed.
                    </p>
                  ) : (
                    <div className="mt-3">
                      <label
                        htmlFor="branch-merge-credential"
                        className="text-sm font-semibold"
                      >
                        Merge authorization credential
                      </label>
                      <input
                        id="branch-merge-credential"
                        type="password"
                        value={credentialInput}
                        onChange={(event) =>
                          setCredentialInput(
                            event.target.value
                          )
                        }
                        disabled={submitting}
                        autoComplete="off"
                        spellCheck="false"
                        className={
                          "mt-2 w-full rounded-lg border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60 " +
                          (
                            isDark
                              ? "border-slate-700 bg-slate-950 text-white"
                              : "border-slate-300 bg-white text-slate-900"
                          )
                        }
                      />
                    </div>
                  )}
                </div>

                {submissionError && (
                  <div
                    ref={credentialErrorRef}
                    role="alert"
                    aria-live="assertive"
                    tabIndex={-1}
                    className={
                      "rounded-xl border p-4 " +
                      (
                        isDark
                          ? "border-red-500/40 bg-red-500/10 text-red-100"
                          : "border-red-200 bg-red-50 text-red-900"
                      )
                    }
                  >
                    <h3 className="font-semibold">
                      Merge request needs attention
                    </h3>
                    <p className="mt-1 break-words text-sm">
                      {submissionError.message}
                    </p>
                    {submissionError.code && (
                      <p className="mt-2 text-xs font-semibold">
                        Code: {submissionError.code}
                      </p>
                    )}
                    {submissionError.operationId && (
                      <p className="mt-1 text-xs">
                        Operation: {submissionError.operationId}
                      </p>
                    )}
                    {submissionError.retrySame && (
                      <p className="mt-2 text-xs font-semibold">
                        Retry same request. The exact
                        body and idempotency key will be
                        reused.
                      </p>
                    )}
                  </div>
                )}

                <label
                  className={
                    "flex items-start gap-3 rounded-xl border p-4 text-sm " +
                    (
                      isDark
                        ? "border-slate-700 bg-slate-900"
                        : "border-slate-200 bg-white"
                    )
                  }
                >
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(event) =>
                      setAcknowledged(
                        event.target.checked
                      )
                    }
                    disabled={submitting}
                    className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-400 text-red-600 focus:ring-red-500"
                  />
                  <span>
                    I understand this is an append-only
                    operation with no Undo in v2.23,
                    and that the excluded metadata and
                    files will not be copied.
                  </span>
                </label>
              </section>
            )}

          {!isLoadingState &&
            !error &&
            step === "success" &&
            success && (
              <section
                aria-live="polite"
                className="mx-auto max-w-3xl space-y-4"
              >
                <div
                  className={
                    "rounded-xl border p-5 " +
                    (
                      isDark
                        ? "border-emerald-500/40 bg-emerald-500/10"
                        : "border-emerald-200 bg-emerald-50"
                    )
                  }
                >
                  <h3 className="text-lg font-bold">
                    Completed
                  </h3>
                  <p className="mt-1 text-sm">
                    {success.replayed
                      ? "The backend safely replayed the existing completed operation."
                      : "The selected canonical turns were appended successfully."}
                  </p>
                  <dl className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-xs uppercase opacity-70">
                        Operation ID
                      </dt>
                      <dd className="font-semibold">
                        {success.operation_id}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase opacity-70">
                        Replayed operation
                      </dt>
                      <dd className="font-semibold">
                        {success.replayed ? "Yes" : "No"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase opacity-70">
                        Destination parent
                      </dt>
                      <dd className="font-semibold">
                        {parentTitle}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase opacity-70">
                        Inserted turns
                      </dt>
                      <dd className="font-semibold">
                        {success.inserted_turn_count}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase opacity-70">
                        Inserted messages
                      </dt>
                      <dd className="font-semibold">
                        {success.inserted_message_count}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase opacity-70">
                        First created message
                      </dt>
                      <dd className="font-semibold">
                        {success.first_created_parent_message_id ??
                          "Unavailable"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase opacity-70">
                        Last created message
                      </dt>
                      <dd className="font-semibold">
                        {success.last_created_parent_message_id ??
                          "Unavailable"}
                      </dd>
                    </div>
                  </dl>
                </div>

                <div
                  className={
                    "rounded-xl border p-4 text-sm " +
                    (
                      isDark
                        ? "border-slate-700 bg-slate-900"
                        : "border-slate-200 bg-slate-50"
                    )
                  }
                >
                  The source branch remains unchanged.
                  Attachments, files, source metadata,
                  PDFs, documents, bookmarks,
                  RAG/Chroma data, branch metadata, and
                  model metadata were not copied.
                </div>
              </section>
            )}
        </div>

        <footer
          className={
            "flex shrink-0 justify-end border-t px-4 py-3 sm:px-5 " +
            (
              isDark
                ? "border-slate-800"
                : "border-slate-200"
            )
          }
        >
          {step === "preview" && (
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={requestClose}
                className={
                  "rounded-lg px-4 py-2 text-sm font-semibold transition " +
                  (
                    isDark
                      ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  )
                }
              >
                Close
              </button>
              {comparison?.comparable && (
                <button
                  type="button"
                  onClick={enterConfirmation}
                  disabled={!canEnterConfirmation}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Review final confirmation
                </button>
              )}
            </div>
          )}

          {step === "confirm" && (
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={returnToPreview}
                disabled={submitting}
                className={
                  "rounded-lg px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 " +
                  (
                    isDark
                      ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  )
                }
              >
                Back to preview
              </button>
              <button
                type="button"
                onClick={submitMergeRequest}
                disabled={
                  submitting ||
                  !acknowledged ||
                  (
                    !hasMergeCredential &&
                    !credentialInput
                  )
                }
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting
                  ? "Appending selected turnsâ€¦"
                  : submissionError?.retrySame
                    ? "Retry same request"
                    : "Append selected turns to parent"}
              </button>
            </div>
          )}

          {step === "success" && (
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={requestClose}
                className={
                  "rounded-lg px-4 py-2 text-sm font-semibold transition " +
                  (
                    isDark
                      ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  )
                }
              >
                Close
              </button>
              <button
                type="button"
                onClick={openMergedParent}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700"
              >
                Open parent and highlight merged messages
              </button>
            </div>
          )}
        </footer>
      </div>
    </div>
  );
}


export default BranchMergePreviewModal;
