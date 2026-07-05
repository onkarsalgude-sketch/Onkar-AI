import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";

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
  newChat,
  sendMessage,
  chats,
  activeChatId,
  selectChat,
  renameCurrentChat,
  deleteCurrentChat,
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
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setUploading(true);

    try {
      const res = await uploadDocument(formData);

      await loadDocuments();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `✅ PDF uploaded successfully!\n\n📄 ${file.name}\nChunks: ${res.data.chunks}`,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "❌ PDF upload failed. Please upload only PDF.",
        },
      ]);
    }

    setUploading(false);
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
        loading={loading}
        uploadPDF={uploadPDF}
      />
    </div>
  );
}

export default App;