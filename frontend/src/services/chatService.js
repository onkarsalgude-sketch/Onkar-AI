import api from "./api";
import { buildChatPayload } from "../utils/agentChat";

const API_URL = (
  api.defaults.baseURL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");


export const getModels = () =>
  api.get("/models");


export const getAgents = () =>
  api.get("/agents");


export const sendChat = (
  message,
  chatId,
  modelId = null,
  agentId = null
) =>
  api.post(
    "/chat",
    buildChatPayload({
      message,
      chatId,
      modelId,
      agentId,
    })
  );


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


export const getBranchParentComparison = (
  branchChatId,
  options = {}
) =>
  api.get(
    `/chats/${branchChatId}/compare-parent`,
    {
      signal: options.signal,
    }
  );


export class BranchMergeRequestError extends Error {
  constructor({
    status = null,
    code = "MERGE_REQUEST_FAILED",
    message = "The branch merge request could not be completed safely.",
    retryable = false,
    refreshPreview = false,
    operationId = null,
    retryAfter = null,
    canceled = false,
  } = {}) {
    super(message);
    this.name = canceled
      ? "AbortError"
      : "BranchMergeRequestError";
    this.status = status;
    this.code = canceled
      ? "ERR_CANCELED"
      : code;
    this.retryable = retryable;
    this.refresh_preview = refreshPreview;
    this.operation_id = operationId;
    this.retry_after = retryAfter;
  }
}


export async function mergeBranchIntoParent(
  branchChatId,
  requestBody,
  credential,
  { signal } = {}
) {
  try {
    const response = await api.post(
      `/chats/${branchChatId}/merge-parent`,
      requestBody,
      {
        signal,
        headers: {
          Authorization: `Bearer ${credential}`,
          "X-Onkar-Merge-Intent": "v1",
          "Content-Type": "application/json",
        },
      }
    );

    return response.data;
  } catch (requestError) {
    if (
      signal?.aborted ||
      requestError?.code === "ERR_CANCELED" ||
      requestError?.name === "CanceledError"
    ) {
      throw new BranchMergeRequestError({
        canceled: true,
        message: "The branch merge request was canceled.",
      });
    }

    const status = Number(
      requestError?.response?.status
    ) || null;
    const rawDetail =
      requestError?.response?.data?.detail;
    const detail =
      rawDetail &&
      typeof rawDetail === "object" &&
      !Array.isArray(rawDetail)
        ? rawDetail
        : {};
    const fallbackMessages = {
      401: "The merge credential was rejected.",
      403: "The merge request was rejected by the origin or intent security policy.",
      404: "Merge execution is disabled or unavailable.",
      413: "The merge request is too large.",
      415: "The client and server disagree about the merge request media type.",
      422: "The canonical selection or merge request is invalid.",
      429: "The merge rate limit was reached.",
      500: "The merge result is uncertain because the backend returned an internal error.",
      503: "The merge result is uncertain because the backend is busy or unavailable.",
    };
    const resultIsUncertain =
      status === null ||
      status === 500 ||
      status === 503;
    const safeMessage = resultIsUncertain
      ? status === null
        ? "The merge result is uncertain because the server response was not received."
        : fallbackMessages[status]
      : typeof detail.message === "string" &&
          detail.message.trim()
        ? detail.message.trim()
        : fallbackMessages[status] ||
          "The branch merge request was rejected safely.";
    const retryAfterHeader =
      requestError?.response?.headers?.[
        "retry-after"
      ];

    throw new BranchMergeRequestError({
      status,
      code:
        typeof detail.code === "string"
          ? detail.code
          : "MERGE_REQUEST_FAILED",
      message: safeMessage,
      retryable: detail.retryable === true,
      refreshPreview:
        detail.refresh_preview === true,
      operationId:
        Number.isInteger(detail.operation_id) &&
        detail.operation_id > 0
          ? detail.operation_id
          : null,
      retryAfter:
        typeof retryAfterHeader === "string"
          ? retryAfterHeader
          : null,
    });
  }
}


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
  modelId = null,
  agentId = null
) {
  const response = await fetch(
    `${API_URL}/chat/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify(
        buildChatPayload({
          message,
          chatId,
          modelId,
          agentId,
        })
      ),
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
  modelId = null,
  agentId = null
) => {
  const payload = {
    model_id: modelId,
  };

  if (agentId) {
    payload.agent_id = agentId;
  }

  return api.post(
    `/chats/${chatId}/messages/${messageId}/regenerate`,
    payload
  );
};
  export const saveMessageBookmark = (
  chatId,
  messageId,
  note = ""
) =>
  api.put(
    `/chats/${chatId}/messages/${messageId}/bookmark`,
    {
      note,
    }
  );


export const removeMessageBookmark = (
  chatId,
  messageId
) =>
  api.delete(
    `/chats/${chatId}/messages/${messageId}/bookmark`
  );


export const getBookmarks = (
  {
    query = "",
    role = null,
    folderId = null,
    limit = 100,
  } = {}
) => {
  const params = {
    limit,
  };

  if (query.trim()) {
    params.q = query.trim();
  }

  if (role) {
    params.role = role;
  }

  if (folderId !== null) {
    params.folder_id = folderId;
  }

  return api.get(
    "/bookmarks",
    {
      params,
    }
  );
};
export const createConversationBranch = (
  chatId,
  messageId,
  title = null
) =>
  api.post(
    `/chats/${chatId}/messages/${messageId}/branch`,
    {
      title,
    }
  );
