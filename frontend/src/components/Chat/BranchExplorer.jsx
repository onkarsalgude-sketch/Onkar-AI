import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import BranchCompareModal from "./BranchCompareModal";
import BranchMergePreviewModal from "./BranchMergePreviewModal";


function toPositiveId(value) {
  const numericId = Number(value);

  return Number.isInteger(numericId) &&
    numericId > 0
    ? numericId
    : null;
}


function compareChats(left, right) {
  const createdAtComparison = String(
    left.created_at || ""
  ).localeCompare(
    String(right.created_at || "")
  );

  if (createdAtComparison !== 0) {
    return createdAtComparison;
  }

  return left.id - right.id;
}


function BranchTreeNode({
  node,
  rootId,
  activeChatId,
  childrenByParentId,
  onSelect,
  isDark,
  depth = 0,
}) {
  const { chat, children } = node;
  const isRoot = chat.id === rootId;
  const isCurrent =
    chat.id === activeChatId;
  const isBranch =
    Boolean(chat.is_branch) ||
    toPositiveId(
      chat.parent_chat_id
    ) !== null;
  const directChildCount =
    childrenByParentId.get(chat.id)
      ?.length || 0;
  const title =
    String(chat.title || "").trim() ||
    "New Chat";

  return (
    <div
      className={
        depth > 0
          ? `ml-3 border-l pl-2 ${
              isDark
                ? "border-slate-700"
                : "border-slate-300"
            }`
          : ""
      }
    >
      <button
        type="button"
        onClick={() => onSelect(chat, isRoot)}
        title={title}
        className={`my-0.5 flex w-full min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition ${
          isCurrent
            ? isDark
              ? "bg-blue-500/20 text-blue-100 ring-1 ring-blue-500/60"
              : "bg-blue-100 text-blue-900 ring-1 ring-blue-300"
            : isDark
              ? "text-slate-300 hover:bg-slate-800"
              : "text-slate-700 hover:bg-slate-100"
        }`}
      >
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${
            isCurrent
              ? "bg-blue-500"
              : isBranch
                ? "bg-emerald-500"
                : "bg-slate-400"
          }`}
        />

        <span className="min-w-0 flex-1 truncate font-medium">
          {title}
        </span>

        <span className="flex shrink-0 items-center gap-1">
          {isRoot && (
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                isDark
                  ? "bg-violet-500/15 text-violet-300"
                  : "bg-violet-100 text-violet-700"
              }`}
            >
              Root
            </span>
          )}

          {isBranch && (
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                isDark
                  ? "bg-emerald-500/15 text-emerald-300"
                  : "bg-emerald-100 text-emerald-700"
              }`}
            >
              Branch
            </span>
          )}

          {isCurrent && (
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                isDark
                  ? "bg-blue-500/20 text-blue-200"
                  : "bg-blue-200 text-blue-800"
              }`}
            >
              Current
            </span>
          )}

          {directChildCount > 0 && (
            <span
              className={
                isDark
                  ? "text-slate-400"
                  : "text-slate-500"
              }
              title={`${directChildCount} direct ${
                directChildCount === 1
                  ? "branch"
                  : "branches"
              }`}
            >
              {directChildCount}
            </span>
          )}
        </span>
      </button>

      {children.map((child) => (
        <BranchTreeNode
          key={child.chat.id}
          node={child}
          rootId={rootId}
          activeChatId={activeChatId}
          childrenByParentId={
            childrenByParentId
          }
          onSelect={onSelect}
          isDark={isDark}
          depth={depth + 1}
        />
      ))}
    </div>
  );
}


