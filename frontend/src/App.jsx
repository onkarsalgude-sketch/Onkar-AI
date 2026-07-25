import { useEffect, useState } from "react";

import Sidebar from "./components/Sidebar/Sidebar";
import ChatWindow from "./components/Chat/ChatWindow";
import WorkspaceRightRail from "./components/Workspace/WorkspaceRightRail";

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
messageSearchTarget,
documentRefreshKey,

messageActionLoadingId,
editMessage,
deleteMessage,
regenerateMessage,
createConversationBranch,
saveMessageBookmark,
removeMessageBookmark,

selectChat,
refreshAfterBranchMerge,
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

    agents,
    agentsLoading,
    agentsAvailable,
    selectedAgentId,
    changeSelectedAgent,

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
      data-workspace-shell="v2.39"
      className={`flex h-screen overflow-hidden md:gap-3 md:p-3 ${
        theme === "dark"
          ? "bg-[#060914] text-white"
          : "bg-slate-200 text-slate-900"
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

      <div
        data-workspace-main="primary"
        className={`min-w-0 flex-1 overflow-hidden md:rounded-[28px] md:border md:shadow-2xl ${
          theme === "dark"
            ? "md:border-white/10 md:bg-[#0f172a] md:shadow-black/30"
            : "md:border-slate-200 md:bg-white md:shadow-slate-300/50"
        }`}
      >
       <ChatWindow
  activeChatId={activeChatId}
  chats={chats}
  selectChat={selectChat}
  onMergeCompleted={
    refreshAfterBranchMerge
  }
  documentRefreshKey={
    documentRefreshKey
  }
  messages={messages}
  messageSearchTarget={
    messageSearchTarget
  }
  input={input}
  setInput={setInput}
  sendMessage={sendMessage}
  loading={loading}
  agents={agents}
  agentsLoading={agentsLoading}
  agentsAvailable={agentsAvailable}
  selectedAgentId={
    selectedAgentId
  }
  onAgentChange={
    changeSelectedAgent
  }
  uploadFile={uploadFile}
  pendingFiles={pendingFiles}
  removePendingFileAt={
    removePendingFileAt
  }
  clearAllPendingFiles={
    clearAllPendingFiles
  }
  uploadProgress={uploadProgress}
  uploadSummary={uploadSummary}
  dismissUploadSummary={
    dismissUploadSummary
  }
  regenerateResponse={
    regenerateResponse
  }

  onEditMessage={editMessage}
  onDeleteMessage={deleteMessage}
  onRegenerateMessage={
    regenerateMessage
  }
  onCreateConversationBranch={
  createConversationBranch
}
  onSaveMessageBookmark={
  saveMessageBookmark
}
onRemoveMessageBookmark={
  removeMessageBookmark
}
  messageActionLoadingId={
    messageActionLoadingId
  }

  chatError={chatError}
  retryLastRequest={
    retryLastRequest
  }
  dismissChatError={
    dismissChatError
  }
  onOpenSidebar={() =>
    setSidebarOpen(true)
  }
  theme={theme}
/>
      </div>

      <WorkspaceRightRail
        agents={agents}
        agentsLoading={agentsLoading}
        agentsAvailable={agentsAvailable}
        selectedAgentId={selectedAgentId}
        onAgentChange={changeSelectedAgent}
        theme={theme}
      />
    </div>
  );
}


export default App;
