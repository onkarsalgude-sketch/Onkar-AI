import { useRef, useState } from "react";

import Message from "./Message";
import MessageInput from "./MessageInput";
import Thinking from "./Thinking";
import WelcomeScreen from "../Common/WelcomeScreen";

function ChatWindow({
  messages,
  input,
  setInput,
  sendMessage,
  loading,
  uploadFile,
  regenerateResponse,
}) {
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  function handleDragEnter(event) {
    event.preventDefault();
    event.stopPropagation();

    dragCounter.current += 1;

    if (event.dataTransfer?.items?.length > 0) {
      setIsDragging(true);
    }
  }

  function handleDragOver(event) {
    event.preventDefault();
    event.stopPropagation();

    event.dataTransfer.dropEffect = "copy";
  }

  function handleDragLeave(event) {
    event.preventDefault();
    event.stopPropagation();

    dragCounter.current -= 1;

    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragging(false);
    }
  }

  async function handleDrop(event) {
    event.preventDefault();
    event.stopPropagation();

    dragCounter.current = 0;
    setIsDragging(false);

    if (loading) return;

    const files = event.dataTransfer?.files;

    if (!files || files.length === 0) return;

    const file = files[0];

    const isPDF = file.type === "application/pdf";
    const isImage = file.type.startsWith("image/");

    if (!isPDF && !isImage) {
      alert("Only PDF and image files are supported.");
      return;
    }

    await uploadFile({
      target: {
        files,
        value: "",
      },
    });
  }

  return (
    <main
      className="relative flex h-screen flex-1 flex-col bg-[#0f172a] text-white"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
          <div className="rounded-2xl border-2 border-dashed border-blue-400 bg-slate-900 px-12 py-10 text-center shadow-2xl">
            <div className="mb-4 text-5xl">📎</div>

            <h3 className="text-xl font-semibold text-white">
              Drop your file here
            </h3>

            <p className="mt-2 text-sm text-slate-400">
              PDF and image files are supported
            </p>
          </div>
        </div>
      )}

      <header className="flex h-20 items-center justify-between border-b border-slate-800 px-8">
        <div>
          <h2 className="text-xl font-bold">
            Onkar Personal AI
          </h2>

          <p className="text-sm text-slate-400">
            PDF RAG • Vision • Voice • Internet Search
          </p>
        </div>

        <div className="rounded-full bg-slate-800 px-4 py-2 text-sm text-slate-300">
          Online
        </div>
      </header>

      <section className="flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto max-w-4xl">
          {messages.length <= 1 && (
            <WelcomeScreen setInput={setInput} />
          )}

          {messages.map((msg, index) => (
            <Message
              key={index}
              role={msg.role}
              content={msg.content}
              imageUrl={msg.imageUrl}
              fileName={msg.fileName}
              fileType={msg.fileType}
              fileSize={msg.fileSize}
              sources={msg.sources || []}
              isLast={index === messages.length - 1}
              regenerateResponse={regenerateResponse}
            />
          ))}

          {loading && <Thinking />}
        </div>
      </section>

      <div className="px-8 pb-6">
        <div className="mx-auto max-w-4xl">
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