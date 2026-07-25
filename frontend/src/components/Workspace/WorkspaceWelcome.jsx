import {
  useMemo,
} from "react";
import {
  FiBookOpen,
  FiCode,
  FiCompass,
  FiEdit3,
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
      </div>
    </section>
  );
}


export default WorkspaceWelcome;
