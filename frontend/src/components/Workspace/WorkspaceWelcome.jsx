import {
  useMemo,
} from "react";
import {
  FiBookmark,
  FiBookOpen,
  FiCode,
  FiCompass,
  FiDatabase,
  FiEdit3,
  FiGitBranch,
  FiLayers,
  FiSearch,
} from "react-icons/fi";


const QUICK_ACTIONS = [
  {
    id: "study",
    label: "Study",
    description:
      "Learn a topic step by step",
    icon: FiBookOpen,
    prompt:
      "Help me study this topic step by step: ",
  },
  {
    id: "code",
    label: "Code",
    description:
      "Build, explain, or debug code",
    icon: FiCode,
    prompt:
      "Help me write or debug code for this task: ",
  },
  {
    id: "research",
    label: "Research",
    description:
      "Explore a topic in depth",
    icon: FiSearch,
    prompt:
      "Research this topic and summarize the important points: ",
  },
  {
    id: "write",
    label: "Write",
    description:
      "Draft and improve writing",
    icon: FiEdit3,
    prompt:
      "Help me write and improve this: ",
  },
  {
    id: "analyze",
    label: "Analyze",
    description:
      "Find patterns and key insights",
    icon: FiCompass,
    prompt:
      "Analyze this and explain the key insights: ",
  },
  {
    id: "create",
    label: "Create",
    description:
      "Turn an idea into a plan",
    icon: FiLayers,
    prompt:
      "Help me create a plan, idea, or project from this: ",
  },
];


function getGreeting() {
  const hour =
    new Date().getHours();

  if (hour < 12) {
    return "Good morning";
  }

  if (hour < 18) {
    return "Good afternoon";
  }

  return "Good evening";
}


