import Message from "./Message";
import MessageInput from "./MessageInput";

function ChatWindow({ messages, input, setInput, sendMessage, loading }) {
  return (
    <div className="flex-1 h-screen bg-slate-900 text-white flex flex-col">
      <div className="p-5 border-b border-slate-800">
        <h2 className="text-2xl font-bold">Onkar Personal AI</h2>
        <p className="text-slate-400">Local AI + PDF RAG Assistant</p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {messages.map((msg, index) => (
          <Message key={index} role={msg.role} content={msg.content} />
        ))}

        {loading && <Message role="assistant" content="Thinking..." />}
      </div>

      <MessageInput
        input={input}
        setInput={setInput}
        sendMessage={sendMessage}
        loading={loading}
      />
    </div>
  );
}

export default ChatWindow;