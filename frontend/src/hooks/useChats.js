import { useState } from "react";
import {
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

export default function useChats(setMessages, setInput) {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);

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
            sources: m.sources || [],
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
        sources: m.sources || [],
      }))
    );
  }

  function newChat() {
    setActiveChatId(null);
    setMessages([welcomeMessage]);
    setInput("");
  }

  async function createNewChatIfNeeded() {
    if (activeChatId) return activeChatId;

    const res = await createChat();
    const chatId = res.data.chat_id;

    setActiveChatId(chatId);

    setChats((prev) => [
      {
        id: chatId,
        title: res.data.title,
        last_message: "",
      },
      ...prev,
    ]);

    return chatId;
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

  return {
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
  };
}