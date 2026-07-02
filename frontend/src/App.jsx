import { useState } from "react";
import axios from "axios";

import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";

import "./App.css";

function App() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "👋 Hi Onkar!\n\nमी तुझा Personal AI Assistant आहे.\nPDF upload कर किंवा काहीही विचार.",
    },
  ]);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  function newChat() {
    setMessages([
      {
        role: "assistant",
        content: "👋 New chat started. PDF upload कर किंवा काहीही विचार.",
      },
    ]);
  }

  async function uploadPDF(e) {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setUploading(true);

    try {
      const res = await axios.post(
        "http://127.0.0.1:8000/documents/upload",
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );

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

  async function sendMessage() {
    if (!input.trim()) return;

    const text = input;

    setMessages((prev) => [...prev, { role: "user", content: text }]);

    setInput("");
    setLoading(true);

    try {
      const res = await axios.post("http://127.0.0.1:8000/chat", {
        message: text,
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.data.reply,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "❌ Backend connection failed.",
        },
      ]);
    }

    setLoading(false);
  }

  return (
    <div className="flex">
      <Sidebar uploadPDF={uploadPDF} uploading={uploading} newChat={newChat} />

      <ChatWindow
        messages={messages}
        input={input}
        setInput={setInput}
        sendMessage={sendMessage}
        loading={loading}
      />
    </div>
  );
}

export default App;