function WelcomeScreen({ setInput }) {
  const suggestions = [
    {
      icon: "📄",
      title: "Summarize PDF",
      prompt: "Summarize the uploaded PDF in simple points.",
    },
    {
      icon: "💻",
      title: "Explain Code",
      prompt: "Explain this code step by step.",
    },
    {
      icon: "🌐",
      title: "Search Internet",
      prompt: "Search the internet and explain the latest information about AI.",
    },
    {
      icon: "📚",
      title: "Resume Review",
      prompt: "Review my resume and suggest improvements.",
    },
  ];

  return (
    <div className="max-w-4xl mx-auto mt-10 text-center">
      <h1 className="text-4xl font-bold mb-3">🤖 Onkar AI</h1>

      <p className="text-slate-400 mb-8">
        How can I help you today?
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {suggestions.map((item, index) => (
          <button
            key={index}
            onClick={() => setInput(item.prompt)}
            className="bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-2xl p-5 text-left transition"
          >
            <div className="text-3xl mb-3">{item.icon}</div>
            <h3 className="font-bold text-lg">{item.title}</h3>
            <p className="text-slate-400 text-sm mt-1">{item.prompt}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

export default WelcomeScreen;