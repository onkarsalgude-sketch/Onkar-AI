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

    chatError,
retryLastRequest,
dismissChatError,

    pendingFiles,
    removePendingFileAt,
    clearAllPendingFiles,
    uploadProgress,
    uploadSummary,
    dismissUploadSummary,
    uploadFile,

    newChat,
    sendMessage,

    chats,
    activeChatId,
    documentRefreshKey,
    selectChat,
    renameCurrentChat,
deleteCurrentChat,
restoreChatBackup,
restoreFullChatBackup,
regenerateResponse,
    toggleChatPin,

    folders,
    createChatFolder,
    renameChatFolder,
    deleteChatFolder,
    moveChatToFolder,

    models,
    defaultModel,
    selectedModel,
    changeSelectedModel,
  } = useChat();


  const [sidebarOpen, setSidebarOpen] =
    useState(false);


  const [theme, setTheme] = useState(() => {
    const savedTheme =
      localStorage.getItem(
        "onkar-ai-theme"
      );

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
        documentRefreshKey={documentRefreshKey}
        selectChat={selectChat}
        renameCurrentChat={
          renameCurrentChat
        }
       deleteCurrentChat={
  deleteCurrentChat
}
restoreChatBackup={
  restoreChatBackup
}
restoreFullChatBackup={
  restoreFullChatBackup
}
toggleChatPin={toggleChatPin}

        folders={folders}
        createChatFolder={
          createChatFolder
        }
        renameChatFolder={
          renameChatFolder
        }
        deleteChatFolder={
          deleteChatFolder
        }
        moveChatToFolder={
          moveChatToFolder
        }

        models={models}
        defaultModel={defaultModel}
        selectedModel={selectedModel}
        onModelChange={
          changeSelectedModel
        }

        isOpen={sidebarOpen}
        onClose={() =>
          setSidebarOpen(false)
        }
        theme={theme}
        onThemeChange={setTheme}
      />

     <ChatWindow
     activeChatId={activeChatId}
  documentRefreshKey={documentRefreshKey}
  messages={messages}
  input={input}
  setInput={setInput}
  sendMessage={sendMessage}
  loading={loading}
  uploadFile={uploadFile}
  pendingFiles={pendingFiles}
  removePendingFileAt={removePendingFileAt}
  clearAllPendingFiles={clearAllPendingFiles}
  uploadProgress={uploadProgress}
  uploadSummary={uploadSummary}
  dismissUploadSummary={dismissUploadSummary}
  regenerateResponse={regenerateResponse}
  chatError={chatError}
  retryLastRequest={retryLastRequest}
  dismissChatError={dismissChatError}
  onOpenSidebar={() =>
    setSidebarOpen(true)
  }
  theme={theme}
/>
    </div>
  );
}


export default App;
