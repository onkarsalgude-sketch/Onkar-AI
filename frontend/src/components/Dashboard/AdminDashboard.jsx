import {
  useEffect,
  useState,
} from "react";

import {
  getDashboardHealth,
  getDashboardSummary,
} from "../../services/dashboardService";


const DASHBOARD_CREDENTIAL_KEY =
  "onkar-ai-dashboard-credential";


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


function storeSessionCredential(
  credential
) {
  try {
    window.sessionStorage.setItem(
      DASHBOARD_CREDENTIAL_KEY,
      credential
    );
  } catch {
    // Session storage is optional.
  }
}


function clearSessionCredential() {
  try {
    window.sessionStorage.removeItem(
      DASHBOARD_CREDENTIAL_KEY
    );
  } catch {
    // Session storage is optional.
  }
}


function formatBytes(value) {
  const bytes = Math.max(
    0,
    Number(value) || 0
  );

  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(
      bytes / 1024
    ).toFixed(1)} KB`;
  }

  if (bytes < 1024 * 1024 * 1024) {
    return `${(
      bytes /
      (1024 * 1024)
    ).toFixed(1)} MB`;
  }

  return `${(
    bytes /
    (1024 * 1024 * 1024)
  ).toFixed(2)} GB`;
}


function formatCheckedAt(value) {
  if (!value) {
    return "Not available";
  }

  const date = new Date(value);

  if (
    Number.isNaN(
      date.getTime()
    )
  ) {
    return "Not available";
  }

  return date.toLocaleString();
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
      ? "border-emerald-700/70 bg-emerald-950/40 text-emerald-200"
      : "border-emerald-200 bg-emerald-50 text-emerald-800";
  }

  if (
    status === "degraded" ||
    status === "initializing"
  ) {
    return isDark
      ? "border-amber-700/70 bg-amber-950/40 text-amber-200"
      : "border-amber-200 bg-amber-50 text-amber-800";
  }

  if (
    status === "unhealthy" ||
    status === "unavailable"
  ) {
    return isDark
      ? "border-red-700/70 bg-red-950/40 text-red-200"
      : "border-red-200 bg-red-50 text-red-800";
  }

  return isDark
    ? "border-slate-700 bg-slate-900 text-slate-300"
    : "border-slate-200 bg-slate-50 text-slate-700";
}


function HealthStatusBadge({
  status,
  isDark,
  system = false,
}) {
  const label = system
    ? systemStatusLabel(status)
    : componentStatusLabel(status);

  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${healthToneClasses(
        status,
        isDark
      )}`}
    >
      {label}
    </span>
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