function BranchExplorer({
  chats = [],
  activeChatId,
  onSelectChat,
  theme = "dark",
}) {
  const [isExpanded, setIsExpanded] =
    useState(true);
  const [isCompareOpen, setIsCompareOpen] =
    useState(false);
  const [compareBranchChatId, setCompareBranchChatId] =
    useState(null);
  const [
    isMergePreviewOpen,
    setIsMergePreviewOpen,
  ] = useState(false);
  const [
    mergePreviewBranchChatId,
    setMergePreviewBranchChatId,
  ] = useState(null);
  const compareButtonRef = useRef(null);
  const mergePreviewButtonRef = useRef(null);
  const isDark = theme === "dark";
  const normalizedActiveChatId =
    toPositiveId(activeChatId);

  const hierarchy = useMemo(() => {
    const chatById = new Map();

    for (const chat of chats) {
      const id = toPositiveId(chat?.id);

      if (id === null) continue;

      chatById.set(id, {
        ...chat,
        id,
      });
    }

    const activeChat = chatById.get(
      normalizedActiveChatId
    );

    if (!activeChat) {
      return null;
    }

    const childrenByParentId = new Map();

    for (const chat of chatById.values()) {
      const parentId = toPositiveId(
        chat.parent_chat_id
      );

      if (parentId === null) continue;

      const siblings =
        childrenByParentId.get(parentId) ||
        [];

      siblings.push(chat);
      childrenByParentId.set(
        parentId,
        siblings
      );
    }

    for (const siblings of
      childrenByParentId.values()) {
      siblings.sort(compareChats);
    }

    let rootChat = activeChat;
    const ancestorIds = new Set([
      activeChat.id,
    ]);

    while (true) {
      const parentId = toPositiveId(
        rootChat.parent_chat_id
      );

      if (
        parentId === null ||
        ancestorIds.has(parentId)
      ) {
        break;
      }

      const parentChat =
        chatById.get(parentId);

      if (!parentChat) break;

      rootChat = parentChat;
      ancestorIds.add(parentId);
    }

    const renderedIds = new Set();

    function buildNode(chat) {
      if (renderedIds.has(chat.id)) {
        return null;
      }

      renderedIds.add(chat.id);

      const children = (
        childrenByParentId.get(chat.id) ||
        []
      )
        .map(buildNode)
        .filter(Boolean);

      return {
        chat,
        children,
      };
    }

    const tree = buildNode(rootChat);
    const activeParentId = toPositiveId(
      activeChat.parent_chat_id
    );
    const activeParent =
      activeParentId === null
        ? null
        : chatById.get(activeParentId) ||
          null;

    return {
      activeChat,
      activeParent,
      childrenByParentId,
      rootChat,
      tree,
      treeChatCount: renderedIds.size,
    };
  }, [chats, normalizedActiveChatId]);

  useEffect(() => {
    if (
      isCompareOpen &&
      compareBranchChatId !==
        normalizedActiveChatId
    ) {
      setIsCompareOpen(false);
      setCompareBranchChatId(null);
    }
  }, [
    compareBranchChatId,
    isCompareOpen,
    normalizedActiveChatId,
  ]);

  useEffect(() => {
    if (
      isMergePreviewOpen &&
      mergePreviewBranchChatId !==
        normalizedActiveChatId
    ) {
      setIsMergePreviewOpen(false);
      setMergePreviewBranchChatId(null);
    }
  }, [
    isMergePreviewOpen,
    mergePreviewBranchChatId,
    normalizedActiveChatId,
  ]);

  if (!hierarchy?.tree) {
    return null;
  }

  const rootIsBranch =
    Boolean(hierarchy.rootChat.is_branch) ||
    toPositiveId(
      hierarchy.rootChat.parent_chat_id
    ) !== null;
  const shouldShow =
    hierarchy.treeChatCount > 1 ||
    rootIsBranch;

  if (!shouldShow) {
    return null;
  }

  function navigateToChat(chat, isRoot) {
    const branchMessageId =
      isRoot
        ? null
        : toPositiveId(
            chat.branch_message_id
          );

    onSelectChat?.(
      chat.id,
      branchMessageId,
      {
        missingTargetBehavior: "silent",
      }
    );
  }

  function navigateToParent() {
    if (!hierarchy.activeParent) return;

    onSelectChat?.(
      hierarchy.activeParent.id,
      toPositiveId(
        hierarchy.activeChat
          .branched_from_message_id
      ),
      {
        missingTargetBehavior: "silent",
      }
    );
  }

  function openComparison() {
    if (!hierarchy.activeParent) return;

    setCompareBranchChatId(
      hierarchy.activeChat.id
    );
    setIsCompareOpen(true);
  }

  function closeComparison() {
    setIsCompareOpen(false);
    setCompareBranchChatId(null);

    window.requestAnimationFrame(() => {
      compareButtonRef.current?.focus();
    });
  }

  function openMergePreview() {
    if (!hierarchy.activeParent) return;

    setMergePreviewBranchChatId(
      hierarchy.activeChat.id
    );
    setIsMergePreviewOpen(true);
  }

  function closeMergePreview() {
    setIsMergePreviewOpen(false);
    setMergePreviewBranchChatId(null);

    window.requestAnimationFrame(() => {
      mergePreviewButtonRef.current?.focus();
    });
  }

  return (
    <>
      <section
        className={`shrink-0 border-b px-3 py-2 sm:px-5 md:px-8 ${
          isDark
            ? "border-slate-800 bg-slate-950/40"
            : "border-slate-200 bg-white"
        }`}
        aria-label="Branch Explorer"
      >
        <div className="mx-auto max-w-4xl">
        <button
          type="button"
          onClick={() =>
            setIsExpanded((value) => !value)
          }
          className={`flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-left transition ${
            isDark
              ? "hover:bg-slate-800/80"
              : "hover:bg-slate-100"
          }`}
          aria-expanded={isExpanded}
          aria-controls="branch-explorer-tree"
        >
          <span className="flex min-w-0 items-center gap-2">
            <span
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded text-sm font-semibold ${
                isDark
                  ? "bg-slate-800 text-slate-300"
                  : "bg-slate-100 text-slate-600"
              }`}
              aria-hidden="true"
            >
              {isExpanded ? "-" : "+"}
            </span>

            <span className="truncate text-xs font-semibold uppercase tracking-wider">
              Branch Explorer
            </span>
          </span>

          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${
              isDark
                ? "bg-slate-800 text-slate-400"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            {hierarchy.treeChatCount} chats
          </span>
        </button>

          {isExpanded && (
            <div
              id="branch-explorer-tree"
              className="mt-1"
            >
              {hierarchy.activeParent && (
                <div className="mb-1 flex flex-wrap items-center gap-1">
                  <button
                    type="button"
                    onClick={navigateToParent}
                    title={`Go to parent: ${
                      hierarchy.activeParent.title ||
                      "New Chat"
                    }`}
                    className={`rounded-lg px-2 py-1 text-xs font-medium transition ${
                      isDark
                        ? "text-blue-300 hover:bg-blue-500/10"
                        : "text-blue-700 hover:bg-blue-50"
                    }`}
                  >
                    Go to parent
                  </button>

                  <button
                    ref={compareButtonRef}
                    type="button"
                    onClick={openComparison}
                    title={`Compare with parent: ${
                      hierarchy.activeParent.title ||
                      "New Chat"
                    }`}
                    className={`rounded-lg px-2 py-1 text-xs font-medium transition ${
                      isDark
                        ? "text-violet-300 hover:bg-violet-500/10"
                        : "text-violet-700 hover:bg-violet-50"
                    }`}
                  >
                    Compare with parent
                  </button>

                  <button
                    ref={mergePreviewButtonRef}
                    type="button"
                    onClick={openMergePreview}
                    title={
                      "Preview merge into parent: " +
                      (
                        hierarchy.activeParent
                          .title ||
                        "New Chat"
                      )
                    }
                    className={
                      "rounded-lg px-2 py-1 text-xs font-medium transition " +
                      (
                        isDark
                          ? "text-emerald-300 hover:bg-emerald-500/10"
                          : "text-emerald-700 hover:bg-emerald-50"
                      )
                    }
                  >
                    Merge Preview
                  </button>
                </div>
              )}

              <BranchTreeNode
                node={hierarchy.tree}
                rootId={hierarchy.rootChat.id}
                activeChatId={
                  normalizedActiveChatId
                }
                childrenByParentId={
                  hierarchy.childrenByParentId
                }
                onSelect={navigateToChat}
                isDark={isDark}
              />
            </div>
          )}
        </div>
      </section>

      <BranchCompareModal
        open={isCompareOpen}
        branchChatId={compareBranchChatId}
        onClose={closeComparison}
        theme={theme}
      />

      <BranchMergePreviewModal
        open={isMergePreviewOpen}
        branchChatId={
          mergePreviewBranchChatId
        }
        onClose={closeMergePreview}
        theme={theme}
      />
    </>
  );
}


export default BranchExplorer;
