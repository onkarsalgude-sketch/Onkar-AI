import api from "./api";

const API_BASE_URL = String(
  import.meta.env.VITE_API_URL || ""
).replace(/\/$/, "");

function normalizePreviewPage(page) {
  const parsed = Number.parseInt(
    String(page ?? ""),
    10
  );

  if (
    !Number.isFinite(parsed) ||
    parsed < 1
  ) {
    return 1;
  }

  return parsed;
}

export function buildPdfPreviewUrls({
  filename,
  chatId,
  page,
} = {}) {
  const safeFilename =
    typeof filename === "string"
      ? filename.trim()
      : "";

  const parsedChatId = Number.parseInt(
    String(chatId ?? ""),
    10
  );

  if (
    !safeFilename ||
    !Number.isFinite(parsedChatId) ||
    parsedChatId < 1 ||
    !API_BASE_URL
  ) {
    return null;
  }

  const normalizedPage =
    normalizePreviewPage(page);

  const encodedFilename =
    encodeURIComponent(safeFilename);

  const encodedChatId = encodeURIComponent(
    String(parsedChatId)
  );

  const validationUrl = `${API_BASE_URL}/documents/${encodedFilename}/preview?chat_id=${encodedChatId}`;

  const viewerUrl = `${validationUrl}#page=${normalizedPage}`;

  return {
    filename: safeFilename,
    chatId: parsedChatId,
    page: normalizedPage,
    validationUrl,
    viewerUrl,
  };
}

export async function validatePdfPreviewUrl(
  validationUrl
) {
  if (!validationUrl) {
    throw new Error(
      "Invalid preview URL"
    );
  }

  const response = await fetch(
    validationUrl,
    {
      method: "HEAD",
    }
  );

  if (!response.ok) {
    throw new Error(
      `Preview unavailable (${response.status})`
    );
  }

  return true;
}

export const uploadDocument = (formData) =>
  api.post("/documents/upload", formData);

export const getDocuments = (chatId) =>
  api.get("/documents", {
    params: {
      chat_id: chatId,
    },
  });

export const updateDocumentSelection = (
  documentId,
  chatId,
  isSelected
) =>
  api.put(
    `/documents/${documentId}/selection`,
    {
      is_selected: isSelected,
    },
    {
      params: {
        chat_id: chatId,
      },
    }
  );

export const deleteDocumentApi = (
  filename,
  chatId
) =>
  api.delete(
    `/documents/${encodeURIComponent(filename)}`,
    {
      params: {
        chat_id: chatId,
      },
    }
  );