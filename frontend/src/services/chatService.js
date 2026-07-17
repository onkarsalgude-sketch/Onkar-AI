import api from "./api";

const API_URL = (
  api.defaults.baseURL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");


export const getModels = () =>
  api.get("/models");


export const sendChat = (
  message,
  chatId,
  modelId = null
) =>
  api.post("/chat", {
    message,
    chat_id: chatId,
    model_id: modelId,
  });


export const getHistory = () =>
  api.get("/chat/history");


export const clearHistory = () =>
  api.delete("/chat/history");


export const createChat = () =>
  api.post("/chats");


export const getChats = () =>
  api.get("/chats");


export const importChatBackup = (
  backup
) =>
  api.post(
    "/chats/import",
    backup
  );
export const getChatMessages = (chatId) =>
  api.get(`/chats/${chatId}/messages`);


export const deleteChat = (chatId) =>
  api.delete(`/chats/${chatId}`);


export const renameChat = (
  chatId,
  title
) =>
  api.put(
    `/chats/${chatId}?title=${encodeURIComponent(
      title
    )}`
  );


export async function streamChat(
  message,
  chatId,
  onChunk,
  modelId = null
) {
  const response = await fetch(
    `${API_URL}/chat/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify({
        message,
        chat_id: chatId,
        model_id: modelId,
      }),
    }
  );

  if (!response.ok) {
    const errorText =
      await response.text();

    throw new Error(
      `Chat request failed: ${response.status} ${errorText}`
    );
  }

  let sources = [];

  const encodedSources =
    response.headers.get("X-Sources");

  if (encodedSources) {
    try {
      sources = JSON.parse(
        decodeURIComponent(
          encodedSources
        )
      );
    } catch (error) {
      console.error(
        "Failed to parse sources:",
        error
      );
    }
  }

  const returnedChatId =
    Number(
      response.headers.get(
        "X-Chat-Id"
      )
    ) || chatId;

  const returnedModelId =
    response.headers.get(
      "X-Model-Id"
    ) || modelId;

  if (!response.body) {
    throw new Error(
      "Streaming response body is unavailable."
    );
  }

  const reader =
    response.body.getReader();

  const decoder =
    new TextDecoder("utf-8");

  while (true) {
    const { value, done } =
      await reader.read();

    if (done) break;

    const chunk = decoder.decode(
      value,
      {
        stream: true,
      }
    );

    if (chunk) {
      onChunk(chunk);
    }
  }

  const finalChunk =
    decoder.decode();

  if (finalChunk) {
    onChunk(finalChunk);
  }

  return {
    sources,
    chatId: returnedChatId,
    modelId: returnedModelId,
  };
}


export const togglePinChat = (
  chatId
) =>
  api.put(
    `/chats/${chatId}/pin`
  );


export const getFolders = () =>
  api.get("/folders");


export const createFolder = (
  name
) =>
  api.post("/folders", null, {
    params: { name },
  });


export const renameFolder = (
  folderId,
  name
) =>
  api.put(
    `/folders/${folderId}`,
    null,
    {
      params: { name },
    }
  );


export const deleteFolder = (
  folderId
) =>
  api.delete(
    `/folders/${folderId}`
  );


export const moveChatToFolder = (
  chatId,
  folderId = null
) =>
  api.put(
    `/chats/${chatId}/folder`,
    null,
    {
      params:
        folderId === null
          ? {}
          : {
              folder_id:
                folderId,
            },
    }
  );
export async function exportFullChatBackup(
  chatId
) {
  const response = await api.get(
    `/backups/chats/${chatId}/full`,
    {
      responseType: "blob",
    }
  );

  return response;
}


export async function importFullChatBackup(
  file
) {
  const formData = new FormData();

  formData.append("file", file);

  return api.post(
    "/backups/chats/import/full",
    formData,
    {
      headers: {
        "Content-Type":
          "multipart/form-data",
      },
    }
  );
}
export const searchChats = (
  query,
  {
    role = null,
    folderId = null,
    limit = 50,
  } = {}
) => {
  const params = {
    q: query,
    limit,
  };

  if (role) {
    params.role = role;
  }

  if (folderId !== null) {
    params.folder_id = folderId;
  }

  return api.get(
    "/chats/search",
    {
      params,
    }
  );
};
export const editMessage = (
  chatId,
  messageId,
  content
) =>
  api.patch(
    `/chats/${chatId}/messages/${messageId}`,
    {
      content,
    }
  );


export const deleteMessage = (
  chatId,
  messageId
) =>
  api.delete(
    `/chats/${chatId}/messages/${messageId}`
  );


export const regenerateMessage = (
  chatId,
  messageId,
  modelId = null
) =>
  api.post(
    `/chats/${chatId}/messages/${messageId}/regenerate`,
    {
      model_id: modelId,
    }
  );