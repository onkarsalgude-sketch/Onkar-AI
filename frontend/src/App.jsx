import { useEffect, useState } from "react";

import Sidebar from "./components/Sidebar/Sidebar";
import ChatWindow from "./components/Chat/ChatWindow";

import useChat from "./hooks/useChat";

import {
  uploadDocument,
  getDocuments,
  deleteDocumentApi,
} from "./services/documentService";

import "./App.css";

function App() {
  const {
    messages,
    setMessages,
    input,
    setInput,
    loading,
    uploadFile: uploadImageFile,
    newChat,
    sendMessage,

    chats,
    activeChatId,
    selectChat,
    renameCurrentChat,
    deleteCurrentChat,
    regenerateResponse,
  } = useChat();

  const [uploading, setUploading] = useState(false);
  const [documents, setDocuments] = useState([]);

  // Mobile sidebar
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    loadDocuments();
  }, []);

  async function loadDocuments() {
    try {
      const response = await getDocuments();
      setDocuments(response.data.documents || []);
    } catch (error) {
      console.error("Load documents error:", error);
    }
  }

  async function uploadPDF(event) {
    const file = event.target.files?.[0];

    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    const fileSize =
      file.size < 1024 * 1024
        ? `${(file.size / 1024).toFixed(1)} KB`
        : `${(file.size / (1024 * 1024)).toFixed(1)} MB`;

    setMessages((previousMessages) => [
      ...previousMessages,
      {
        role: "user",
        content: "",
        fileType: "pdf",
        fileName: file.name,
        fileSize,
        sources: [],
      },
    ]);

    setUploading(true);

    try {
      const response = await uploadDocument(formData);

      await loadDocuments();

      setMessages((previousMessages) => [
        ...previousMessages,
        {
          role: "assistant",
          content: `✅ **${file.name}** uploaded and indexed successfully.\n\nChunks: ${
            response.data?.chunks ?? 0
          }`,
          sources: [],
        },
      ]);
    } catch (error) {
      console.error("PDF upload error:", error);

      setMessages((previousMessages) => [
        ...previousMessages,
        {
          role: "assistant",
          content:
            error.response?.data?.detail ||
            "❌ PDF upload failed. Please upload a valid PDF.",
          sources: [],
        },
      ]);
    } finally {
      setUploading(false);

      if (event.target) {
        event.target.value = "";
      }
    }
  }

  async function handleUploadFile(event) {
    const file = event.target.files?.[0];

    if (!file) return;

    if (file.type === "application/pdf") {
      await uploadPDF(event);
      return;
    }

    if (file.type.startsWith("image/")) {
      await uploadImageFile(event);
      return;
    }

    alert("Only PDF and image files are supported.");
  }

  async function deleteDocument(filename) {
    try {
      await deleteDocumentApi(filename);
      await loadDocuments();

      setMessages((previousMessages) => [
        ...previousMessages,
        {
          role: "assistant",
          content: `🗑️ **${filename}** deleted successfully.`,
          sources: [],
        },
      ]);
    } catch (error) {
      console.error("Delete document error:", error);

      setMessages((previousMessages) => [
        ...previousMessages,
        {
          role: "assistant",
          content: `❌ Failed to delete **${filename}**.`,
          sources: [],
        },
      ]);
    }
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar
        uploadPDF={uploadPDF}
        uploading={uploading}
        newChat={newChat}
        documents={documents}
        deleteDocument={deleteDocument}
        chats={chats}
        activeChatId={activeChatId}
        selectChat={selectChat}
        renameCurrentChat={renameCurrentChat}
        deleteCurrentChat={deleteCurrentChat}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <ChatWindow
        messages={messages}
        input={input}
        setInput={setInput}
        sendMessage={sendMessage}
        loading={loading || uploading}
        uploadFile={handleUploadFile}
        regenerateResponse={regenerateResponse}
        onOpenSidebar={() => setSidebarOpen(true)}
      />
    </div>
  );
}

export default App;