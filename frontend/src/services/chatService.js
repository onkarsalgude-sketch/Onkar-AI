import api from "./api";

export const sendChat = (message, chatId) =>
  api.post("/chat", { message, chat_id: chatId });

export const getHistory = () =>
  api.get("/chat/history");

export const clearHistory = () =>
  api.delete("/chat/history");

export const createChat = () =>
  api.post("/chats");

export const getChats = () =>
  api.get("/chats");

export const getChatMessages = (chatId) =>
  api.get(`/chats/${chatId}/messages`);

export const deleteChat = (chatId) =>
  api.delete(`/chats/${chatId}`);

export const renameChat = (chatId, title) =>
  api.put(`/chats/${chatId}?title=${encodeURIComponent(title)}`);

export async function streamChat(message, chatId, onChunk) {
  const response = await fetch(
    `${import.meta.env.VITE_API_URL}/chat/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        chat_id: chatId,
      }),
    }
  );

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { value, done } = await reader.read();

    if (done) break;

    await new Promise((resolve) => setTimeout(resolve, 45));
    onChunk(decoder.decode(value));
  }
}