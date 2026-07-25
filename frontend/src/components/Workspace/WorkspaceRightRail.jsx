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
  getDashboardHealth,
} from "../../services/dashboardService";


const DASHBOARD_CREDENTIAL_KEY =
  "onkar-ai-dashboard-credential";

const RIGHT_RAIL_HEALTH_REFRESH_MS =
  30_000;


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
          setHealthState(
            "unauthorized"
          );
          setHealthMessage(
            "Monitoring credential was not accepted"
          );
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
          data-right-rail-memory="placeholder"
          className={`rounded-2xl border border-dashed p-3.5 ${
            isDark
              ? "border-white/10 bg-white/[0.02]"
              : "border-slate-300 bg-slate-50/70"
          }`}
        >
          <div className="flex items-center gap-3">
            <span
              className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                isDark
                  ? "bg-violet-500/10 text-violet-300"
                  : "bg-violet-100 text-violet-700"
              }`}
            >
              <FiDatabase
                aria-hidden="true"
                size={17}
              />
            </span>

            <div>
              <h3 className="text-sm font-semibold">
                Memory
              </h3>

              <p className="text-[11px] text-slate-500">
                Coming later
              </p>
            </div>
          </div>

          <p className="mt-3 text-[11px] leading-4 text-slate-500">
            No memory data is shown until a
            real memory feature exists.
          </p>
        </section>

        <section
          data-right-rail-analytics="placeholder"
          data-right-rail-activity="no-timeseries"
          className={`rounded-2xl border border-dashed p-3.5 ${
            isDark
              ? "border-white/10 bg-white/[0.02]"
              : "border-slate-300 bg-slate-50/70"
          }`}
        >
          <div className="flex items-center gap-3">
            <span
              className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                isDark
                  ? "bg-cyan-500/10 text-cyan-300"
                  : "bg-cyan-100 text-cyan-700"
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
                Planned for v2.40
              </p>
            </div>
          </div>

          <div
            className={`mt-3 rounded-xl border border-dashed px-3 py-3 ${
              isDark
                ? "border-white/10 bg-slate-950/50"
                : "border-slate-200 bg-white"
            }`}
          >
            <div className="space-y-2 opacity-50">
              <div className="h-px bg-slate-600/30" />
              <div className="h-px bg-slate-600/30" />
              <div className="h-px bg-slate-600/30" />
            </div>

            <div className="mt-3 flex items-start gap-2 text-[11px] leading-4 text-slate-500">
              <FiActivity
                aria-hidden="true"
                className="mt-0.5 shrink-0"
                size={14}
              />

              <span>
                <span className="block font-medium">
                  No fabricated chart data
                </span>
                No real time-series source is
                available yet.
              </span>
            </div>
          </div>
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
