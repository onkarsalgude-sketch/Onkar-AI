import { useEffect, useState } from "react";

import {
  streamChat,
  getChats,
  getModels,
  togglePinChat as togglePinChatRequest,
  getFolders,
  createFolder as createFolderRequest,
  renameFolder as renameFolderRequest,
  deleteFolder as deleteFolderRequest,
  moveChatToFolder as moveChatToFolderRequest,
} from "../services/chatService";

import { analyzeImage } from "../services/imageService";
import { uploadDocument } from "../services/documentService";

import useChats from "./useChats";


const welcomeMessage = {
  role: "assistant",
  content: "Hello! How can I help you today?",
  sources: [],
};


function formatFileSize(size) {
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(
    size /
    (1024 * 1024)
  ).toFixed(1)} MB`;
}


export default function useChat() {
  const [messages, setMessages] = useState([
    welcomeMessage,
  ]);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const [folders, setFolders] = useState([]);

  const [models, setModels] = useState([]);
  const [defaultModel, setDefaultModel] =
    useState("");

  const [selectedModel, setSelectedModel] =
    useState(() => {
      return (
        localStorage.getItem(
          "onkar-ai-selected-model"
        ) || ""
      );
    });

  // Send करण्यापूर्वी निवडलेली PDF
  const [pendingFile, setPendingFile] =
    useState(null);

  const {
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
  } = useChats(
    setMessages,
    setInput
  );


  useEffect(() => {
    loadChats();
    loadFolders();
    loadAvailableModels();
  }, []);


  async function loadAvailableModels() {
    try {
      const response = await getModels();

      const availableModels =
        response.data.models || [];

      const backendDefaultModel =
        response.data.default_model || "";

      setModels(availableModels);
      setDefaultModel(
        backendDefaultModel
      );

      const savedModel =
        localStorage.getItem(
          "onkar-ai-selected-model"
        );

      const savedModelExists =
        availableModels.some(
          (model) =>
            model.id === savedModel
        );

      const modelToUse =
        savedModelExists
          ? savedModel
          : backendDefaultModel ||
            availableModels[0]?.id ||
            "";

      setSelectedModel(modelToUse);

      if (modelToUse) {
        localStorage.setItem(
          "onkar-ai-selected-model",
          modelToUse
        );
      }
    } catch (error) {
      console.error(
        "Load models error:",
        error
      );

      setModels([]);
    }
  }


  function changeSelectedModel(modelId) {
    if (!modelId) return;

    setSelectedModel(modelId);

    localStorage.setItem(
      "onkar-ai-selected-model",
      modelId
    );
  }


  function removePendingFile() {
    setPendingFile(null);
  }


  function handleNewChat() {
    setPendingFile(null);
    newChat();
  }


  async function handleSelectChat(chatId) {
    setPendingFile(null);
    await selectChat(chatId);
  }


  async function uploadFile(event) {
    const file =
      event.target.files?.[0];

    if (!file) return;

    // Same file पुन्हा निवडता यावी
    event.target.value = "";

    if (
      file.type ===
      "application/pdf"
    ) {
      setPendingFile({
        file,
        fileType: "pdf",
        fileName: file.name,
        fileSize: formatFileSize(
          file.size
        ),
      });

      return;
    }

    if (
      file.type.startsWith("image/")
    ) {
      setLoading(true);

      const imageUrl =
        URL.createObjectURL(file);

      setMessages(
        (previousMessages) => [
          ...previousMessages,
          {
            role: "user",
            content: "",
            imageUrl,
            fileName: file.name,
            sources: [],
          },
          {
            role: "assistant",
            content: "",
            sources: [],
          },
        ]
      );

      try {
        const response =
          await analyzeImage(file);

        setMessages(
          (previousMessages) => {
            const updatedMessages = [
              ...previousMessages,
            ];

            const lastIndex =
              updatedMessages.length -
              1;

            updatedMessages[
              lastIndex
            ] = {
              ...updatedMessages[
                lastIndex
              ],
              content:
                response.result ||
                "Image analyzed successfully.",
            };

            return updatedMessages;
          }
        );
      } catch (error) {
        console.error(
          "Image analysis error:",
          error
        );

        setMessages(
          (previousMessages) => {
            const updatedMessages = [
              ...previousMessages,
            ];

            const lastIndex =
              updatedMessages.length -
              1;

            updatedMessages[
              lastIndex
            ] = {
              ...updatedMessages[
                lastIndex
              ],
              content:
                "❌ Image analysis failed.",
            };

            return updatedMessages;
          }
        );
      } finally {
        setLoading(false);
      }

      return;
    }

    alert(
      "Only PDF and image files are supported."
    );
  }


  async function sendMessage() {
    const text = input.trim();

    if (
      (!text && !pendingFile) ||
      loading
    ) {
      return;
    }

    const attachedFile =
      pendingFile;

    const currentChatId =
      await createNewChatIfNeeded();

    const userMessage = {
      role: "user",
      content: text,
      sources: [],
    };

    if (
      attachedFile?.fileType ===
      "pdf"
    ) {
      userMessage.fileType = "pdf";
      userMessage.fileName =
        attachedFile.fileName;
      userMessage.fileSize =
        attachedFile.fileSize;
    }

    setMessages(
      (previousMessages) => [
        ...previousMessages,
        userMessage,
        {
          role: "assistant",
          content: "",
          sources: [],
        },
      ]
    );

    setInput("");
    setPendingFile(null);
    setLoading(true);

    try {
      let requestText = text;

      if (
        attachedFile?.fileType ===
        "pdf"
      ) {
        const formData =
          new FormData();

        formData.append(
          "file",
          attachedFile.file
        );

        formData.append(
          "chat_id",
          String(currentChatId)
        );

        await uploadDocument(
          formData
        );

        requestText = text
          ? `Use the PDF uploaded in this chat to answer this question:\n${text}`
          : `Summarize the PDF "${attachedFile.fileName}" uploaded in this chat.`;
      }

      const result =
        await streamChat(
          requestText,
          currentChatId,
          (chunk) => {
            setMessages(
              (
                previousMessages
              ) => {
                const updatedMessages =
                  [
                    ...previousMessages,
                  ];

                const lastIndex =
                  updatedMessages.length -
                  1;

                updatedMessages[
                  lastIndex
                ] = {
                  ...updatedMessages[
                    lastIndex
                  ],
                  content:
                    updatedMessages[
                      lastIndex
                    ].content + chunk,
                };

                return updatedMessages;
              }
            );
          },
          selectedModel || null
        );

      setMessages(
        (previousMessages) => {
          const updatedMessages = [
            ...previousMessages,
          ];

          const lastIndex =
            updatedMessages.length - 1;

          updatedMessages[
            lastIndex
          ] = {
            ...updatedMessages[
              lastIndex
            ],
            sources:
              result?.sources || [],
            modelId:
              result?.modelId ||
              selectedModel,
          };

          return updatedMessages;
        }
      );

      if (result?.chatId) {
        setActiveChatId(
          result.chatId
        );
      }

      const chatsResponse =
        await getChats();

      setChats(
        chatsResponse.data.chats ||
          []
      );
    } catch (error) {
      console.error(
        "Chat or PDF error:",
        error
      );

      setMessages(
        (previousMessages) => {
          const updatedMessages = [
            ...previousMessages,
          ];

          const lastIndex =
            updatedMessages.length - 1;

          updatedMessages[
            lastIndex
          ] = {
            ...updatedMessages[
              lastIndex
            ],
            content:
              error.response?.data
                ?.detail ||
              error.message ||
              "❌ Message or PDF processing failed.",
            sources: [],
          };

          return updatedMessages;
        }
      );
    } finally {
      setLoading(false);
    }
  }


  async function regenerateResponse() {
    const lastUserMessage = [
      ...messages,
    ]
      .reverse()
      .find(
        (message) =>
          message.role ===
            "user" &&
          message.content?.trim()
      );

    if (
      !lastUserMessage ||
      loading ||
      !activeChatId
    ) {
      return;
    }

    setLoading(true);

    setMessages(
      (previousMessages) => {
        const updatedMessages = [
          ...previousMessages,
        ];

        if (
          updatedMessages[
            updatedMessages.length -
              1
          ]?.role === "assistant"
        ) {
          updatedMessages.pop();
        }

        updatedMessages.push({
          role: "assistant",
          content: "",
          sources: [],
        });

        return updatedMessages;
      }
    );

    try {
      const result =
        await streamChat(
          lastUserMessage.content,
          activeChatId,
          (chunk) => {
            setMessages(
              (
                previousMessages
              ) => {
                const updatedMessages =
                  [
                    ...previousMessages,
                  ];

                const lastIndex =
                  updatedMessages.length -
                  1;

                updatedMessages[
                  lastIndex
                ] = {
                  ...updatedMessages[
                    lastIndex
                  ],
                  content:
                    updatedMessages[
                      lastIndex
                    ].content + chunk,
                };

                return updatedMessages;
              }
            );
          },
          selectedModel || null
        );

      setMessages(
        (previousMessages) => {
          const updatedMessages = [
            ...previousMessages,
          ];

          const lastIndex =
            updatedMessages.length - 1;

          updatedMessages[
            lastIndex
          ] = {
            ...updatedMessages[
              lastIndex
            ],
            sources:
              result?.sources || [],
            modelId:
              result?.modelId ||
              selectedModel,
          };

          return updatedMessages;
        }
      );

      const chatsResponse =
        await getChats();

      setChats(
        chatsResponse.data.chats ||
          []
      );
    } catch (error) {
      console.error(
        "Regenerate error:",
        error
      );

      setMessages(
        (previousMessages) => {
          const updatedMessages = [
            ...previousMessages,
          ];

          const lastIndex =
            updatedMessages.length - 1;

          updatedMessages[
            lastIndex
          ] = {
            ...updatedMessages[
              lastIndex
            ],
            content:
              error.message ||
              "❌ Regenerate failed.",
            sources: [],
          };

          return updatedMessages;
        }
      );
    } finally {
      setLoading(false);
    }
  }


  async function toggleChatPin(
    chatId
  ) {
    if (!chatId) return;

    try {
      await togglePinChatRequest(
        chatId
      );

      await loadChats();
    } catch (error) {
      console.error(
        "Pin chat error:",
        error
      );

      alert(
        "Chat pin/unpin failed."
      );
    }
  }


  async function loadFolders() {
    try {
      const response =
        await getFolders();

      setFolders(
        response.data.folders ||
          []
      );
    } catch (error) {
      console.error(
        "Load folders error:",
        error
      );

      setFolders([]);
    }
  }


  async function createChatFolder(
    name
  ) {
    const folderName =
      name?.trim();

    if (!folderName) return false;

    try {
      await createFolderRequest(
        folderName
      );

      await loadFolders();

      return true;
    } catch (error) {
      console.error(
        "Create folder error:",
        error
      );

      alert(
        error.response?.data
          ?.detail ||
          "Folder creation failed."
      );

      return false;
    }
  }


  async function renameChatFolder(
    folderId,
    name
  ) {
    const folderName =
      name?.trim();

    if (!folderName) return false;

    try {
      await renameFolderRequest(
        folderId,
        folderName
      );

      await Promise.all([
        loadFolders(),
        loadChats(),
      ]);

      return true;
    } catch (error) {
      console.error(
        "Rename folder error:",
        error
      );

      alert(
        error.response?.data
          ?.detail ||
          "Folder rename failed."
      );

      return false;
    }
  }


  async function deleteChatFolder(
    folderId
  ) {
    try {
      await deleteFolderRequest(
        folderId
      );

      await Promise.all([
        loadFolders(),
        loadChats(),
      ]);

      return true;
    } catch (error) {
      console.error(
        "Delete folder error:",
        error
      );

      alert(
        error.response?.data
          ?.detail ||
          "Folder deletion failed."
      );

      return false;
    }
  }


  async function moveChatToFolder(
    chatId,
    folderId = null
  ) {
    try {
      await moveChatToFolderRequest(
        chatId,
        folderId
      );

      await Promise.all([
        loadChats(),
        loadFolders(),
      ]);

      return true;
    } catch (error) {
      console.error(
        "Move chat error:",
        error
      );

      alert(
        error.response?.data
          ?.detail ||
          "Moving chat failed."
      );

      return false;
    }
  }


  return {
    messages,
    setMessages,

    input,
    setInput,

    loading,

    pendingFile,
    removePendingFile,

    chats,
    setChats,
    activeChatId,
    setActiveChatId,

    folders,
    loadFolders,

    models,
    defaultModel,
    selectedModel,
    changeSelectedModel,
    loadAvailableModels,

    loadChats,

    selectChat:
      handleSelectChat,

    newChat:
      handleNewChat,

    sendMessage,
    regenerateResponse,

    renameCurrentChat,
    deleteCurrentChat,
    toggleChatPin,

    createChatFolder,
    renameChatFolder,
    deleteChatFolder,
    moveChatToFolder,

    uploadFile,
  };
}