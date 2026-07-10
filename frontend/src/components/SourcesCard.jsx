function SourcesCard({ sources = [] }) {
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

    return source;
  });

  const uniqueSources = normalizedSources.filter(
    (source, index, array) => {
      const currentKey =
        source.url ||
        `${source.filename || source.title}-${source.page || ""}`;

      return (
        index ===
        array.findIndex((item) => {
          const itemKey =
            item.url ||
            `${item.filename || item.title}-${item.page || ""}`;

          return itemKey === currentKey;
        })
      );
    }
  );

  return (
    <div className="mt-4 border-t border-slate-700 pt-4">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
        Sources
      </p>

      <div className="flex flex-wrap gap-2">
        {uniqueSources.map((source, index) => {
          const isPdf =
            source.type === "pdf" || Boolean(source.filename);

          if (isPdf) {
            return (
              <div
                key={`${source.filename}-${source.page}-${index}`}
                className="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200"
              >
                <span>📄</span>

                <div>
                  <p className="max-w-56 truncate font-medium">
                    {source.filename ||
                      source.title ||
                      "Uploaded PDF"}
                  </p>

                  {source.page && (
                    <p className="text-xs text-slate-400">
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
                className="flex max-w-72 items-center gap-2 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-blue-300 transition hover:border-blue-500 hover:bg-slate-800"
              >
                <span>🌐</span>

                <span className="truncate">
                  {source.title || source.url}
                </span>
              </a>
            );
          }

          return (
            <div
              key={index}
              className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-300"
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