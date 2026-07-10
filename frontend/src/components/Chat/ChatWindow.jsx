import Message from "./Message";
import MessageInput from "./MessageInput";
import Thinking from "./Thinking";

import DropZone from "../Upload/DropZone";
import WelcomeScreen from "../Common/WelcomeScreen";
import ImageUpload from "../Upload/ImageUpload";

function ChatWindow({
  messages,
  input,
  setInput,
  sendMessage,
  loading,
  uploadPDF,
  uploadFile,
  regenerateResponse,
})  {
  return (
    <main className="flex-1 h-screen bg-[#0f172a] text-white flex flex-col">
      <header className="h-20 px-8 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Onkar Personal AI</h2>
          <p className="text-sm text-slate-400">PDF RAG • Voice • Internet Search • Local LLM</p>
        </div>

        <div className="text-sm bg-slate-800 px-4 py-2 rounded-full text-slate-300">
          Online
        </div>
      </header>

      <section className="flex-1 overflow-y-auto px-8 py-6">
        <div className="max-w-4xl mx-auto">
          <div className="mb-6">
  {<DropZone uploadPDF={uploadPDF} />}
  {<ImageUpload />}
</div>
{messages.length <= 1 && <WelcomeScreen setInput={setInput} />}
  {messages.map((msg, index) => (
  <Message
  key={index}
  role={msg.role}
  content={msg.content}
  imageUrl={msg.imageUrl}
  fileName={msg.fileName}
  sources={msg.sources || []}
  isLast={index === messages.length - 1}
  regenerateResponse={regenerateResponse}
/>
))}

         {loading && <Thinking />}
        </div>
      </section>

      <div className="px-8 pb-6">
        <div className="max-w-4xl mx-auto">
         <MessageInput
  input={input}
  setInput={setInput}
  sendMessage={sendMessage}
  loading={loading}
  uploadFile={uploadFile}
/>
        </div>
      </div>
    </main>
  );
}

export default ChatWindow;