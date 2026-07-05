import api from "./api";

export const sendChat = (message) =>
  api.post("/chat", { message });

export const getHistory = () =>
  api.get("/chat/history");

export const clearHistory = () =>
  api.delete("/chat/history");

// ✅ Streaming API
export async function streamChat(message, onChunk) {
  const response = await fetch(
    `${import.meta.env.VITE_API_URL}/chat/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
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