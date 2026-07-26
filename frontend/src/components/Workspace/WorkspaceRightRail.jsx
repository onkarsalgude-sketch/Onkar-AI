import {
  useEffect,
  useRef,
  useState,
} from "react";
import {
  FiActivity,
  FiBarChart2,
  FiCpu,
  FiDatabase,
  FiLock,
  FiRadio,
} from "react-icons/fi";

import {
  getDashboardActivityToday,
  getDashboardHealth,
} from "../../services/dashboardService";
import {
  clearMemory,
  getMemory,
} from "../../services/memoryService";


const DASHBOARD_CREDENTIAL_KEY =
  "onkar-ai-dashboard-credential";

const MEMORY_CREDENTIAL_KEY =
  "onkar-ai-memory-credential";

const RIGHT_RAIL_HEALTH_REFRESH_MS =
  30_000;

const RIGHT_RAIL_MEMORY_LIMIT =
  6;


function readSessionCredential() {
  try {
    return (
      window.sessionStorage.getItem(
        DASHBOARD_CREDENTIAL_KEY
      ) || ""
    );
  } catch {
    return "";
  }
}


function removeSessionCredential() {
  try {
    window.sessionStorage.removeItem(
      DASHBOARD_CREDENTIAL_KEY
    );
  } catch {
    // Session storage may be unavailable.
  }
}


function activityStateLabel(state) {
  return {
    locked: "Locked",
    loading: "Loading",
    live: "Live",
    empty: "Empty",
    unauthorized: "Unauthorized",
    unavailable: "Unavailable",
  }[state] || "Unavailable";
}


function formatBucketLabel(startIso) {
  if (!startIso) {
    return "";
  }

  const match = String(
    startIso
  ).match(/T(\d{2}:\d{2})/);

  return match ? match[1] : "";
}



function readMemorySessionCredential() {
  try {
    return (
      window.sessionStorage.getItem(
        MEMORY_CREDENTIAL_KEY
      ) || ""
    );
  } catch {
    return "";
  }
}


function storeMemorySessionCredential(
  credential
) {
  try {
    window.sessionStorage.setItem(
      MEMORY_CREDENTIAL_KEY,
      credential
    );

    return true;
  } catch {
    return false;
  }
}


function removeMemorySessionCredential() {
  try {
    window.sessionStorage.removeItem(
      MEMORY_CREDENTIAL_KEY
    );
  } catch {
    // Session storage may be unavailable.
  }
}


function memoryStateLabel(state) {
  return {
    locked: "Locked",
    loading: "Loading",
    live: "Live",
    empty: "Empty",
    unauthorized: "Unauthorized",
    unavailable: "Unavailable",
  }[state] || "Unavailable";
}


function systemStatusLabel(status) {
  return {
    healthy: "Healthy",
    degraded: "Warning",
    unhealthy: "Critical",
    initializing: "Initializing",
  }[status] || "Unknown";
}


function componentStatusLabel(status) {
  return {
    healthy: "Healthy",
    degraded: "Warning",
    unavailable: "Unavailable",
    disabled: "Disabled",
  }[status] || "Unknown";
}


function healthToneClasses(
  status,
  isDark
) {
  if (status === "healthy") {
    return isDark
      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
      : "border-emerald-200 bg-emerald-50 text-emerald-700";
  }

  if (
    status === "degraded" ||
    status === "initializing"
  ) {
    return isDark
      ? "border-amber-500/20 bg-amber-500/10 text-amber-300"
      : "border-amber-200 bg-amber-50 text-amber-700";
  }

  if (
    status === "unhealthy" ||
    status === "unavailable"
  ) {
    return isDark
      ? "border-red-500/20 bg-red-500/10 text-red-300"
      : "border-red-200 bg-red-50 text-red-700";
  }

  return isDark
    ? "border-white/10 bg-slate-950/60 text-slate-400"
    : "border-slate-200 bg-white text-slate-600";
}


function formatCheckedAt(value) {
  if (!value) {
    return "";
  }

  const date =
    new Date(value);

  if (
    Number.isNaN(
      date.getTime()
    )
  ) {
    return "";
  }

  return date.toLocaleTimeString(
    [],
    {
      hour: "2-digit",
      minute: "2-digit",
    }
  );
}


function healthComponentLabel(name) {
  return {
    database: "Database",
    document_storage:
      "Document Storage",
    document_recovery:
      "Document Recovery",
    knowledge_rag:
      "Knowledge / RAG",
  }[name] || name || "Unknown";
}


