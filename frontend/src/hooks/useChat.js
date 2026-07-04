import { useState, useEffect } from "react";
import { sendChat, getHistory, clearHistory } from "../services/chatService";

export default function useChat() {
  const welcomeMessage = {
    role: "assistant",
    content:
      "👋 Hi Onkar!\n\nमी तुझा Personal AI Assistant आहे.\nPDF upload कर किंवा काहीही विचार.",
  };

  const [messages, setMessages] = useState([welcomeMessage]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadHistory();
  }, []);

  async function loadHistory() {
    try {
      const res = await getHistory();

      if (res.data.messages.length > 0) {
        setMessages(
          res.data.messages.map((msg) => ({
            role: msg.role,
            content: msg.content,
          }))
        );
      }
    } catch (err) {
      console.log(err);
    }
  }

  async function newChat() {
  try {
    await clearHistory();
  } catch (err) {
    console.log("Backend not connected, clearing frontend only");
  }

  setMessages([welcomeMessage]);
  setInput("");
}

  async function sendMessage() {
    if (!input.trim()) return;

    const text = input;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const res = await sendChat(text);

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

  return {
    messages,
    setMessages,
    input,
    setInput,
    loading,
    newChat,
    sendMessage,
    loadHistory,
  };
}