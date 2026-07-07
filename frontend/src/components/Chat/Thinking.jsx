function Thinking() {
  return (
    <div className="flex justify-start mb-5">
      <div className="bg-slate-800 rounded-2xl rounded-bl-md px-5 py-4">

        <div className="flex items-center gap-3 mb-2">
          <span className="text-lg">🤖</span>

          <span className="font-medium">
            Onkar AI
          </span>
        </div>

        <div className="flex gap-2">
          <span className="w-2 h-2 rounded-full bg-white animate-bounce"></span>

          <span
            className="w-2 h-2 rounded-full bg-white animate-bounce"
            style={{ animationDelay: "0.2s" }}
          ></span>

          <span
            className="w-2 h-2 rounded-full bg-white animate-bounce"
            style={{ animationDelay: "0.4s" }}
          ></span>
        </div>

      </div>
    </div>
  );
}

export default Thinking;