function SourcesCard({
  sources = [],
  theme = "dark",
}) {
  const isDark = theme === "dark";

  if (!Array.isArray(sources) || sources.length === 0) {
    return null;
  }

  const normalizedSources = sources.map((source) => {
    if (typeof source === "string") {
      return {
        type: "internet",
        title: source,
        url: source,
      };
    }

    return source || {};
  });

  // Duplicate sources काढणे
  const uniqueSources = normalizedSources.filter(
    (source, index, allSources) => {
      const sourceKey =
        source.url ||
        `${source.filename || source.title}-${source.page || ""}`;

      return (
        index ===
        allSources.findIndex((item) => {
          const itemKey =
            item.url ||
            `${item.filename || item.title}-${item.page || ""}`;

          return itemKey === sourceKey;
        })
      );
    }
  );

  return (
    <div
      className={`mt-5 rounded-xl border p-4 ${
        isDark
          ? "border-slate-700 bg-slate-900"
          : "border-slate-200 bg-slate-50"
      }`}
    >
      <h3
        className={`mb-3 text-sm font-semibold ${
          isDark
            ? "text-slate-300"
            : "text-slate-700"
        }`}
      >
        📚 Sources
      </h3>

      <div className="space-y-2">
        {uniqueSources.map((source, index) => {
          const isPDF =
            source.type === "pdf" ||
            Boolean(source.filename);

          if (isPDF) {
            return (
              <div
                key={`${source.filename}-${source.page}-${index}`}
                className={`flex items-center gap-3 rounded-lg border p-3 ${
                  isDark
                    ? "border-slate-700 bg-slate-800"
                    : "border-slate-200 bg-white"
                }`}
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-red-500/15 text-xl">
                  📄
                </div>

                <div className="min-w-0">
                  <p
                    className={`truncate text-sm font-medium ${
                      isDark
                        ? "text-slate-100"
                        : "text-slate-900"
                    }`}
                    title={
                      source.filename ||
                      source.title
                    }
                  >
                    {source.filename ||
                      source.title ||
                      "Uploaded PDF"}
                  </p>

                  {source.page && (
                    <p className="mt-1 text-xs text-slate-500">
                      Page {source.page}
                    </p>
                  )}
                </div>
              </div>
            );
          }

          if (source.url) {
            return (
              <a
                key={`${source.url}-${index}`}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className={`block rounded-lg border p-3 transition ${
                  isDark
                    ? "border-slate-700 bg-slate-800 hover:bg-slate-700"
                    : "border-slate-200 bg-white hover:bg-slate-100"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-500/15 text-xl">
                    🌐
                  </div>

                  <div className="min-w-0">
                    <p
                      className={`truncate text-sm font-medium ${
                        isDark
                          ? "text-slate-100"
                          : "text-slate-900"
                      }`}
                    >
                      {source.title ||
                        source.domain ||
                        "Web source"}
                    </p>

                    <p className="mt-1 truncate text-xs text-slate-500">
                      {source.domain || source.url}
                    </p>
                  </div>
                </div>
              </a>
            );
          }

          return (
            <div
              key={index}
              className={`rounded-lg border p-3 text-sm ${
                isDark
                  ? "border-slate-700 bg-slate-800 text-slate-300"
                  : "border-slate-200 bg-white text-slate-700"
              }`}
            >
              🔗 {source.title || `Source ${index + 1}`}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default SourcesCard;