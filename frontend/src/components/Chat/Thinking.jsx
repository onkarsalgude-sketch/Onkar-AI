function Thinking() {
  return (
    <div className="flex justify-start mb-5 animate-fadeIn">
      <div className="max-w-sm bg-slate-800 rounded-2xl rounded-bl-md px-5 py-4 shadow-lg border border-slate-700">

        {/* Header */}
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center text-lg shadow-md">
            🤖
          </div>

          <div>
            <h3 className="font-semibold text-white">
              Onkar AI
            </h3>

            <p className="text-xs text-slate-400">
              Thinking...
            </p>
          </div>
        </div>

        {/* Animated Dots */}
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-400 animate-bounce"></span>

          <span
            className="w-2.5 h-2.5 rounded-full bg-blue-400 animate-bounce"
            style={{ animationDelay: "0.2s" }}
          ></span>

          <span
            className="w-2.5 h-2.5 rounded-full bg-blue-400 animate-bounce"
            style={{ animationDelay: "0.4s" }}
          ></span>
        </div>

        {/* Status */}
        <p className="text-sm text-slate-400 mt-3 italic">
          Generating response...
        </p>

      </div>
    </div>
  );
}

export default Thinking;