function WorkspaceWelcome({
  setInput,
  activeChatId = null,
  branchCount = 0,
  onOpenKnowledge,
  onOpenBranches,
  onOpenSidebar,
  theme = "dark",
}) {
  const isDark =
    theme === "dark";

  const greeting = useMemo(
    () => getGreeting(),
    []
  );

  function chooseAction(action) {
    setInput?.(action.prompt);
  }

  return (
    <section
      data-workspace-welcome="v2.39"
      className="pb-7 pt-3 sm:pb-9 sm:pt-5"
    >
      <div className="mx-auto max-w-5xl">
        <div className="mb-7 flex flex-col gap-3 sm:mb-8">
          <div className="flex items-center gap-2">
            <span
              className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${
                isDark
                  ? "border-blue-400/20 bg-blue-500/10 text-blue-300"
                  : "border-blue-200 bg-blue-50 text-blue-700"
              }`}
            >
              Personal AI Workspace
            </span>
          </div>

          <div>
            <h1
              className={`text-3xl font-bold tracking-tight sm:text-4xl ${
                isDark
                  ? "text-white"
                  : "text-slate-950"
              }`}
            >
              {greeting},{" "}
              <span className="text-blue-400">
                Onkar
              </span>
              ! 👋
            </h1>

            <p
              className={`mt-2 max-w-2xl text-sm leading-6 sm:text-base ${
                isDark
                  ? "text-slate-400"
                  : "text-slate-600"
              }`}
            >
              What would you like to work on today?
              Pick a quick action or start typing below.
            </p>
          </div>
        </div>

        <div
          data-workspace-quick-actions="6"
          className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
        >
          {QUICK_ACTIONS.map(
            (action) => {
              const Icon =
                action.icon;

              return (
                <button
                  key={action.id}
                  type="button"
                  onClick={() =>
                    chooseAction(action)
                  }
                  className={`group min-h-32 rounded-2xl border p-4 text-left transition duration-200 hover:-translate-y-0.5 ${
                    isDark
                      ? "border-white/10 bg-white/[0.035] hover:border-blue-400/30 hover:bg-blue-500/[0.08]"
                      : "border-slate-200 bg-white hover:border-blue-300 hover:bg-blue-50/60"
                  }`}
                  aria-label={`Quick action: ${action.label}`}
                  title={action.description}
                >
                  <span
                    className={`mb-4 flex h-10 w-10 items-center justify-center rounded-xl border transition ${
                      isDark
                        ? "border-white/10 bg-slate-900/80 text-blue-300 group-hover:border-blue-400/30"
                        : "border-slate-200 bg-slate-50 text-blue-700 group-hover:border-blue-300"
                    }`}
                  >
                    <Icon
                      aria-hidden="true"
                      size={18}
                    />
                  </span>

                  <span
                    className={`block text-sm font-semibold ${
                      isDark
                        ? "text-slate-100"
                        : "text-slate-900"
                    }`}
                  >
                    {action.label}
                  </span>

                  <span
                    className={`mt-1 block text-[11px] leading-4 ${
                      isDark
                        ? "text-slate-500"
                        : "text-slate-500"
                    }`}
                  >
                    {action.description}
                  </span>
                </button>
              );
            }
          )}
        </div>

        <div
          data-workspace-bottom-cards="3"
          className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-3"
        >
          <button
            type="button"
            onClick={onOpenKnowledge}
            disabled={!activeChatId}
            className={`group rounded-2xl border p-4 text-left transition ${
              !activeChatId
                ? "cursor-not-allowed opacity-55"
                : "hover:-translate-y-0.5"
            } ${
              isDark
                ? "border-white/10 bg-white/[0.03] hover:border-blue-400/25 hover:bg-blue-500/[0.06]"
                : "border-slate-200 bg-white hover:border-blue-300 hover:bg-blue-50/50"
            }`}
          >
            <div className="flex items-start gap-3">
              <span
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                  isDark
                    ? "bg-blue-500/10 text-blue-300"
                    : "bg-blue-100 text-blue-700"
                }`}
              >
                <FiDatabase
                  aria-hidden="true"
                  size={18}
                />
              </span>

              <div className="min-w-0">
                <p className="text-sm font-semibold">
                  Knowledge Base
                </p>

                <p className="mt-1 text-[11px] leading-4 text-slate-500">
                  {activeChatId
                    ? "Open the existing PDF and RAG tools for this chat."
                    : "Open a saved chat before using document tools."}
                </p>
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={onOpenSidebar}
            className={`group rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 ${
              isDark
                ? "border-white/10 bg-white/[0.03] hover:border-amber-400/25 hover:bg-amber-500/[0.06]"
                : "border-slate-200 bg-white hover:border-amber-300 hover:bg-amber-50/50"
            }`}
          >
            <div className="flex items-start gap-3">
              <span
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                  isDark
                    ? "bg-amber-500/10 text-amber-300"
                    : "bg-amber-100 text-amber-700"
                }`}
              >
                <FiBookmark
                  aria-hidden="true"
                  size={18}
                />
              </span>

              <div className="min-w-0">
                <p className="text-sm font-semibold">
                  Recent Bookmarks
                </p>

                <p className="mt-1 text-[11px] leading-4 text-slate-500">
                  Open the existing bookmarks panel from the left sidebar.
                </p>
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={onOpenBranches}
            disabled={
              !activeChatId ||
              branchCount <= 0
            }
            className={`group rounded-2xl border p-4 text-left transition ${
              !activeChatId ||
              branchCount <= 0
                ? "cursor-not-allowed opacity-55"
                : "hover:-translate-y-0.5"
            } ${
              isDark
                ? "border-white/10 bg-white/[0.03] hover:border-emerald-400/25 hover:bg-emerald-500/[0.06]"
                : "border-slate-200 bg-white hover:border-emerald-300 hover:bg-emerald-50/50"
            }`}
          >
            <div className="flex items-start gap-3">
              <span
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                  isDark
                    ? "bg-emerald-500/10 text-emerald-300"
                    : "bg-emerald-100 text-emerald-700"
                }`}
              >
                <FiGitBranch
                  aria-hidden="true"
                  size={18}
                />
              </span>

              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold">
                    Chat Branches
                  </p>

                  {branchCount > 0 && (
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        isDark
                          ? "bg-emerald-500/10 text-emerald-300"
                          : "bg-emerald-100 text-emerald-700"
                      }`}
                    >
                      {branchCount}
                    </span>
                  )}
                </div>

                <p className="mt-1 text-[11px] leading-4 text-slate-500">
                  {branchCount > 0
                    ? "Open the existing Branch Explorer for this conversation."
                    : "Create a branch from a user message to enable this shortcut."}
                </p>
              </div>
            </div>
          </button>
        </div>
      </div>
    </section>
  );
}


export default WorkspaceWelcome;
