import { useEffect, useRef, useState } from "react";

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
  onOpenSidebar,
}) {
  const [isDragging, setIsDragging] = useState(false);

  const dragCounter = useRef(0);
  const messagesEndRef = useRef(null);

  // नवीन message किंवा streaming response आल्यावर खाली scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages, loading]);

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
      className="relative flex h-screen min-w-0 flex-1 flex-col bg-[#0f172a] text-white"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag and drop overlay */}
      {isDragging && (
        <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border-2 border-dashed border-blue-400 bg-slate-900 px-6 py-10 text-center shadow-2xl sm:px-12">
            <div className="mb-4 text-5xl">📎</div>

            <h3 className="text-xl font-semibold">
              Drop your file here
            </h3>

            <p className="mt-2 text-sm text-slate-400">
              PDF and image files are supported
            </p>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="flex h-20 shrink-0 items-center justify-between border-b border-slate-800 px-3 sm:px-5 md:px-8">
        <div className="flex min-w-0 items-center gap-3">
          {/* Mobile hamburger button */}
          <button
            type="button"
            onClick={onOpenSidebar}
            className="shrink-0 rounded-lg bg-slate-800 p-2 text-xl transition hover:bg-slate-700 md:hidden"
            aria-label="Open sidebar"
          >
            ☰
          </button>

          <div className="min-w-0">
            <h2 className="truncate text-base font-bold sm:text-lg md:text-xl">
              Onkar Personal AI
            </h2>

            <p className="hidden truncate text-sm text-slate-400 sm:block">
              PDF RAG • Vision • Voice • Internet Search
            </p>
          </div>
        </div>

        <div className="ml-2 shrink-0 rounded-full bg-slate-800 px-3 py-2 text-xs text-slate-300 md:px-4 md:text-sm">
          Online
        </div>
      </header>

      {/* Messages */}
      <section className="flex-1 overflow-y-auto px-3 py-4 sm:px-5 md:px-8 md:py-6">
        <div className="mx-auto max-w-4xl">
          {messages.length <= 1 && (
            <WelcomeScreen setInput={setInput} />
          )}

          {messages.map((message, index) => (
            <Message
              key={index}
              role={message.role}
              content={message.content}
              imageUrl={message.imageUrl}
              fileName={message.fileName}
              fileType={message.fileType}
              fileSize={message.fileSize}
              sources={message.sources || []}
              isLast={index === messages.length - 1}
              regenerateResponse={regenerateResponse}
            />
          ))}

          {loading && <Thinking />}

          <div ref={messagesEndRef} />
        </div>
      </section>

      {/* Message input */}
      <div className="shrink-0 px-3 pb-4 sm:px-5 md:px-8 md:pb-6">
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