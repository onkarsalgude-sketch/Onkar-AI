import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  searchChats,
} from "../../services/chatService";

const MIN_SEARCH_LENGTH = 2;
const SEARCH_DELAY_MS = 350;

function HighlightedText({
  text,
  query,
}) {
  const value = String(text || "");
  const searchValue = String(
    query || ""
  ).trim();

  if (!searchValue) {
    return value;
  }

  const lowerValue =
    value.toLowerCase();

  const lowerSearch =
    searchValue.toLowerCase();

  const parts = [];
  let start = 0;
  let matchIndex =
    lowerValue.indexOf(
      lowerSearch,
      start
    );

  while (matchIndex !== -1) {
    if (matchIndex > start) {
      parts.push(
        value.slice(
          start,
          matchIndex
        )
      );
    }

    parts.push(
      <mark
        key={`${matchIndex}-${parts.length}`}
        className="rounded bg-amber-300 px-0.5 text-slate-950"
      >
        {value.slice(
          matchIndex,
          matchIndex +
            searchValue.length
        )}
      </mark>
    );

    start =
      matchIndex +
      searchValue.length;

    matchIndex =
      lowerValue.indexOf(
        lowerSearch,
        start
      );
  }

  if (start < value.length) {
    parts.push(
      value.slice(start)
    );
  }

  return parts;
}