function HealthComponentRow({
  component,
  isDark,
}) {
  return (
    <div
      className={`rounded-xl border p-3 ${
        isDark
          ? "border-slate-700 bg-slate-900"
          : "border-slate-200 bg-slate-50"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">
            {healthComponentLabel(
              component?.name
            )}
          </p>

          <p
            className={`mt-1 text-xs ${
              isDark
                ? "text-slate-400"
                : "text-slate-500"
            }`}
          >
            {component?.detail ||
              "No detail"}{" "}
            ·{" "}
            {Math.max(
              0,
              Number(
                component?.latency_ms
              ) || 0
            )}{" "}
            ms
          </p>
        </div>

        <HealthStatusBadge
          status={component?.status}
          isDark={isDark}
        />
      </div>
    </div>
  );
}


function MetricCard({
  label,
  value,
  note = "",
  isDark,
}) {
  return (
    <div
      className={`rounded-2xl border p-4 ${
        isDark
          ? "border-slate-700 bg-slate-800/80"
          : "border-slate-200 bg-white"
      }`}
    >
      <p
        className={`text-xs font-semibold uppercase tracking-wider ${
          isDark
            ? "text-slate-400"
            : "text-slate-500"
        }`}
      >
        {label}
      </p>

      <p className="mt-2 text-2xl font-bold">
        {value}
      </p>

      {note && (
        <p
          className={`mt-1 text-xs ${
            isDark
              ? "text-slate-400"
              : "text-slate-500"
          }`}
        >
          {note}
        </p>
      )}
    </div>
  );
}


function AdminDashboard({
  open,
  onClose,
  theme = "dark",
}) {
  const isDark = theme === "dark";

  const [
    credential,
    setCredential,
  ] = useState("");

  const [
    summary,
    setSummary,
  ] = useState(null);

  const [
    health,
    setHealth,
  ] = useState(null);

  const [
    healthErrorMessage,
    setHealthErrorMessage,
  ] = useState("");

  const [
    loading,
    setLoading,
  ] = useState(false);

  const [
    errorMessage,
    setErrorMessage,
  ] = useState("");

  function dashboardErrorMessage(
    error,
    kind
  ) {
    if (
      error?.code ===
      "credential_required"
    ) {
      return (
        "Enter the monitoring credential to continue."
      );
    }

    if (error?.status === 401) {
      return (
        "The monitoring credential was not accepted."
      );
    }

    if (error?.status === 404) {
      return kind === "health"
        ? "Live system health is not enabled on this server."
        : "The dashboard endpoint is not enabled on this server.";
    }

    if (error?.status === 503) {
      return kind === "health"
        ? "Live system health is temporarily unavailable."
        : "Dashboard metrics are temporarily unavailable.";
    }

    return kind === "health"
      ? "Could not load live system health."
      : "Could not load dashboard metrics.";
  }

  async function loadDashboard(
    suppliedCredential
  ) {
    const token = String(
      suppliedCredential || ""
    ).trim();

    if (!token) {
      setSummary(null);
      setHealth(null);
      setHealthErrorMessage("");
      setErrorMessage(
        "Enter the monitoring credential to load dashboard metrics."
      );
      return;
    }

    setLoading(true);
    setErrorMessage("");
    setHealthErrorMessage("");

    try {
      const [
        summaryResult,
        healthResult,
      ] = await Promise.allSettled([
        getDashboardSummary(token),
        getDashboardHealth(token),
      ]);

      let acceptedCredential =
        false;

      if (
        summaryResult.status ===
        "fulfilled"
      ) {
        const response =
          summaryResult.value;

        if (
          response?.service ===
            "dashboard" &&
          response?.summary
        ) {
          setSummary(
            response.summary
          );
          acceptedCredential =
            true;
        } else {
          setErrorMessage(
            "Could not load dashboard metrics."
          );
        }
      } else {
        setErrorMessage(
          dashboardErrorMessage(
            summaryResult.reason,
            "summary"
          )
        );
      }

      if (
        healthResult.status ===
        "fulfilled"
      ) {
        const response =
          healthResult.value;

        if (
          response?.service ===
            "dashboard_health" &&
          response?.health?.service ===
            "system_health"
        ) {
          setHealth(
            response.health
          );
          acceptedCredential =
            true;
        } else {
          setHealthErrorMessage(
            "Could not load live system health."
          );
        }
      } else {
        setHealthErrorMessage(
          dashboardErrorMessage(
            healthResult.reason,
            "health"
          )
        );
      }

      if (acceptedCredential) {
        storeSessionCredential(
          token
        );
        setCredential(token);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open) {
      return;
    }

    const savedCredential =
      readSessionCredential();

    setCredential(
      savedCredential
    );

    if (savedCredential) {
      loadDashboard(
        savedCredential
      );
    }
  }, [open]);

  if (!open) {
    return null;
  }

  const usage =
    summary?.usage || {};

  const chats =
    usage?.chats || {};

  const messages =
    usage?.messages || {};

  const agents =
    usage?.agents || {};

  const documents =
    usage?.documents || {};

  const storage =
    usage?.storage || {};

  const recovery =
    summary?.recovery || {
      available: false,
      metrics: null,
    };

  const incidents =
    summary?.incidents || {
      available: false,
      metrics: null,
    };

  const agentUsage =
    Array.isArray(
      agents?.usage
    )
      ? agents.usage
      : [];

  const healthComponents =
    Array.isArray(
      health?.components
    )
      ? health.components
      : [];

  function handleSubmit(event) {
    event.preventDefault();
    loadDashboard(
      credential
    );
  }

  function handleForgetCredential() {
    clearSessionCredential();
    setCredential("");
    setSummary(null);
    setHealth(null);
    setHealthErrorMessage("");
    setErrorMessage(
      "Monitoring credential cleared for this browser session."
    );
  }

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
      onClick={
        handleOverlayClick
      }
      className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60 px-3 py-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Admin dashboard"
    >
      <div
        className={`flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border shadow-2xl ${
          isDark
            ? "border-slate-700 bg-slate-900 text-white"
            : "border-slate-200 bg-slate-50 text-slate-900"
        }`}
      >
        <div
          className={`flex items-start justify-between gap-4 border-b p-5 ${
            isDark
              ? "border-slate-700"
              : "border-slate-200"
          }`}
        >
          <div>
            <h2 className="text-xl font-bold">
              📊 Admin Dashboard
            </h2>

            <p
              className={`mt-1 text-sm ${
                isDark
                  ? "text-slate-400"
                  : "text-slate-500"
              }`}
            >
              Live system health, usage,
              storage, recovery, and incident visibility.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className={`rounded-lg p-2 text-xl transition ${
              isDark
                ? "text-slate-400 hover:bg-slate-800 hover:text-white"
                : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            }`}
            aria-label="Close dashboard"
          >
            ✕
          </button>
        </div>

        <div className="overflow-y-auto p-5">
          <form
            onSubmit={handleSubmit}
            className={`mb-5 rounded-2xl border p-4 ${
              isDark
                ? "border-slate-700 bg-slate-800/60"
                : "border-slate-200 bg-white"
            }`}
          >
            <label
              htmlFor="dashboard-credential"
              className="text-sm font-semibold"
            >
              Monitoring credential
            </label>

            <p
              className={`mt-1 text-xs ${
                isDark
                  ? "text-slate-400"
                  : "text-slate-500"
              }`}
            >
              Stored only in sessionStorage
              for this browser tab.
            </p>

            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <input
                id="dashboard-credential"
                type="password"
                autoComplete="off"
                value={credential}
                onChange={(event) =>
                  setCredential(
                    event.target.value
                  )
                }
                placeholder="Enter monitoring credential"
                className={`min-w-0 flex-1 rounded-xl border px-3 py-2 outline-none focus:border-blue-500 ${
                  isDark
                    ? "border-slate-700 bg-slate-950 text-white"
                    : "border-slate-300 bg-white text-slate-900"
                }`}
              />

              <button
                type="submit"
                disabled={
                  loading ||
                  !credential.trim()
                }
                className="rounded-xl bg-blue-600 px-4 py-2 font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {loading
                  ? "Loading…"
                  : summary || health
                    ? "Refresh"
                    : "Load Dashboard"}
              </button>

              <button
                type="button"
                onClick={
                  handleForgetCredential
                }
                className={`rounded-xl border px-4 py-2 font-semibold transition ${
                  isDark
                    ? "border-slate-700 hover:bg-slate-800"
                    : "border-slate-300 hover:bg-slate-100"
                }`}
              >
                Forget credential
              </button>
            </div>

            {errorMessage && (
              <p
                className={`mt-3 rounded-xl border px-3 py-2 text-sm ${
                  isDark
                    ? "border-amber-700/60 bg-amber-950/30 text-amber-200"
                    : "border-amber-200 bg-amber-50 text-amber-800"
                }`}
              >
                {errorMessage}
              </p>
            )}
          </form>

          {!summary &&
            !health &&
            !healthErrorMessage &&
            !loading && (
            <div
              className={`rounded-2xl border border-dashed p-8 text-center ${
                isDark
                  ? "border-slate-700 text-slate-400"
                  : "border-slate-300 text-slate-500"
              }`}
            >
              Enter the monitoring
              credential to view metrics.
            </div>
          )}

          {(health ||
            healthErrorMessage) && (
            <section
              className={`mb-5 rounded-2xl border p-4 ${
                isDark
                  ? "border-slate-700 bg-slate-800/60"
                  : "border-slate-200 bg-white"
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold">
                    System Health
                  </h3>

                  <p
                    className={`mt-1 text-xs ${
                      isDark
                        ? "text-slate-400"
                        : "text-slate-500"
                    }`}
                  >
                    Last checked:{" "}
                    {formatCheckedAt(
                      health?.checked_at
                    )}
                  </p>
                </div>

                {health && (
                  <HealthStatusBadge
                    status={health.status}
                    isDark={isDark}
                    system
                  />
                )}
              </div>

              {healthErrorMessage && (
                <p
                  className={`mt-3 rounded-xl border px-3 py-2 text-sm ${
                    isDark
                      ? "border-amber-700/60 bg-amber-950/30 text-amber-200"
                      : "border-amber-200 bg-amber-50 text-amber-800"
                  }`}
                >
                  {healthErrorMessage}
                </p>
              )}

              {health && (
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {healthComponents.map(
                    (component) => (
                      <HealthComponentRow
                        key={
                          component.name
                        }
                        component={
                          component
                        }
                        isDark={isDark}
                      />
                    )
                  )}
                </div>
              )}
            </section>
          )}

          {summary && (
            <div className="space-y-5">
              <section>
                <h3 className="mb-3 text-sm font-semibold">
                  Usage & Storage
                </h3>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <MetricCard
                    label="Chats"
                    value={
                      chats.total || 0
                    }
                    isDark={isDark}
                  />

                  <MetricCard
                    label="Messages"
                    value={
                      messages.total ||
                      0
                    }
                    note={`${messages.user || 0} user · ${messages.assistant || 0} assistant`}
                    isDark={isDark}
                  />

                  <MetricCard
                    label="Documents"
                    value={
                      documents.total ||
                      0
                    }
                    note={`${documents.ready || 0} ready`}
                    isDark={isDark}
                  />

                  <MetricCard
                    label="Document Storage"
                    value={formatBytes(
                      storage.document_bytes
                    )}
                    isDark={isDark}
                  />
                </div>
              </section>

              <section
                className={`rounded-2xl border p-4 ${
                  isDark
                    ? "border-slate-700 bg-slate-800/60"
                    : "border-slate-200 bg-white"
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">
                    Agent Usage
                  </h3>

                  <span
                    className={`text-xs ${
                      isDark
                        ? "text-slate-400"
                        : "text-slate-500"
                    }`}
                  >
                    {agents.assistant_messages_with_agent || 0} tagged assistant messages
                  </span>
                </div>

                {agentUsage.length > 0 ? (
                  <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {agentUsage.map(
                      (item) => (
                        <div
                          key={
                            item.agent_id
                          }
                          className={`rounded-xl border px-3 py-2 ${
                            isDark
                              ? "border-slate-700 bg-slate-900"
                              : "border-slate-200 bg-slate-50"
                          }`}
                        >
                          <p className="font-semibold">
                            {
                              item.agent_id
                            }
                          </p>
                          <p
                            className={`text-xs ${
                              isDark
                                ? "text-slate-400"
                                : "text-slate-500"
                            }`}
                          >
                            {item.message_count || 0} messages
                          </p>
                        </div>
                      )
                    )}
                  </div>
                ) : (
                  <p
                    className={`mt-3 text-sm ${
                      isDark
                        ? "text-slate-400"
                        : "text-slate-500"
                    }`}
                  >
                    No agent-tagged
                    assistant messages yet.
                  </p>
                )}
              </section>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <section
                  className={`rounded-2xl border p-4 ${
                    isDark
                      ? "border-slate-700 bg-slate-800/60"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  <h3 className="text-sm font-semibold">
                    Recovery
                  </h3>

                  {!recovery.available ? (
                    <p
                      className={`mt-3 text-sm ${
                        isDark
                          ? "text-slate-400"
                          : "text-slate-500"
                      }`}
                    >
                      Recovery metrics
                      are unavailable.
                    </p>
                  ) : (
                    <div className="mt-3 grid grid-cols-2 gap-3">
                      <MetricCard
                        label="Runs"
                        value={
                          recovery.metrics?.total_runs ||
                          0
                        }
                        isDark={isDark}
                      />

                      <MetricCard
                        label="Failure Runs"
                        value={
                          recovery.metrics?.failure_runs ||
                          0
                        }
                        note={`${recovery.metrics?.total_failures || 0} failures`}
                        isDark={isDark}
                      />
                    </div>
                  )}
                </section>

                <section
                  className={`rounded-2xl border p-4 ${
                    isDark
                      ? "border-slate-700 bg-slate-800/60"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  <h3 className="text-sm font-semibold">
                    Incidents
                  </h3>

                  {!incidents.available ? (
                    <p
                      className={`mt-3 text-sm ${
                        isDark
                          ? "text-slate-400"
                          : "text-slate-500"
                      }`}
                    >
                      Incident metrics
                      are unavailable.
                    </p>
                  ) : (
                    <div className="mt-3 grid grid-cols-2 gap-3">
                      <MetricCard
                        label="Active"
                        value={
                          incidents.metrics?.active_count ||
                          0
                        }
                        note={`${incidents.metrics?.active_critical_count || 0} critical`}
                        isDark={isDark}
                      />

                      <MetricCard
                        label="Resolved"
                        value={
                          incidents.metrics?.resolved_count ||
                          0
                        }
                        note={`${incidents.metrics?.total_incidents || 0} total`}
                        isDark={isDark}
                      />
                    </div>
                  )}
                </section>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


export default AdminDashboard;
