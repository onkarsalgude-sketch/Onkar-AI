import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  getBookmarks,
  removeMessageBookmark,
  saveMessageBookmark,
} from "../../services/chatService";


function formatBookmarkDate(
  value
) {
  if (!value) return "";

  const date = new Date(value);

  if (
    Number.isNaN(date.getTime())
  ) {
    return "";
  }

  return new Intl.DateTimeFormat(
    "en-IN",
    {
      dateStyle: "medium",
      timeStyle: "short",
    }
  ).format(date);
}


function BookmarksPanel({
  folders = [],
  onSelectResult,
  onPanelActiveChange,
  theme = "dark",
}) {
  const [isOpen, setIsOpen] =
    useState(false);

  const [query, setQuery] =
    useState("");

  const [role, setRole] =
    useState("");

  const [
    folderValue,
    setFolderValue,
  ] = useState("all");

  const [
    bookmarks,
    setBookmarks,
  ] = useState([]);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  const requestIdRef = useRef(0);

  const isDark =
    theme === "dark";


  useEffect(() => {
    onPanelActiveChange?.(
      isOpen
    );
  }, [
    isOpen,
    onPanelActiveChange,
  ]);


  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const timer =
      window.setTimeout(
        async () => {
          const requestId =
            requestIdRef.current + 1;

          requestIdRef.current =
            requestId;

          setLoading(true);
          setError("");

          let folderId = null;

          if (
            folderValue ===
            "unfiled"
          ) {
            folderId = 0;
          } else if (
            folderValue !==
            "all"
          ) {
            folderId = Number(
              folderValue
            );
          }

          try {
            const response =
              await getBookmarks({
                query,
                role:
                  role || null,
                folderId,
                limit: 200,
              });

            if (
              requestId !==
              requestIdRef.current
            ) {
              return;
            }

            setBookmarks(
              response?.data
                ?.bookmarks || []
            );
          } catch (requestError) {
            if (
              requestId !==
              requestIdRef.current
            ) {
              return;
            }

            console.error(
              "Load bookmarks error:",
              requestError
            );

            setBookmarks([]);

            setError(
              requestError?.response
                ?.data?.detail ||
                "Unable to load bookmarks."
            );
          } finally {
            if (
              requestId ===
              requestIdRef.current
            ) {
              setLoading(false);
            }
          }
        },
        300
      );

    return () => {
      window.clearTimeout(
        timer
      );
    };
  }, [
    isOpen,
    query,
    role,
    folderValue,
  ]);


  function closePanel() {
    setIsOpen(false);
  }


  function handleSelectBookmark(
    bookmark
  ) {
    onSelectResult?.(
      bookmark
    );

    closePanel();
  }


  async function handleEditNote(
    event,
    bookmark
  ) {
    event.stopPropagation();

    const enteredNote =
      window.prompt(
        "Update bookmark note:",
        bookmark.note || ""
      );

    if (enteredNote === null) {
      return;
    }

    try {
      const response =
        await saveMessageBookmark(
          bookmark.chat_id,
          bookmark.message_id,
          enteredNote.trim()
        );

      const updated =
        response?.data;

      setBookmarks(
        (currentBookmarks) =>
          currentBookmarks.map(
            (item) =>
              item.message_id ===
              bookmark.message_id
                ? {
                    ...item,
                    note:
                      updated?.note ??
                      enteredNote.trim(),
                    updated_at:
                      updated?.updated_at ??
                      item.updated_at,
                  }
                : item
          )
      );
    } catch (requestError) {
      console.error(
        "Update bookmark note error:",
        requestError
      );

      window.alert(
        requestError?.response
          ?.data?.detail ||
          "Unable to update the bookmark note."
      );
    }
  }


  async function handleRemoveBookmark(
    event,
    bookmark
  ) {
    event.stopPropagation();

    const confirmed =
      window.confirm(
        "Remove this bookmark?"
      );

    if (!confirmed) return;

    try {
      await removeMessageBookmark(
        bookmark.chat_id,
        bookmark.message_id
      );

      setBookmarks(
        (currentBookmarks) =>
          currentBookmarks.filter(
            (item) =>
              item.message_id !==
              bookmark.message_id
          )
      );
    } catch (requestError) {
      console.error(
        "Remove bookmark error:",
        requestError
      );

      window.alert(
        requestError?.response
          ?.data?.detail ||
          "Unable to remove the bookmark."
      );
    }
  }


  return (
    <div
      className={`mb-4 rounded-xl border ${
        isDark
          ? "border-slate-800 bg-slate-900/60"
          : "border-slate-200 bg-slate-50"
      }`}
    >
      <button
        type="button"
        onClick={() =>
          setIsOpen(
            (currentValue) =>
              !currentValue
          )
        }
        className={`flex w-full items-center justify-between rounded-xl px-3 py-3 text-left text-sm font-semibold transition ${
          isDark
            ? "hover:bg-slate-800"
            : "hover:bg-slate-100"
        }`}
        aria-expanded={isOpen}
      >
        <span>
          🔖 Bookmarks
        </span>

        <span
          className="text-xs text-slate-500"
        >
          {isOpen
            ? "▲"
            : "▼"}
        </span>
      </button>

      {isOpen && (
        <div
          className={`border-t p-3 ${
            isDark
              ? "border-slate-800"
              : "border-slate-200"
          }`}
        >
          <input
            type="search"
            value={query}
            onChange={(event) =>
              setQuery(
                event.target.value
              )
            }
            placeholder="Search bookmarks..."
            maxLength={200}
            className={`w-full rounded-lg border px-3 py-2 text-sm outline-none transition focus:border-amber-500 ${
              isDark
                ? "border-slate-700 bg-slate-950 text-white"
                : "border-slate-300 bg-white text-slate-900"
            }`}
          />

          <div className="mt-2 grid grid-cols-2 gap-2">
            <select
              value={role}
              onChange={(event) =>
                setRole(
                  event.target.value
                )
              }
              className={`rounded-lg border px-2 py-2 text-xs outline-none ${
                isDark
                  ? "border-slate-700 bg-slate-950 text-slate-300"
                  : "border-slate-300 bg-white text-slate-700"
              }`}
              aria-label="Bookmark role filter"
            >
              <option value="">
                All roles
              </option>

              <option value="user">
                User
              </option>

              <option value="assistant">
                Assistant
              </option>
            </select>

            <select
              value={folderValue}
              onChange={(event) =>
                setFolderValue(
                  event.target.value
                )
              }
              className={`rounded-lg border px-2 py-2 text-xs outline-none ${
                isDark
                  ? "border-slate-700 bg-slate-950 text-slate-300"
                  : "border-slate-300 bg-white text-slate-700"
              }`}
              aria-label="Bookmark folder filter"
            >
              <option value="all">
                All folders
              </option>

              <option value="unfiled">
                Unfiled
              </option>

              {folders.map(
                (folder) => (
                  <option
                    key={folder.id}
                    value={folder.id}
                  >
                    {folder.name}
                  </option>
                )
              )}
            </select>
          </div>

          <div className="mt-3 flex items-center justify-between">
            <p className="text-xs text-slate-500">
              {loading
                ? "Loading..."
                : `${bookmarks.length} bookmark${
                    bookmarks.length === 1
                      ? ""
                      : "s"
                  }`}
            </p>

            {(query ||
              role ||
              folderValue !==
                "all") && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setRole("");
                  setFolderValue(
                    "all"
                  );
                }}
                className="text-xs text-blue-500 hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>

          {error && (
            <p className="mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-500">
              {error}
            </p>
          )}

          {!loading &&
            !error &&
            bookmarks.length ===
              0 && (
              <p
                className={`mt-3 rounded-lg border border-dashed px-3 py-5 text-center text-xs ${
                  isDark
                    ? "border-slate-700 text-slate-500"
                    : "border-slate-300 text-slate-500"
                }`}
              >
                No bookmarks found
              </p>
            )}

          <div className="mt-3 max-h-96 space-y-2 overflow-y-auto pr-1">
            {bookmarks.map(
              (bookmark) => (
                <div
                  key={
                    bookmark.bookmark_id
                  }
                  role="button"
                  tabIndex={0}
                  onClick={() =>
                    handleSelectBookmark(
                      bookmark
                    )
                  }
                  onKeyDown={(event) => {
                    if (
                      event.key ===
                        "Enter" ||
                      event.key === " "
                    ) {
                      event.preventDefault();

                      handleSelectBookmark(
                        bookmark
                      );
                    }
                  }}
                  className={`block w-full cursor-pointer rounded-xl border p-3 text-left transition ${
                    isDark
                      ? "border-slate-700 bg-slate-950 hover:border-amber-500/60"
                      : "border-slate-200 bg-white hover:border-amber-400"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-amber-500">
                        🔖{" "}
                        {bookmark.chat_title ||
                          "Chat"}
                      </p>

                      <p
                        className={`mt-2 line-clamp-3 text-xs ${
                          isDark
                            ? "text-slate-300"
                            : "text-slate-700"
                        }`}
                      >
                        {bookmark.snippet ||
                          bookmark.content ||
                          "Empty message"}
                      </p>

                      {bookmark.note && (
                        <p
                          className={`mt-2 rounded-lg px-2 py-1.5 text-xs ${
                            isDark
                              ? "bg-amber-500/10 text-amber-200"
                              : "bg-amber-50 text-amber-800"
                          }`}
                        >
                          Note:{" "}
                          {bookmark.note}
                        </p>
                      )}

                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
                        <span>
                          {bookmark.role ===
                          "user"
                            ? "👤 User"
                            : "🤖 Assistant"}
                        </span>

                        {bookmark.folder_name && (
                          <span>
                            📁{" "}
                            {
                              bookmark.folder_name
                            }
                          </span>
                        )}

                        <span>
                          Message #
                          {
                            bookmark.message_id
                          }
                        </span>
                      </div>

                      {formatBookmarkDate(
                        bookmark.updated_at
                      ) && (
                        <p className="mt-1 text-[10px] text-slate-500">
                          Updated{" "}
                          {formatBookmarkDate(
                            bookmark.updated_at
                          )}
                        </p>
                      )}
                    </div>

                    <div className="flex shrink-0 gap-1">
                      <span
                        role="button"
                        tabIndex={0}
                        onClick={(
                          event
                        ) =>
                          handleEditNote(
                            event,
                            bookmark
                          )
                        }
                        onKeyDown={(
                          event
                        ) => {
                          if (
                            event.key ===
                              "Enter" ||
                            event.key ===
                              " "
                          ) {
                            handleEditNote(
                              event,
                              bookmark
                            );
                          }
                        }}
                        className={`rounded-md p-1.5 text-xs transition ${
                          isDark
                            ? "hover:bg-slate-800"
                            : "hover:bg-slate-100"
                        }`}
                        title="Edit bookmark note"
                        aria-label="Edit bookmark note"
                      >
                        ✏️
                      </span>

                      <span
                        role="button"
                        tabIndex={0}
                        onClick={(
                          event
                        ) =>
                          handleRemoveBookmark(
                            event,
                            bookmark
                          )
                        }
                        onKeyDown={(
                          event
                        ) => {
                          if (
                            event.key ===
                              "Enter" ||
                            event.key ===
                              " "
                          ) {
                            handleRemoveBookmark(
                              event,
                              bookmark
                            );
                          }
                        }}
                        className="rounded-md p-1.5 text-xs transition hover:bg-red-500/20"
                        title="Remove bookmark"
                        aria-label="Remove bookmark"
                      >
                        🗑️
                      </span>
                    </div>
                  </div>
                </div>
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default BookmarksPanel;