function GlobalChatSearch({
  folders = [],
  onSelectResult,
  onSearchActiveChange,
  theme = "dark",
}) {
  const isDark = theme === "dark";
  const requestIdRef = useRef(0);

  const [query, setQuery] =
    useState("");

  const [role, setRole] =
    useState("");

  const [folderFilter, setFolderFilter] =
    useState("all");

  const [results, setResults] =
    useState([]);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  const trimmedQuery =
    query.trim();

  const searchActive =
    trimmedQuery.length > 0;

  const canSearch =
    trimmedQuery.length >=
    MIN_SEARCH_LENGTH;

  const selectedFolderId =
    useMemo(() => {
      if (folderFilter === "all") {
        return null;
      }

      return Number(folderFilter);
    }, [folderFilter]);

  useEffect(() => {
    onSearchActiveChange?.(
      searchActive
    );
  }, [
    searchActive,
    onSearchActiveChange,
  ]);

  useEffect(() => {
    if (!canSearch) {
      requestIdRef.current += 1;
      setResults([]);
      setLoading(false);
      setError("");
      return undefined;
    }

    const currentRequestId =
      requestIdRef.current + 1;

    requestIdRef.current =
      currentRequestId;

    const timer = window.setTimeout(
      async () => {
        setLoading(true);
        setError("");

        try {
          const response =
            await searchChats(
              trimmedQuery,
              {
                role:
                  role || null,
                folderId:
                  selectedFolderId,
                limit: 50,
              }
            );

          if (
            requestIdRef.current !==
            currentRequestId
          ) {
            return;
          }

          setResults(
            response?.data?.results ||
              []
          );
        } catch (searchError) {
          if (
            requestIdRef.current !==
            currentRequestId
          ) {
            return;
          }

          console.error(
            "Global chat search error:",
            searchError
          );

          setResults([]);

          setError(
            searchError?.response?.data
              ?.detail ||
              "Unable to search chats."
          );
        } finally {
          if (
            requestIdRef.current ===
            currentRequestId
          ) {
            setLoading(false);
          }
        }
      },
      SEARCH_DELAY_MS
    );

    return () => {
      window.clearTimeout(timer);
    };
  }, [
    canSearch,
    role,
    selectedFolderId,
    trimmedQuery,
  ]);

  function clearSearch() {
    requestIdRef.current += 1;
    setQuery("");
    setRole("");
    setFolderFilter("all");
    setResults([]);
    setError("");
    setLoading(false);
  }

  return (
    <section className="mb-5">
      <div className="relative">
        <input
          type="search"
          value={query}
          onChange={(event) =>
            setQuery(
              event.target.value
            )
          }
          placeholder="🔍 Search all chats..."
          maxLength={200}
          className={`w-full rounded-xl border py-2.5 pl-3 pr-10 text-sm outline-none transition focus:border-blue-500 ${
            isDark
              ? "border-slate-700 bg-slate-900 text-white placeholder:text-slate-500"
              : "border-slate-300 bg-slate-50 text-slate-900 placeholder:text-slate-400"
          }`}
          aria-label="Search all chats"
        />

        {query && (
          <button
            type="button"
            onClick={clearSearch}
            className={`absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 text-xs transition ${
              isDark
                ? "text-slate-400 hover:bg-slate-800 hover:text-white"
                : "text-slate-500 hover:bg-slate-200 hover:text-slate-900"
            }`}
            aria-label="Clear search"
            title="Clear search"
          >
            ✕
          </button>
        )}
      </div>

      {searchActive && (
        <div
          className={`mt-3 rounded-xl border p-3 ${
            isDark
              ? "border-slate-800 bg-slate-900/70"
              : "border-slate-200 bg-slate-50"
          }`}
        >
          <div className="grid grid-cols-2 gap-2">
            <select
              value={role}
              onChange={(event) =>
                setRole(
                  event.target.value
                )
              }
              className={`rounded-lg border px-2 py-2 text-xs outline-none focus:border-blue-500 ${
                isDark
                  ? "border-slate-700 bg-slate-950 text-slate-200"
                  : "border-slate-300 bg-white text-slate-700"
              }`}
              aria-label="Filter by role"
            >
              <option value="">
                All roles
              </option>
              <option value="user">
                You
              </option>
              <option value="assistant">
                Onkar AI
              </option>
            </select>

            <select
              value={folderFilter}
              onChange={(event) =>
                setFolderFilter(
                  event.target.value
                )
              }
              className={`rounded-lg border px-2 py-2 text-xs outline-none focus:border-blue-500 ${
                isDark
                  ? "border-slate-700 bg-slate-950 text-slate-200"
                  : "border-slate-300 bg-white text-slate-700"
              }`}
              aria-label="Filter by folder"
            >
              <option value="all">
                All folders
              </option>
              <option value="0">
                Unfiled chats
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

          {!canSearch && (
            <p className="py-4 text-center text-xs text-slate-500">
              Enter at least{" "}
              {MIN_SEARCH_LENGTH}{" "}
              characters.
            </p>
          )}

          {canSearch && loading && (
            <p className="py-4 text-center text-xs text-slate-500">
              Searching all chats...
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

          {canSearch &&
            !loading &&
            !error &&
            results.length === 0 && (
              <p className="py-4 text-center text-xs text-slate-500">
                No matching chats or messages.
              </p>
            )}

          {!loading &&
            results.length > 0 && (
              <div className="mt-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Search Results
                  </p>

                  <span className="text-xs text-slate-500">
                    {results.length}
                  </span>
                </div>

                <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                  {results.map(
                    (result, index) => (
                      <button
                        type="button"
                        key={`${
                          result.match_type
                        }-${
                          result.message_id ||
                          result.chat_id
                        }-${index}`}
                        onClick={() =>
                          onSelectResult?.(
                            result
                          )
                        }
                        className={`w-full rounded-xl border p-3 text-left transition ${
                          isDark
                            ? "border-slate-800 bg-slate-950 hover:border-blue-500 hover:bg-slate-800"
                            : "border-slate-200 bg-white hover:border-blue-500 hover:bg-blue-50"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="min-w-0 flex-1 truncate text-sm font-semibold">
                            {result.match_type ===
                            "title"
                              ? "💬"
                              : result.role ===
                                  "user"
                                ? "👤"
                                : "🤖"}{" "}
                            {
                              result.chat_title
                            }
                          </p>

                          <span
                            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${
                              result.match_type ===
                              "title"
                                ? "bg-blue-500/15 text-blue-500"
                                : result.role ===
                                    "user"
                                  ? "bg-emerald-500/15 text-emerald-500"
                                  : "bg-violet-500/15 text-violet-500"
                            }`}
                          >
                            {result.match_type ===
                            "title"
                              ? "Title"
                              : result.role ===
                                  "user"
                                ? "You"
                                : "Onkar AI"}
                          </span>
                        </div>

                        <p
                          className={`mt-2 line-clamp-3 text-xs leading-5 ${
                            isDark
                              ? "text-slate-300"
                              : "text-slate-600"
                          }`}
                        >
                          <HighlightedText
                            text={
                              result.snippet
                            }
                            query={
                              trimmedQuery
                            }
                          />
                        </p>

                        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-500">
                          {result.folder_name && (
                            <span>
                              📁{" "}
                              {
                                result.folder_name
                              }
                            </span>
                          )}

                          {result.message_id && (
                            <span>
                              Message #
                              {
                                result.message_id
                              }
                            </span>
                          )}
                        </div>
                      </button>
                    )
                  )}
                </div>
              </div>
            )}
        </div>
      )}
    </section>
  );
}

export default GlobalChatSearch;
