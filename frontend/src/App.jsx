import Sidebar from "./components/Sidebar/Sidebar";
import ChatWindow from "./components/Chat/ChatWindow";

import useChat from "./hooks/useChat";

import {
  uploadDocument,
  getDocuments,
  deleteDocumentApi,
} from "./services/documentService";

import { useEffect, useState } from "react";

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

  useEffect(() => {
    loadDocuments();
  }, []);

  async function loadDocuments() {
    try {
      const res = await getDocuments();
      setDocuments(res.data.documents);
    } catch (err) {
      console.log(err);
    }
  }

  async function uploadPDF(e) {
  const file = e.target.files?.[0];

  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  const fileSize =
    file.size < 1024 * 1024
      ? `${(file.size / 1024).toFixed(1)} KB`
      : `${(file.size / (1024 * 1024)).toFixed(1)} MB`;

  // User message मध्ये PDF preview card
  setMessages((prev) => [
    ...prev,
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
    const res = await uploadDocument(formData);

    await loadDocuments();

    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: `✅ **${file.name}** uploaded and indexed successfully.\n\nChunks: ${
          res.data?.chunks ?? 0
        }`,
        sources: [],
      },
    ]);
  } catch (error) {
    console.error("PDF upload error:", error);

    setMessages((prev) => [
      ...prev,
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
    e.target.value = "";
  }
}
  async function handleUploadFile(e) {
  const file = e.target.files?.[0];

  if (!file) return;

  if (file.type === "application/pdf") {
    await uploadPDF(e);
    return;
  }

  if (file.type.startsWith("image/")) {
    await uploadImageFile(e);
    return;
  }

  alert("Only PDF and image files are supported.");
}

  async function deleteDocument(filename) {
    try {
      await deleteDocumentApi(filename);
      await loadDocuments();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `🗑️ ${filename} deleted successfully.`,
        },
      ]);
    } catch (err) {
      console.log(err);
    }
  }

  return (
    <div className="flex">
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
/>

      <ChatWindow
  messages={messages}
  input={input}
  setInput={setInput}
  sendMessage={sendMessage}
  loading={loading || uploading}
  uploadFile={handleUploadFile}
  regenerateResponse={regenerateResponse}
/>
    </div>
  );
}

export default App;