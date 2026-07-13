import api from "./api";

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