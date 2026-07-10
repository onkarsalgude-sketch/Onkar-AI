import { useState, useEffect } from "react";
import { streamChat, getChats } from "../services/chatService";
import useChats from "./useChats";
import { analyzeImage } from "../services/imageService";

const welcomeMessage = {
  role: "assistant",
  content: "Hello! How can I help you today?",
};

export default function useChat() {
  const [messages, setMessages] = useState([welcomeMessage]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const {
    chats,
    setChats,
    activeChatId,
    setActiveChatId,
    loadChats,
    selectChat,
    newChat,
    createNewChatIfNeeded,
    renameCurrentChat,
    deleteCurrentChat,
  } = useChats(setMessages, setInput);

  useEffect(() => {
    loadChats();
  }, []);

  async function sendMessage() {
    if (!input.trim()) return;

    const text = input;
    const currentChatId = await createNewChatIfNeeded();

    setMessages((prev) => [
      ...prev,
      { role: "user", content: text, sources: [] },
      { role: "assistant", content: "", sources: [] },
    ]);

    setInput("");
    setLoading(true);

    try {
      await streamChat(text, currentChatId, (chunk) => {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1].content += chunk;
          return updated;
        });
      });

      const chatsRes = await getChats();
      setChats(chatsRes.data.chats);
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1].content =
          "❌ Backend connection failed.";
        return updated;
      });
    }

    setLoading(false);
  }

  async function uploadFile(e) {
  const file = e.target.files[0];

  if (!file) return;

  // 📄 PDF
  if (file.type === "application/pdf") {
    uploadPDF(e);
    return;
  }

  // 🖼️ Image
  if (file.type.startsWith("image/")) {
    setLoading(true);

    try {
      const res = await analyzeImage(file);

      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: `📷 ${file.name}`,
        },
        {
          role: "assistant",
          content: res.result,
        },
      ]);
    } catch (err) {
      console.error(err);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "❌ Image analysis failed.",
        },
      ]);
    }

    setLoading(false);
    return;
  }

  alert("Unsupported file type.");
}

  async function regenerateResponse() {
    const lastUserMessage = [...messages]
      .reverse()
      .find((msg) => msg.role === "user");

    if (!lastUserMessage || loading || !activeChatId) return;

    setLoading(true);

    setMessages((prev) => {
      const updated = [...prev];

      if (updated[updated.length - 1]?.role === "assistant") {
        updated.pop();
      }

      updated.push({
        role: "assistant",
        content: "",
        sources: [],
      });

      return updated;
    });

    try {
      await streamChat(lastUserMessage.content, activeChatId, (chunk) => {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1].content += chunk;
          return updated;
        });
      });

      const chatsRes = await getChats();
      setChats(chatsRes.data.chats);
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1].content = "❌ Regenerate failed.";
        return updated;
      });
    }

    setLoading(false);
  }

  return {
    messages,
    setMessages,
    input,
    setInput,
    loading,

    chats,
    setChats,
    activeChatId,
    setActiveChatId,

    loadChats,
    selectChat,
    newChat,
    sendMessage,
    renameCurrentChat,
    deleteCurrentChat,
    regenerateResponse,
     uploadFile,
  };
}