function SourcesCard({ sources = [] }) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-5 rounded-xl border border-slate-700 bg-slate-900 p-4">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">
        🌐 Sources
      </h3>

      <div className="space-y-2">
        {sources.map((source, index) => (
          <a
            key={index}
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block rounded-lg p-3 hover:bg-slate-800 transition"
          >
            <div className="font-medium text-white">
              {source.title}
            </div>

            <div className="text-xs text-slate-400">
              {source.domain}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

export default SourcesCard;