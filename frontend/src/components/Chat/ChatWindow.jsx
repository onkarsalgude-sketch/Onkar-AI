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
  pendingFile,
  removePendingFile,
  regenerateResponse,
  onOpenSidebar,
  theme = "dark",
}) {
  const [isDragging, setIsDragging] = useState(false);

  const dragCounter = useRef(0);
  const messagesEndRef = useRef(null);

  const isDark = theme === "dark";

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
      className={`relative flex h-screen min-w-0 flex-1 flex-col transition-colors duration-300 ${
        isDark
          ? "bg-[#0f172a] text-white"
          : "bg-slate-100 text-slate-900"
      }`}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div
          className={`pointer-events-none absolute inset-0 z-50 flex items-center justify-center px-4 backdrop-blur-sm ${
            isDark
              ? "bg-slate-950/80"
              : "bg-slate-200/80"
          }`}
        >
          <div
            className={`w-full max-w-md rounded-2xl border-2 border-dashed border-blue-500 px-6 py-10 text-center shadow-2xl sm:px-12 ${
              isDark
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-900"
            }`}
          >
            <div className="mb-4 text-5xl">📎</div>

            <h3 className="text-xl font-semibold">
              Drop your file here
            </h3>

            <p className="mt-2 text-sm text-slate-500">
              PDF and image files are supported
            </p>
          </div>
        </div>
      )}

      <header
        className={`flex h-20 shrink-0 items-center justify-between border-b px-3 sm:px-5 md:px-8 ${
          isDark
            ? "border-slate-800 bg-[#0f172a]"
            : "border-slate-200 bg-white"
        }`}
      >
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onOpenSidebar}
            className={`shrink-0 rounded-lg p-2 text-xl md:hidden ${
              isDark
                ? "bg-slate-800 hover:bg-slate-700"
                : "bg-slate-200 hover:bg-slate-300"
            }`}
            aria-label="Open sidebar"
          >
            ☰
          </button>

          <div className="min-w-0">
            <h2 className="truncate text-base font-bold sm:text-lg md:text-xl">
              Onkar Personal AI
            </h2>

            <p className="hidden truncate text-sm text-slate-500 sm:block">
              PDF RAG • Vision • Voice • Internet Search
            </p>
          </div>
        </div>

        <div
          className={`ml-2 shrink-0 rounded-full px-3 py-2 text-xs md:px-4 md:text-sm ${
            isDark
              ? "bg-slate-800 text-slate-300"
              : "bg-emerald-100 text-emerald-700"
          }`}
        >
          ● Online
        </div>
      </header>

      <section className="flex-1 overflow-y-auto px-3 py-4 sm:px-5 md:px-8 md:py-6">
        <div className="mx-auto max-w-4xl">
          {messages.length <= 1 && (
            <WelcomeScreen
              setInput={setInput}
              theme={theme}
            />
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
              theme={theme}
            />
          ))}

          {loading && <Thinking theme={theme} />}

          <div ref={messagesEndRef} />
        </div>
      </section>

      <div
        className={`shrink-0 px-3 pb-4 sm:px-5 md:px-8 md:pb-6 ${
          isDark ? "bg-[#0f172a]" : "bg-slate-100"
        }`}
      >
        <div className="mx-auto max-w-4xl">
          <MessageInput
            input={input}
            setInput={setInput}
            sendMessage={sendMessage}
            loading={loading}
            uploadFile={uploadFile}
            pendingFile={pendingFile}
            removePendingFile={removePendingFile}
            theme={theme}
          />
        </div>
      </div>
    </main>
  );
}

export default ChatWindow;