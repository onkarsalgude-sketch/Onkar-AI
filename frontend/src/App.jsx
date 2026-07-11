import { useEffect, useState } from "react";

import Sidebar from "./components/Sidebar/Sidebar";
import ChatWindow from "./components/Chat/ChatWindow";

import useChat from "./hooks/useChat";

import "./App.css";

function App() {
  const {
    messages,
    input,
    setInput,
    loading,

    pendingFile,
    removePendingFile,

    uploadFile,
    newChat,
    sendMessage,

    chats,
    activeChatId,
    selectChat,
    renameCurrentChat,
    deleteCurrentChat,
    regenerateResponse,
    toggleChatPin,
  } = useChat();

  const [sidebarOpen, setSidebarOpen] =
    useState(false);

  const [theme, setTheme] = useState(() => {
    const savedTheme =
      localStorage.getItem("onkar-ai-theme");

    if (
      savedTheme === "light" ||
      savedTheme === "dark"
    ) {
      return savedTheme;
    }

    return "dark";
  });

  useEffect(() => {
    localStorage.setItem(
      "onkar-ai-theme",
      theme
    );

    document.documentElement.dataset.theme =
      theme;

    document.documentElement.style.colorScheme =
      theme;
  }, [theme]);

  return (
    <div
      className={`flex min-h-screen ${
        theme === "dark"
          ? "bg-[#0f172a] text-white"
          : "bg-slate-100 text-slate-900"
      }`}
    >
      <Sidebar
  messages={messages}
  newChat={newChat}
  chats={chats}
  activeChatId={activeChatId}
  selectChat={selectChat}
  renameCurrentChat={renameCurrentChat}
  deleteCurrentChat={deleteCurrentChat}
  toggleChatPin={toggleChatPin}
  isOpen={sidebarOpen}
  onClose={() => setSidebarOpen(false)}
  theme={theme}
  onThemeChange={setTheme}
/>

      <ChatWindow
        messages={messages}
        input={input}
        setInput={setInput}
        sendMessage={sendMessage}
        loading={loading}
        uploadFile={uploadFile}
        pendingFile={pendingFile}
        removePendingFile={removePendingFile}
        regenerateResponse={regenerateResponse}
        onOpenSidebar={() =>
          setSidebarOpen(true)
        }
        theme={theme}
      />
    </div>
  );
}

export default App;