import {
  useEffect,
  useRef,
  useState,
} from "react";

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


function createErrorDetails(error) {
  const status =
    error?.response?.status;

  const backendMessage =
    error?.response?.data?.detail;

  const errorMessage =
    backendMessage ||
    error?.message ||
    "The request could not be completed.";

  if (
    typeof navigator !== "undefined" &&
    !navigator.onLine
  ) {
    return {
      title: "You are offline",
      message:
        "Reconnect to the internet and try again.",
      canRetry: true,
    };
  }

  if (
    status === 429 ||
    errorMessage.includes("429")
  ) {
    return {
      title: "Too many requests",
      message:
        "The AI service rate limit was reached. Wait briefly and retry.",
      canRetry: true,
    };
  }

  if (
    status === 401 ||
    status === 403
  ) {
    return {
      title: "AI service authorization failed",
      message:
        "The API key may be missing, invalid, or not permitted to use this model.",
      canRetry: false,
    };
  }

  if (
    status === 404
  ) {
    return {
      title: "Resource not found",
      message: errorMessage,
      canRetry: false,
    };
  }

  if (
    status >= 500
  ) {
    return {
      title: "Server error",
      message:
        "The backend or AI service encountered an error. Please retry.",
      canRetry: true,
    };
  }

  if (
    errorMessage
      .toLowerCase()
      .includes("failed to fetch") ||
    errorMessage
      .toLowerCase()
      .includes("networkerror") ||
    errorMessage
      .toLowerCase()
      .includes("network error")
  ) {
    return {
      title: "Backend unavailable",
      message:
        "Onkar AI could not connect to the backend. Check whether the server is running.",
      canRetry: true,
    };
  }

  return {
    title: "Request failed",
    message: errorMessage,
    canRetry: true,
  };
}


export default function useChat() {
  const [messages, setMessages] =
    useState([welcomeMessage]);

  const [input, setInput] =
    useState("");

  const [loading, setLoading] =
    useState(false);

  const [folders, setFolders] =
    useState([]);

  const [models, setModels] =
    useState([]);

  const [
    defaultModel,
    setDefaultModel,
  ] = useState("");

  const [
    selectedModel,
    setSelectedModel,
  ] = useState(() => {
    return (
      localStorage.getItem(
        "onkar-ai-selected-model"
      ) || ""
    );
  });

  const [pendingFile, setPendingFile] =
    useState(null);

  const [chatError, setChatError] =
    useState(null);

  const lastFailedRequestRef =
    useRef(null);

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
      const response =
        await getModels();

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


  function changeSelectedModel(
    modelId
  ) {
    if (!modelId) return;

    setSelectedModel(modelId);

    localStorage.setItem(
      "onkar-ai-selected-model",
      modelId
    );
  }


  function dismissChatError() {
    setChatError(null);
  }


  async function retryLastRequest() {
    const failedRequest =
      lastFailedRequestRef.current;

    if (
      !failedRequest ||
      loading
    ) {
      return;
    }

    await sendMessage({
      ...failedRequest,
      isRetry: true,
    });
  }


  function removePendingFile() {
    setPendingFile(null);
  }


  function handleNewChat() {
    setPendingFile(null);
    setChatError(null);

    lastFailedRequestRef.current =
      null;

    newChat();
  }


  async function handleSelectChat(
    chatId
  ) {
    setPendingFile(null);
    setChatError(null);

    lastFailedRequestRef.current =
      null;

    await selectChat(chatId);
  }


  async function uploadFile(event) {
    const file =
      event.target.files?.[0];

    if (!file) return;

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
      setChatError(null);

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

        setChatError(
          createErrorDetails(error)
        );

        setMessages(
          (previousMessages) => {
            const updatedMessages = [
              ...previousMessages,
            ];

            const lastMessage =
              updatedMessages[
                updatedMessages.length -
                  1
              ];

            if (
              lastMessage?.role ===
                "assistant" &&
              !lastMessage.content?.trim()
            ) {
              updatedMessages.pop();
            }

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


  async function sendMessage(
    requestOverride = null
  ) {
    const isRetry =
      requestOverride?.isRetry ===
      true;

    const text = isRetry
      ? String(
          requestOverride.text || ""
        ).trim()
      : input.trim();

    const attachedFile = isRetry
      ? requestOverride.attachedFile ||
        null
      : pendingFile;

    if (
      (!text && !attachedFile) ||
      loading
    ) {
      return;
    }

    const requestModelId = isRetry
      ? requestOverride.modelId ||
        selectedModel ||
        null
      : selectedModel || null;

    const requestPayload = {
      text,
      attachedFile,
      chatId: isRetry
        ? requestOverride.chatId ||
          null
        : null,
      modelId: requestModelId,
      userMessageAdded: isRetry
        ? Boolean(
            requestOverride.userMessageAdded
          )
        : false,
    };

    setChatError(null);
    setLoading(true);

    try {
      let currentChatId =
        requestPayload.chatId;

      if (!currentChatId) {
        currentChatId =
          await createNewChatIfNeeded();

        requestPayload.chatId =
          currentChatId;
      }

      const userMessage = {
        role: "user",
        content: text,
        sources: [],
      };

      if (
        attachedFile?.fileType ===
        "pdf"
      ) {
        userMessage.fileType =
          "pdf";

        userMessage.fileName =
          attachedFile.fileName;

        userMessage.fileSize =
          attachedFile.fileSize;
      }

      if (
        requestPayload.userMessageAdded
      ) {
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
      } else {
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

        requestPayload.userMessageAdded =
          true;

        setInput("");
        setPendingFile(null);
      }

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
          requestModelId
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
              requestModelId,
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

      lastFailedRequestRef.current =
        null;

      setChatError(null);
    } catch (error) {
      console.error(
        "Chat or PDF error:",
        error
      );

      lastFailedRequestRef.current =
        requestPayload;

      setChatError(
        createErrorDetails(error)
      );

      setMessages(
        (previousMessages) => {
          const updatedMessages = [
            ...previousMessages,
          ];

          const lastMessage =
            updatedMessages[
              updatedMessages.length -
                1
            ];

          if (
            lastMessage?.role ===
              "assistant" &&
            !lastMessage.content?.trim()
          ) {
            updatedMessages.pop();
          }

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

    const retryPayload = {
      text:
        lastUserMessage.content,
      attachedFile: null,
      chatId: activeChatId,
      modelId:
        selectedModel || null,
      userMessageAdded: true,
    };

    setChatError(null);
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

      lastFailedRequestRef.current =
        null;

      setChatError(null);
    } catch (error) {
      console.error(
        "Regenerate error:",
        error
      );

      lastFailedRequestRef.current =
        retryPayload;

      setChatError(
        createErrorDetails(error)
      );

      setMessages(
        (previousMessages) => {
          const updatedMessages = [
            ...previousMessages,
          ];

          const lastMessage =
            updatedMessages[
              updatedMessages.length -
                1
            ];

          if (
            lastMessage?.role ===
              "assistant" &&
            !lastMessage.content?.trim()
          ) {
            updatedMessages.pop();
          }

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

    chatError,
    retryLastRequest,
    dismissChatError,

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