function WorkspaceRightRail({
  agents = [],
  agentsLoading = false,
  agentsAvailable = false,
  selectedAgentId = "",
  onAgentChange,
  theme = "dark",
}) {
  const isDark =
    theme === "dark";

  const [
    isOnline,
    setIsOnline,
  ] = useState(() => {
    if (
      typeof navigator ===
      "undefined"
    ) {
      return true;
    }

    return navigator.onLine;
  });

  const [
    systemHealth,
    setSystemHealth,
  ] = useState(null);

  const [
    healthState,
    setHealthState,
  ] = useState("locked");

  const [
    healthMessage,
    setHealthMessage,
  ] = useState(
    "Dashboard credential required"
  );

  const healthInFlightRef =
    useRef(false);

  const healthEpochRef =
    useRef(0);

  const [
    activityData,
    setActivityData,
  ] = useState(null);

  const [
    activityState,
    setActivityState,
  ] = useState("locked");

  const [
    activityMessage,
    setActivityMessage,
  ] = useState(
    "Dashboard credential required"
  );

  const [
    activityRefreshKey,
    setActivityRefreshKey,
  ] = useState(0);

  const activityInFlightRef =
    useRef(false);

  const activityEpochRef =
    useRef(0);

  const [
    memoryItems,
    setMemoryItems,
  ] = useState([]);

  const [
    memoryState,
    setMemoryState,
  ] = useState("locked");

  const [
    memoryMessage,
    setMemoryMessage,
  ] = useState(
    "Memory credential required"
  );

  const [
    memoryCredentialInput,
    setMemoryCredentialInput,
  ] = useState("");

  const [
    memoryRefreshKey,
    setMemoryRefreshKey,
  ] = useState(0);

  const [
    memoryClearing,
    setMemoryClearing,
  ] = useState(false);

  const memoryInFlightRef =
    useRef(false);

  const memoryEpochRef =
    useRef(0);


  useEffect(() => {
    function handleOnline() {
      setIsOnline(true);
    }

    function handleOffline() {
      setIsOnline(false);
    }

    window.addEventListener(
      "online",
      handleOnline
    );

    window.addEventListener(
      "offline",
      handleOffline
    );

    return () => {
      window.removeEventListener(
        "online",
        handleOnline
      );

      window.removeEventListener(
        "offline",
        handleOffline
      );
    };
  }, []);


  useEffect(() => {
    let disposed = false;

    async function loadHealth() {
      if (
        healthInFlightRef.current
      ) {
        return;
      }

      const credential =
        readSessionCredential();

      if (!credential) {
        healthEpochRef.current += 1;

        if (!disposed) {
          setSystemHealth(null);
          setHealthState("locked");
          setHealthMessage(
            "Dashboard credential required"
          );
        }

        return;
      }

      const requestEpoch =
        healthEpochRef.current;

      healthInFlightRef.current =
        true;

      if (
        !disposed &&
        !systemHealth
      ) {
        setHealthState("loading");
        setHealthMessage(
          "Checking live backend health"
        );
      }

      try {
        const response =
          await getDashboardHealth(
            credential
          );

        if (
          disposed ||
          requestEpoch !==
            healthEpochRef.current
        ) {
          return;
        }

        if (
          response?.service ===
            "dashboard_health" &&
          response?.health?.service ===
            "system_health"
        ) {
          setSystemHealth(
            response.health
          );
          setHealthState("live");
          setHealthMessage("");
          return;
        }

        setSystemHealth(null);
        setHealthState("unavailable");
        setHealthMessage(
          "Live backend health unavailable"
        );
      } catch (error) {
        if (disposed) {
          return;
        }

        setSystemHealth(null);

        if (
          error?.status === 401
        ) {
          removeSessionCredential();
          setHealthState(
            "unauthorized"
          );
          setHealthMessage(
            "Monitoring credential was not accepted"
          );
          setActivityState(
            "unauthorized"
          );
          setActivityMessage(
            "Dashboard credential was not accepted"
          );
          setActivityData(null);
        } else if (
          error?.status === 404
        ) {
          setHealthState(
            "unavailable"
          );
          setHealthMessage(
            "Live system health is not enabled"
          );
        } else {
          setHealthState(
            "unavailable"
          );
          setHealthMessage(
            "Live backend health unavailable"
          );
        }
      } finally {
        healthInFlightRef.current =
          false;
      }
    }

    void loadHealth();

    const intervalId =
      window.setInterval(
        () => {
          void loadHealth();
        },
        RIGHT_RAIL_HEALTH_REFRESH_MS
      );

    function handleFocus() {
      void loadHealth();
    }

    window.addEventListener(
      "focus",
      handleFocus
    );

    return () => {
      disposed = true;
      healthEpochRef.current += 1;

      window.clearInterval(
        intervalId
      );

      window.removeEventListener(
        "focus",
        handleFocus
      );
    };
  }, []);


  useEffect(() => {
    let disposed = false;

    async function loadActivity() {
      if (
        activityInFlightRef.current
      ) {
        return;
      }

      const credential =
        readSessionCredential();

      if (!credential) {
        activityEpochRef.current += 1;

        if (!disposed) {
          setActivityData(null);
          setActivityState("locked");
          setActivityMessage(
            "Dashboard credential required"
          );
        }

        return;
      }

      const requestEpoch =
        activityEpochRef.current;

      activityInFlightRef.current =
        true;

      if (
        !disposed &&
        !activityData
      ) {
        setActivityState("loading");
        setActivityMessage(
          "Loading conversation activity"
        );
      }

      try {
        const response =
          await getDashboardActivityToday(
            credential
          );

        if (
          disposed ||
          requestEpoch !==
            activityEpochRef.current
        ) {
          return;
        }

        const act =
          response?.activity;

        if (
          response?.service ===
            "dashboard_activity" &&
          act
        ) {
          setActivityData(act);

          const total =
            act.messages?.total || 0;

          if (total > 0) {
            setActivityState("live");
            setActivityMessage("");
          } else {
            setActivityState("empty");
            setActivityMessage(
              "No conversation messages recorded for this server-local day."
            );
          }

          return;
        }

        setActivityData(null);
        setActivityState("unavailable");
        setActivityMessage(
          "Live activity data unavailable"
        );
      } catch (error) {
        if (disposed) {
          return;
        }

        setActivityData(null);

        if (
          error?.status === 401
        ) {
          removeSessionCredential();
          setActivityState(
            "unauthorized"
          );
          setActivityMessage(
            "Dashboard credential was not accepted"
          );
          setHealthState(
            "unauthorized"
          );
          setHealthMessage(
            "Monitoring credential was not accepted"
          );
          setSystemHealth(null);
        } else if (
          error?.status === 404
        ) {
          setActivityState(
            "unavailable"
          );
          setActivityMessage(
            "Activity API is not available"
          );
        } else {
          setActivityState(
            "unavailable"
          );
          setActivityMessage(
            "Live activity data unavailable"
          );
        }
      } finally {
        activityInFlightRef.current =
          false;
      }
    }

    void loadActivity();

    function handleFocus() {
      void loadActivity();
    }

    window.addEventListener(
      "focus",
      handleFocus
    );

    return () => {
      disposed = true;
      activityEpochRef.current += 1;

      window.removeEventListener(
        "focus",
        handleFocus
      );
    };
  }, [activityRefreshKey]);


  function handleActivityRefresh() {
    activityEpochRef.current += 1;
    setActivityRefreshKey(
      (value) => value + 1
    );
  }



  useEffect(() => {
    let disposed = false;

    async function loadMemory() {
      if (
        memoryInFlightRef.current
      ) {
        return;
      }

      const credential =
        readMemorySessionCredential();

      if (!credential) {
        memoryEpochRef.current += 1;

        if (!disposed) {
          setMemoryItems([]);
          setMemoryState("locked");
          setMemoryMessage(
            "Memory credential required"
          );
        }

        return;
      }

      const requestEpoch =
        memoryEpochRef.current;

      memoryInFlightRef.current =
        true;

      if (!disposed) {
        setMemoryState("loading");
        setMemoryMessage(
          "Loading stored conversation memory"
        );
      }

      try {
        const response =
          await getMemory(
            credential,
            {
              limit:
                RIGHT_RAIL_MEMORY_LIMIT,
            }
          );

        if (
          disposed ||
          requestEpoch !==
            memoryEpochRef.current
        ) {
          return;
        }

        const items =
          Array.isArray(
            response?.items
          )
            ? response.items
            : [];

        setMemoryItems(items);

        if (items.length > 0) {
          setMemoryState("live");
          setMemoryMessage("");
        } else {
          setMemoryState("empty");
          setMemoryMessage(
            "No stored conversational memory"
          );
        }
      } catch (error) {
        if (disposed) {
          return;
        }

        setMemoryItems([]);

        if (
          error?.status === 401
        ) {
          removeMemorySessionCredential();
          setMemoryState(
            "unauthorized"
          );
          setMemoryMessage(
            "Memory credential was not accepted"
          );
        } else if (
          error?.status === 404
        ) {
          setMemoryState(
            "unavailable"
          );
          setMemoryMessage(
            "Memory API is not available"
          );
        } else {
          setMemoryState(
            "unavailable"
          );
          setMemoryMessage(
            "Memory is unavailable"
          );
        }
      } finally {
        memoryInFlightRef.current =
          false;
      }
    }

    void loadMemory();

    function handleFocus() {
      void loadMemory();
    }

    window.addEventListener(
      "focus",
      handleFocus
    );

    return () => {
      disposed = true;
      memoryEpochRef.current += 1;

      window.removeEventListener(
        "focus",
        handleFocus
      );
    };
  }, [memoryRefreshKey]);


  function handleMemoryAuthorize(
    event
  ) {
    event.preventDefault();

    const credential =
      memoryCredentialInput.trim();

    if (!credential) {
      setMemoryState("locked");
      setMemoryMessage(
        "Enter the memory credential"
      );
      return;
    }

    if (
      !storeMemorySessionCredential(
        credential
      )
    ) {
      setMemoryState("unavailable");
      setMemoryMessage(
        "Browser session storage is unavailable"
      );
      return;
    }

    setMemoryCredentialInput("");
    memoryEpochRef.current += 1;
    setMemoryRefreshKey(
      (value) => value + 1
    );
  }


  function handleMemoryRefresh() {
    memoryEpochRef.current += 1;
    setMemoryRefreshKey(
      (value) => value + 1
    );
  }


  function handleForgetMemoryCredential() {
    removeMemorySessionCredential();
    memoryEpochRef.current += 1;
    setMemoryItems([]);
    setMemoryCredentialInput("");
    setMemoryState("locked");
    setMemoryMessage(
      "Memory credential required"
    );
  }


  async function handleClearMemory() {
    const credential =
      readMemorySessionCredential();

    if (!credential) {
      setMemoryItems([]);
      setMemoryState("locked");
      setMemoryMessage(
        "Memory credential required"
      );
      return;
    }

    const confirmed =
      window.confirm(
        "Clear all conversational memory? This cannot be undone."
      );

    if (!confirmed) {
      return;
    }

    setMemoryClearing(true);

    try {
      await clearMemory(
        credential
      );

      memoryEpochRef.current += 1;

      setMemoryRefreshKey(
        (value) => value + 1
      );
    } catch (error) {
      if (
        error?.status === 401
      ) {
        removeMemorySessionCredential();
        setMemoryItems([]);
        setMemoryState(
          "unauthorized"
        );
        setMemoryMessage(
          "Memory credential was not accepted"
        );
      } else {
        setMemoryState(
          "unavailable"
        );
        setMemoryMessage(
          "Memory could not be cleared"
        );
      }
    } finally {
      setMemoryClearing(false);
    }
  }


  const healthComponents =
    Array.isArray(
      systemHealth?.components
    )
      ? systemHealth.components
      : [];

  const checkedAt =
    formatCheckedAt(
      systemHealth?.checked_at
    );

  const systemStatus =
    systemHealth?.status || "";


  return (
    <aside
      data-workspace-right-rail="v2.40"
      className={`hidden h-full w-[300px] shrink-0 flex-col overflow-hidden rounded-[28px] border shadow-2xl 2xl:flex ${
        isDark
          ? "border-white/10 bg-[#0b1020] text-white shadow-black/30"
          : "border-slate-200 bg-white text-slate-900 shadow-slate-300/50"
      }`}
    >
      <div
        className={`border-b px-4 py-4 ${
          isDark
            ? "border-white/10"
            : "border-slate-200"
        }`}
      >
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          Workspace
        </p>

        <h2 className="mt-1 text-lg font-bold">
          AI Utilities
        </h2>

        <p
          className={`mt-1 text-xs leading-5 ${
            isDark
              ? "text-slate-400"
              : "text-slate-500"
          }`}
        >
          Real controls and honest
          availability states.
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        <section
          data-right-rail-agents="live"
          className={`rounded-2xl border p-3.5 ${
            isDark
              ? "border-white/10 bg-white/[0.035]"
              : "border-slate-200 bg-slate-50"
          }`}
        >
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                  isDark
                    ? "bg-blue-500/10 text-blue-300"
                    : "bg-blue-100 text-blue-700"
                }`}
              >
                <FiCpu
                  aria-hidden="true"
                  size={17}
                />
              </span>

              <div>
                <h3 className="text-sm font-semibold">
                  Agents
                </h3>

                <p className="text-[11px] text-slate-500">
                  Server catalog
                </p>
              </div>
            </div>

            <span
              className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
                agentsAvailable
                  ? isDark
                    ? "bg-emerald-500/10 text-emerald-300"
                    : "bg-emerald-100 text-emerald-700"
                  : isDark
                    ? "bg-slate-800 text-slate-400"
                    : "bg-slate-200 text-slate-600"
              }`}
            >
              {agentsLoading
                ? "Loading"
                : agentsAvailable
                  ? `${agents.length} live`
                  : "Unavailable"}
            </span>
          </div>

          <select
            value={selectedAgentId}
            onChange={(event) =>
              onAgentChange?.(
                event.target.value
              )
            }
            disabled={
              agentsLoading ||
              !agentsAvailable
            }
            className={`w-full rounded-xl border px-3 py-2 text-sm outline-none transition focus:border-blue-500 disabled:cursor-not-allowed disabled:opacity-60 ${
              isDark
                ? "border-white/10 bg-slate-950/80 text-white"
                : "border-slate-200 bg-white text-slate-900"
            }`}
            aria-label="Select workspace agent"
          >
            <option value="">
              {agentsLoading
                ? "Loading agents..."
                : agentsAvailable
                  ? "Automatic (no agent)"
                  : "Agent catalog unavailable"}
            </option>

            {agents.map((agent) => (
              <option
                key={agent.agent_id}
                value={agent.agent_id}
              >
                {agent.name}
              </option>
            ))}
          </select>
        </section>

        <section
          data-right-rail-memory={
            memoryState
          }
          className={`rounded-2xl border p-3.5 ${
            isDark
              ? "border-white/10 bg-white/[0.035]"
              : "border-slate-200 bg-slate-50"
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                  memoryState === "live"
                    ? isDark
                      ? "bg-violet-500/10 text-violet-300"
                      : "bg-violet-100 text-violet-700"
                    : isDark
                      ? "bg-slate-800 text-slate-400"
                      : "bg-slate-200 text-slate-600"
                }`}
              >
                {memoryState ===
                "locked" ? (
                  <FiLock
                    aria-hidden="true"
                    size={16}
                  />
                ) : (
                  <FiDatabase
                    aria-hidden="true"
                    size={17}
                  />
                )}
              </span>

              <div>
                <h3 className="text-sm font-semibold">
                  Memory
                </h3>

                <p className="text-[11px] text-slate-500">
                  Conversation memory
                </p>
              </div>
            </div>

            <span
              className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
                memoryState === "live"
                  ? isDark
                    ? "bg-emerald-500/10 text-emerald-300"
                    : "bg-emerald-100 text-emerald-700"
                  : memoryState ===
                        "unauthorized" ||
                      memoryState ===
                        "unavailable"
                    ? isDark
                      ? "bg-red-500/10 text-red-300"
                      : "bg-red-100 text-red-700"
                    : isDark
                      ? "bg-slate-800 text-slate-400"
                      : "bg-slate-200 text-slate-600"
              }`}
            >
              {memoryStateLabel(
                memoryState
              )}
            </span>
          </div>

          {(
            memoryState === "locked" ||
            memoryState === "unauthorized"
          ) ? (
            <form
              className="mt-3 space-y-2"
              onSubmit={
                handleMemoryAuthorize
              }
            >
              <label
                htmlFor="right-rail-memory-credential"
                className="block text-[11px] font-medium text-slate-400"
              >
                Memory credential
              </label>

              <input
                id="right-rail-memory-credential"
                type="password"
                value={
                  memoryCredentialInput
                }
                onChange={(event) =>
                  setMemoryCredentialInput(
                    event.target.value
                  )
                }
                autoComplete="off"
                placeholder="Enter credential"
                className={`w-full rounded-xl border px-3 py-2 text-xs outline-none transition focus:border-violet-500 ${
                  isDark
                    ? "border-white/10 bg-slate-950/80 text-white placeholder:text-slate-600"
                    : "border-slate-200 bg-white text-slate-900 placeholder:text-slate-400"
                }`}
              />

              <button
                type="submit"
                disabled={
                  !memoryCredentialInput.trim()
                }
                className="w-full rounded-xl bg-violet-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Authorize Memory
              </button>

              <p className="text-[10px] leading-4 text-slate-500">
                Stored only in sessionStorage for
                this browser session.
              </p>

              {memoryMessage && (
                <p
                  className={`text-[10px] leading-4 ${
                    memoryState ===
                    "unauthorized"
                      ? "text-red-400"
                      : "text-slate-500"
                  }`}
                >
                  {memoryMessage}
                </p>
              )}
            </form>
          ) : memoryState ===
            "loading" ? (
            <div
              className={`mt-3 rounded-xl px-3 py-2.5 text-[11px] ${
                isDark
                  ? "bg-slate-950/60 text-slate-400"
                  : "bg-white text-slate-600"
              }`}
            >
              Loading stored conversation
              memory...
            </div>
          ) : (
            <>
              {memoryState === "live" ? (
                <div className="mt-3 space-y-2">
                  {memoryItems.map(
                    (item, index) => (
                      <div
                        key={`${item.role}-${index}`}
                        data-memory-preview="backend"
                        data-memory-truncated={
                          item.truncated
                            ? "true"
                            : "false"
                        }
                        className={`rounded-xl border px-3 py-2 ${
                          isDark
                            ? "border-white/10 bg-slate-950/60"
                            : "border-slate-200 bg-white"
                        }`}
                      >
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-violet-400">
                          {item.role}
                        </p>

                        <p className="mt-1 break-words text-[11px] leading-4 text-slate-400">
                          {item.preview}
                          {item.truncated
                            ? "..."
                            : ""}
                        </p>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <div
                  className={`mt-3 rounded-xl px-3 py-2.5 text-[11px] leading-4 ${
                    isDark
                      ? "bg-slate-950/60 text-slate-400"
                      : "bg-white text-slate-600"
                  }`}
                >
                  <p className="font-medium">
                    {memoryMessage}
                  </p>
                </div>
              )}

              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={
                    handleMemoryRefresh
                  }
                  disabled={
                    memoryState ===
                    "loading"
                  }
                  className={`rounded-lg border px-2.5 py-1.5 text-[10px] font-semibold transition ${
                    isDark
                      ? "border-white/10 text-slate-300 hover:bg-white/[0.06]"
                      : "border-slate-200 text-slate-600 hover:bg-white"
                  }`}
                >
                  Refresh
                </button>

                <button
                  type="button"
                  onClick={
                    handleClearMemory
                  }
                  disabled={
                    memoryClearing
                  }
                  className="rounded-lg border border-red-500/20 px-2.5 py-1.5 text-[10px] font-semibold text-red-400 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {memoryClearing
                    ? "Clearing..."
                    : "Clear Memory"}
                </button>

                <button
                  type="button"
                  onClick={
                    handleForgetMemoryCredential
                  }
                  className="rounded-lg px-2.5 py-1.5 text-[10px] font-medium text-slate-500 transition hover:text-slate-300"
                >
                  Forget credential
                </button>
              </div>
            </>
          )}
        </section>

        <section
          data-right-rail-activity={
            activityState
          }
          data-activity-source="dashboard-backend"
          className={`rounded-2xl border p-3.5 ${
            isDark
              ? "border-white/10 bg-white/[0.035]"
              : "border-slate-200 bg-slate-50"
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                  activityState === "live"
                    ? isDark
                      ? "bg-cyan-500/10 text-cyan-300"
                      : "bg-cyan-100 text-cyan-700"
                    : isDark
                      ? "bg-slate-800 text-slate-400"
                      : "bg-slate-200 text-slate-600"
                }`}
              >
                <FiBarChart2
                  aria-hidden="true"
                  size={17}
                />
              </span>

              <div>
                <h3 className="text-sm font-semibold">
                  Today&apos;s Activity
                </h3>

                <p className="text-[11px] text-slate-500">
                  Conversation activity
                </p>
              </div>
            </div>

            <span
              className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
                activityState === "live"
                  ? isDark
                    ? "bg-emerald-500/10 text-emerald-300"
                    : "bg-emerald-100 text-emerald-700"
                  : activityState ===
                      "empty"
                    ? isDark
                      ? "bg-blue-500/10 text-blue-300"
                      : "bg-blue-100 text-blue-700"
                    : activityState ===
                          "unauthorized" ||
                        activityState ===
                          "unavailable"
                      ? isDark
                        ? "bg-red-500/10 text-red-300"
                        : "bg-red-100 text-red-700"
                      : isDark
                        ? "bg-slate-800 text-slate-400"
                        : "bg-slate-200 text-slate-600"
              }`}
            >
              {activityStateLabel(
                activityState
              )}
            </span>
          </div>

          <div className="mt-2 text-[11px] text-slate-500">
            Server-local day
            {activityData?.day
              ? ` · ${activityData.day}`
              : ""}
          </div>

          {activityState === "loading" ? (
            <div
              className={`mt-3 rounded-xl px-3 py-2.5 text-[11px] ${
                isDark
                  ? "bg-slate-950/60 text-slate-400"
                  : "bg-white text-slate-600"
              }`}
            >
              Loading conversation activity...
            </div>
          ) : activityState ===
              "locked" ||
            activityState ===
              "unauthorized" ? (
            <div
              className={`mt-3 rounded-xl px-3 py-2.5 text-[11px] leading-4 ${
                isDark
                  ? "bg-slate-950/60 text-slate-400"
                  : "bg-white text-slate-600"
              }`}
            >
              <p className="font-medium">
                {activityMessage}
              </p>

              <p className="mt-1 text-slate-500">
                Open Dashboard from the left
                sidebar to authorize live activity.
              </p>
            </div>
          ) : activityState ===
            "unavailable" ? (
            <div
              className={`mt-3 rounded-xl px-3 py-2.5 text-[11px] leading-4 ${
                isDark
                  ? "bg-slate-950/60 text-slate-400"
                  : "bg-white text-slate-600"
              }`}
            >
              <p className="font-medium">
                {activityMessage}
              </p>
            </div>
          ) : (
            <>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <div
                  className={`rounded-xl border p-2 ${
                    isDark
                      ? "border-white/10 bg-slate-950/60"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  <p className="text-[10px] font-semibold uppercase text-slate-400">
                    Total
                  </p>
                  <p className="mt-0.5 text-base font-bold">
                    {activityData?.messages?.total ??
                      0}
                  </p>
                </div>

                <div
                  className={`rounded-xl border p-2 ${
                    isDark
                      ? "border-white/10 bg-slate-950/60"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  <p className="text-[10px] font-semibold uppercase text-cyan-400">
                    User
                  </p>
                  <p className="mt-0.5 text-base font-bold">
                    {activityData?.messages?.user ??
                      0}
                  </p>
                </div>

                <div
                  className={`rounded-xl border p-2 ${
                    isDark
                      ? "border-white/10 bg-slate-950/60"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  <p className="text-[10px] font-semibold uppercase text-violet-400">
                    Assistant
                  </p>
                  <p className="mt-0.5 text-base font-bold">
                    {activityData?.messages?.assistant ??
                      0}
                  </p>
                </div>
              </div>

              {(activityData?.messages?.other ??
                0) > 0 && (
                <div className="mt-2 text-center text-[10px] text-slate-400">
                  Other:{" "}
                  {
                    activityData.messages
                      .other
                  }
                </div>
              )}

              {Array.isArray(
                activityData?.buckets
              ) &&
                activityData.buckets
                  .length > 0 && (
                  <div className="mt-3">
                    <div
                      className={`flex h-16 items-end gap-1.5 rounded-xl border p-2.5 ${
                        isDark
                          ? "border-white/10 bg-slate-950/60"
                          : "border-slate-200 bg-white"
                      }`}
                    >
                      {(() => {
                        const maxVal =
                          Math.max(
                            1,
                            ...activityData.buckets.map(
                              (b) =>
                                b.message_count ||
                                0
                            )
                          );

                        return activityData.buckets.map(
                          (b, idx) => {
                            const count =
                              b.message_count ||
                              0;

                            const heightPct =
                              count > 0
                                ? Math.max(
                                    8,
                                    Math.round(
                                      (count /
                                        maxVal) *
                                        100
                                    )
                                  )
                                : 0;

                            const label =
                              formatBucketLabel(
                                b.start
                              );

                            return (
                              <div
                                key={
                                  b.start ||
                                  idx
                                }
                                className="flex h-full flex-1 flex-col items-center justify-end"
                                title={`Bucket ${label}: ${count} messages`}
                                aria-label={`Bucket ${label}: ${count} messages`}
                              >
                                <div
                                  style={{
                                    height: `${heightPct}%`,
                                  }}
                                  className={`w-full rounded-t transition-all ${
                                    count > 0
                                      ? isDark
                                        ? "bg-cyan-500/80 hover:bg-cyan-400"
                                        : "bg-cyan-600 hover:bg-cyan-500"
                                      : "bg-transparent"
                                  }`}
                                />
                              </div>
                            );
                          }
                        );
                      })()}
                    </div>

                    <div className="mt-1.5 flex justify-between px-1 font-mono text-[9px] text-slate-500">
                      {activityData.buckets.map(
                        (b, idx) => (
                          <span
                            key={
                              b.start ||
                              idx
                            }
                          >
                            {formatBucketLabel(
                              b.start
                            )}
                          </span>
                        )
                      )}
                    </div>
                  </div>
                )}

              {activityState === "empty" && (
                <div className="mt-2 text-[11px] leading-4 text-slate-400">
                  No conversation messages
                  recorded for this
                  server-local day.
                </div>
              )}

              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={
                    handleActivityRefresh
                  }
                  disabled={
                    activityState ===
                    "loading"
                  }
                  className={`rounded-lg border px-2.5 py-1.5 text-[10px] font-semibold transition ${
                    isDark
                      ? "border-white/10 text-slate-300 hover:bg-white/[0.06]"
                      : "border-slate-200 text-slate-600 hover:bg-white"
                  }`}
                >
                  Refresh
                </button>
              </div>
            </>
          )}
        </section>

        <section
          data-right-rail-system-status={
            healthState
          }
          className={`rounded-2xl border p-3.5 ${
            isDark
              ? "border-white/10 bg-white/[0.035]"
              : "border-slate-200 bg-slate-50"
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                  healthState === "live"
                    ? healthToneClasses(
                        systemStatus,
                        isDark
                      )
                    : isDark
                      ? "bg-slate-800 text-slate-400"
                      : "bg-slate-200 text-slate-600"
                }`}
              >
                {healthState ===
                "locked" ? (
                  <FiLock
                    aria-hidden="true"
                    size={16}
                  />
                ) : (
                  <FiActivity
                    aria-hidden="true"
                    size={17}
                  />
                )}
              </span>

              <div>
                <h3 className="text-sm font-semibold">
                  System Status
                </h3>

                <p className="text-[11px] text-slate-500">
                  Backend health
                </p>
              </div>
            </div>

            {healthState === "live" && (
              <span
                className={`rounded-full border px-2 py-1 text-[10px] font-semibold ${healthToneClasses(
                  systemStatus,
                  isDark
                )}`}
              >
                {systemStatusLabel(
                  systemStatus
                )}
              </span>
            )}
          </div>

          {healthState === "live" ? (
            <>
              <div className="mt-3 space-y-2">
                {healthComponents
                  .slice(0, 3)
                  .map((component) => (
                    <div
                      key={
                        component?.name ||
                        component?.detail
                      }
                      className={`flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-[11px] ${
                        isDark
                          ? "bg-slate-950/60"
                          : "bg-white"
                      }`}
                    >
                      <span className="truncate text-slate-400">
                        {healthComponentLabel(
                          component?.name
                        )}
                      </span>

                      <span
                        className={`shrink-0 font-medium ${
                          component?.status ===
                          "healthy"
                            ? "text-emerald-500"
                            : component?.status ===
                                "degraded"
                              ? "text-amber-500"
                              : "text-slate-500"
                        }`}
                      >
                        {componentStatusLabel(
                          component?.status
                        )}
                      </span>
                    </div>
                  ))}
              </div>

              {checkedAt && (
                <p className="mt-2 text-[10px] text-slate-500">
                  Last checked {checkedAt}
                </p>
              )}
            </>
          ) : (
            <div
              className={`mt-3 rounded-xl px-3 py-2.5 text-[11px] leading-4 ${
                isDark
                  ? "bg-slate-950/60 text-slate-400"
                  : "bg-white text-slate-600"
              }`}
            >
              <p className="font-medium">
                {healthMessage}
              </p>

              {healthState ===
                "locked" && (
                <p className="mt-1 text-slate-500">
                  Open Dashboard from the left
                  sidebar to authorize live health.
                </p>
              )}
            </div>
          )}

          <div
            data-right-rail-network="live"
            className={`mt-3 flex items-center justify-between gap-3 border-t pt-3 ${
              isDark
                ? "border-white/10"
                : "border-slate-200"
            }`}
          >
            <div className="flex items-center gap-2">
              <FiRadio
                aria-hidden="true"
                size={14}
                className={
                  isOnline
                    ? "text-emerald-500"
                    : "text-red-500"
                }
              />

              <div>
                <p className="text-[11px] font-medium">
                  Browser Network
                </p>

                <p className="text-[10px] text-slate-500">
                  Browser connectivity only —
                  not backend system health.
                </p>
              </div>
            </div>

            <span
              className={`text-[10px] font-semibold ${
                isOnline
                  ? "text-emerald-500"
                  : "text-red-500"
              }`}
            >
              {isOnline
                ? "Online"
                : "Offline"}
            </span>
          </div>
        </section>
      </div>
    </aside>
  );
}


export default WorkspaceRightRail;
