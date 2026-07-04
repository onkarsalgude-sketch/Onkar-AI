import api from "./api";

export const sendChat = (message) =>
  api.post("/chat", { message });

export const getHistory = () =>
  api.get("/chat/history");

export const clearHistory = () =>
  api.delete("/chat/history");