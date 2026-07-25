import {
  useEffect,
  useState,
} from "react";
import {
  FiActivity,
  FiBarChart2,
  FiCpu,
  FiDatabase,
  FiRadio,
} from "react-icons/fi";


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

  const [isOnline, setIsOnline] =
    useState(() => {
      if (
        typeof navigator ===
        "undefined"
      ) {
        return true;
      }

      return navigator.onLine;
    });

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

  return (
    <aside
      data-workspace-right-rail="v2.39"
      className={`hidden h-full w-[300px] shrink-0 flex-col overflow-hidden rounded-[28px] border shadow-2xl 2xl:flex ${
        isDark
          ? "border-white/10 bg-[#0b1020] text-white shadow-black/30"
          : "border-slate-200 bg-white text-slate-900 shadow-slate-300/50"
      }`}
    >
      <div
        className={`border-b px-4 py-5 ${
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
          Live controls only where the
          product already has real data.
        </p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <section
          data-right-rail-agents="live"
          className={`rounded-2xl border p-4 ${
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
                  Onkar-AI Agents
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

          {!agentsAvailable &&
            !agentsLoading && (
              <p className="mt-2 text-[11px] leading-4 text-slate-500">
                Chat remains in automatic mode
                while the catalog is unavailable.
              </p>
            )}
        </section>

        <section
          data-right-rail-network="live"
          className={`rounded-2xl border p-4 ${
            isDark
              ? "border-white/10 bg-white/[0.035]"
              : "border-slate-200 bg-slate-50"
          }`}
        >
          <div className="flex items-center gap-3">
            <span
              className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                isOnline
                  ? isDark
                    ? "bg-emerald-500/10 text-emerald-300"
                    : "bg-emerald-100 text-emerald-700"
                  : isDark
                    ? "bg-red-500/10 text-red-300"
                    : "bg-red-100 text-red-700"
              }`}
            >
              <FiRadio
                aria-hidden="true"
                size={17}
              />
            </span>

            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold">
                Browser Network
              </h3>

              <p
                className={`mt-0.5 text-xs ${
                  isOnline
                    ? "text-emerald-500"
                    : "text-red-500"
                }`}
              >
                {isOnline
                  ? "Online"
                  : "Offline"}
              </p>
            </div>
          </div>

          <p className="mt-3 text-[11px] leading-4 text-slate-500">
            This is your browser connection
            status, not backend system health.
          </p>
        </section>

        <section
          data-right-rail-memory="placeholder"
          className={`rounded-2xl border border-dashed p-4 ${
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
          className={`rounded-2xl border border-dashed p-4 ${
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
                Activity & Trends
              </h3>

              <p className="text-[11px] text-slate-500">
                Planned for v2.40
              </p>
            </div>
          </div>

          <div
            className={`mt-3 flex items-center gap-2 rounded-xl px-3 py-2 text-[11px] ${
              isDark
                ? "bg-slate-950/70 text-slate-500"
                : "bg-white text-slate-500"
            }`}
          >
            <FiActivity
              aria-hidden="true"
              size={14}
            />
            No fabricated chart data
          </div>
        </section>
      </div>
    </aside>
  );
}


export default WorkspaceRightRail;
