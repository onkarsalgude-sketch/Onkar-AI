import api from "./api";

export const uploadDocument = (formData) =>
  api.post("/documents/upload", formData);

export const getDocuments = () =>
  api.get("/documents");

export const deleteDocumentApi = (filename) =>
  api.delete(`/documents/${filename}`);