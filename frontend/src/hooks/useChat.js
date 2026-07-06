import { useState, useEffect } from "react";
import {
  streamChat,
  getHistory,
  clearHistory,
  createChat,
  getChats,
  getChatMessages,
  renameChat,
  deleteChat,
} from "../services/chatService";

const welcomeMessage = {
  role: "assistant",
  content: "Hello! How can I help you today?",
};

export default function useChat() {
  const [messages, setMessages] = useState([welcomeMessage]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeChatId, setActiveChatId] = useState(null);
const [chats, setChats] = useState([]);

 useEffect(() => {
  loadChats();
}, []);
async function loadChats() {
  try {
    const res = await getChats();

    setChats(res.data.chats);

    if (res.data.chats.length > 0) {
      const firstChat = res.data.chats[0];

      setActiveChatId(firstChat.id);

      const msgs = await getChatMessages(firstChat.id);

      setMessages(
        msgs.data.messages.map((m) => ({
          role: m.role,
          content: m.content,
        }))
      );
    }
  } catch (err) {
    console.log(err);
  }
}
async function selectChat(chatId) {
  setActiveChatId(chatId);

  const res = await getChatMessages(chatId);

  setMessages(
    res.data.messages.map((m) => ({
      role: m.role,
      content: m.content,
    }))
  );
}

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
  setActiveChatId(null);
  setMessages([welcomeMessage]);
  setInput("");
}
async function renameCurrentChat(chatId) {
  const title = prompt("Enter new chat title");

  if (!title) return;

  await renameChat(chatId, title);

  await loadChats();
}

async function deleteCurrentChat(chatId) {
  if (!confirm("Delete this chat?")) return;

  await deleteChat(chatId);

  await loadChats();
}

  async function sendMessage() {
  if (!input.trim()) return;

  const text = input;
  let currentChatId = activeChatId;

if (!currentChatId) {
  const res = await createChat();
  currentChatId = res.data.chat_id;
  setActiveChatId(currentChatId);

  setChats((prev) => [
    { id: currentChatId, title: res.data.title },
    ...prev,
  ]);
}

  // User message add
  setMessages((prev) => [...prev, { role: "user", content: text }]);
  setInput("");
  setLoading(true);

  // Empty assistant message add
  setMessages((prev) => [
    ...prev,
    {
      role: "assistant",
      content: "",
    },
  ]);

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

  return {
    messages,
    setMessages,
    input,
    setInput,
    loading,
    newChat,
    sendMessage,
    loadHistory,
    activeChatId,
    setActiveChatId,
    chats,
    setChats,
    selectChat,
    renameCurrentChat,
    deleteCurrentChat,
  };
}