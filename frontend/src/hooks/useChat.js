import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  streamChat,
  getChats,
  getChatMessages,
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

  // Array of { file, fileType, fileName, fileSize }
  const [pendingFiles, setPendingFiles] =
    useState([]);

  // null | { current: number, total: number, fileName: string }
  const [uploadProgress, setUploadProgress] =
    useState(null);

  // null | { succeeded: string[], duplicates: string[], failed: string[] }
  const [uploadSummary, setUploadSummary] =
    useState(null);

  const [chatError, setChatError] =
    useState(null);

  const [
    documentRefreshKey,
    setDocumentRefreshKey,
  ] = useState(0);

  const lastFailedRequestRef =
    useRef(null);

  const {
  chats,
  setChats,

  activeChatId,
  setActiveChatId,

  messageSearchTarget,
  clearMessageSearchTarget,

  messageActionLoadingId,
  editCurrentMessage,
  deleteCurrentMessage,
  regenerateCurrentMessage,
  saveCurrentMessageBookmark,
removeCurrentMessageBookmark,

  loadChats,
  selectChat,
  newChat,
  createNewChatIfNeeded,
  restoreChatBackup,
  restoreFullChatBackup,
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


  function removePendingFileAt(index) {
    setPendingFiles((prev) =>
      prev.filter((_, i) => i !== index)
    );
  }

  function clearAllPendingFiles() {
    setPendingFiles([]);
  }

  function dismissUploadSummary() {
    setUploadSummary(null);
  }


  function handleNewChat() {
    setPendingFiles([]);
    setUploadSummary(null);
    setChatError(null);

    lastFailedRequestRef.current =
      null;

    newChat();
  }


 async function handleSelectChat(
  chatId,
  messageId = null
) {
    setPendingFiles([]);
    setUploadSummary(null);
    setChatError(null);

    lastFailedRequestRef.current =
      null;

    await selectChat(
  chatId,
  messageId
);
  }

  async function syncLatestPersistedMessages(
  chatId
) {
  if (!chatId) return;

  try {
    const response =
      await getChatMessages(chatId);

    const persistedMessages =
      response?.data?.messages || [];

    const latestUserMessage = [
      ...persistedMessages,
    ]
      .reverse()
      .find(
        (message) =>
          message.role === "user"
      );

    const latestAssistantMessage = [
      ...persistedMessages,
    ]
      .reverse()
      .find(
        (message) =>
          message.role ===
          "assistant"
      );

    setMessages(
      (previousMessages) => {
        const updatedMessages = [
          ...previousMessages,
        ];

        let assistantIndex = -1;

        for (
          let index =
            updatedMessages.length - 1;
          index >= 0;
          index -= 1
        ) {
          if (
            updatedMessages[index]
              ?.role === "assistant"
          ) {
            assistantIndex = index;
            break;
          }
        }

        let userIndex = -1;

        const userSearchStart =
          assistantIndex > 0
            ? assistantIndex - 1
            : updatedMessages.length -
              1;

        for (
          let index = userSearchStart;
          index >= 0;
          index -= 1
        ) {
          if (
            updatedMessages[index]
              ?.role === "user"
          ) {
            userIndex = index;
            break;
          }
        }

        if (
          userIndex >= 0 &&
          latestUserMessage
        ) {
          updatedMessages[userIndex] = {
            ...updatedMessages[userIndex],
            id:
              latestUserMessage.id,
            created_at:
              latestUserMessage.created_at,
          };
        }

        if (
          assistantIndex >= 0 &&
          latestAssistantMessage
        ) {
          updatedMessages[
            assistantIndex
          ] = {
            ...updatedMessages[
              assistantIndex
            ],
            id:
              latestAssistantMessage.id,
            created_at:
              latestAssistantMessage.created_at,
            sources:
              latestAssistantMessage
                .sources ||
              updatedMessages[
                assistantIndex
              ].sources ||
              [],
            modelId:
              latestAssistantMessage
                .model_id ||
              updatedMessages[
                assistantIndex
              ].modelId ||
              null,
          };
        }

        return updatedMessages;
      }
    );
  } catch (error) {
    console.error(
      "Message ID sync error:",
      error
    );
  }
}

  async function handleEditMessage(
  messageId,
  content
) {
  setChatError(null);

  lastFailedRequestRef.current =
    null;

  return editCurrentMessage(
    messageId,
    content
  );
}


async function handleDeleteMessage(
  messageId
) {
  setChatError(null);

  lastFailedRequestRef.current =
    null;

  return deleteCurrentMessage(
    messageId
  );
}


async function handleRegenerateMessage(
  messageId
) {
  setChatError(null);

  lastFailedRequestRef.current =
    null;

  return regenerateCurrentMessage(
    messageId,
    selectedModel || null
  );
}

async function handleSaveMessageBookmark(
  messageId,
  note = ""
) {
  setChatError(null);

  lastFailedRequestRef.current =
    null;

  return saveCurrentMessageBookmark(
    messageId,
    note
  );
}


async function handleRemoveMessageBookmark(
  messageId
) {
  setChatError(null);

  lastFailedRequestRef.current =
    null;

  return removeCurrentMessageBookmark(
    messageId
  );
}

  async function uploadFile(event) {
    const allFiles = Array.from(
      event.target.files || []
    );

    if (allFiles.length === 0) return;

    event.target.value = "";

    const pdfFiles = allFiles.filter(
      (f) => f.type === "application/pdf"
    );

    const imageFiles = allFiles.filter(
      (f) => f.type.startsWith("image/")
    );

    const otherFiles = allFiles.filter(
      (f) =>
        f.type !== "application/pdf" &&
        !f.type.startsWith("image/")
    );

    // Mixed PDF + image in one pick is not supported
    if (pdfFiles.length > 0 && imageFiles.length > 0) {
      alert(
        "Please select either PDF files or a single image, not both at once."
      );
      return;
    }

    if (otherFiles.length > 0 && pdfFiles.length === 0 && imageFiles.length === 0) {
      alert("Only PDF and image files are supported.");
      return;
    }

    // --- PDF batch ---
    if (pdfFiles.length > 0) {
      const MAX_PDFS = 10;

      setPendingFiles((prev) => {
        const existingKeys = new Set(
          prev.map((p) => `${p.fileName}__${p.file.size}`)
        );

        const newEntries = pdfFiles
          .filter(
            (f) =>
              !existingKeys.has(`${f.name}__${f.size}`)
          )
          .map((f) => ({
            file: f,
            fileType: "pdf",
            fileName: f.name,
            fileSize: formatFileSize(f.size),
          }));

        return [...prev, ...newEntries].slice(0, MAX_PDFS);
      });

      return;
    }

    // --- Image (single file, unchanged flow) ---
    if (
      imageFiles.length > 0
    ) {
      const file = imageFiles[0];
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
      requestOverride?.isRetry === true;

    const text = isRetry
      ? String(requestOverride.text || "").trim()
      : input.trim();

    // On retry, attachedFile is always null —
    // PDFs were already uploaded; we only replay the chat request.
    const attachedFile = isRetry
      ? null
      : null; // kept for structural clarity; batch uses pendingFiles

    // For a retry, hasPendingPdfs is always false
    const hasPendingPdfs =
      !isRetry && pendingFiles.length > 0;

    if (
      (!text && !hasPendingPdfs) ||
      loading
    ) {
      return;
    }

    const requestModelId = isRetry
      ? requestOverride.modelId ||
        selectedModel ||
        null
      : selectedModel || null;

    // requestPayload intentionally carries NO file references —
    // it is only used for chat-level retry after uploads are done.
    const requestPayload = {
      text,
      attachedFile: null,
      chatId: isRetry
        ? requestOverride.chatId || null
        : null,
      modelId: requestModelId,
      userMessageAdded: isRetry
        ? Boolean(requestOverride.userMessageAdded)
        : false,
    };

    setChatError(null);
    setUploadSummary(null);
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

      // --- Build user message ---
      const userMessage = {
        role: "user",
        content: text,
        sources: [],
      };

      if (hasPendingPdfs) {
        // Annotate with count of PDFs being attached
        userMessage.fileType = "pdf";
        userMessage.fileName =
          pendingFiles.length === 1
            ? pendingFiles[0].fileName
            : `${pendingFiles.length} PDFs`;
        userMessage.fileSize =
          pendingFiles.length === 1
            ? pendingFiles[0].fileSize
            : "";
      }

      if (requestPayload.userMessageAdded) {
        setMessages((previousMessages) => {
          const updatedMessages = [
            ...previousMessages,
          ];

          if (
            updatedMessages[
              updatedMessages.length - 1
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
        });
      } else {
        setMessages((previousMessages) => [
          ...previousMessages,
          userMessage,
          {
            role: "assistant",
            content: "",
            sources: [],
          },
        ]);

        requestPayload.userMessageAdded = true;

        setInput("");
        setPendingFiles([]);
      }

      // --- Sequential PDF batch upload ---
      let requestText = text;

      if (hasPendingPdfs) {
        const batchFiles = [...pendingFiles];
        const succeeded = [];
        const duplicates = [];
        const failed = [];

        for (let i = 0; i < batchFiles.length; i++) {
          const pf = batchFiles[i];

          setUploadProgress({
            current: i + 1,
            total: batchFiles.length,
            fileName: pf.fileName,
          });

          const formData = new FormData();
          formData.append("file", pf.file);
          formData.append(
            "chat_id",
            String(currentChatId)
          );

          try {
            await uploadDocument(formData);
            succeeded.push(pf.fileName);
          } catch (uploadError) {
            if (
              uploadError?.response?.status === 409
            ) {
              duplicates.push(pf.fileName);
            } else {
              failed.push(pf.fileName);
              console.error(
                `Upload failed for ${pf.fileName}:`,
                uploadError
              );
            }
          }
        }

        setUploadProgress(null);

        // Refresh Document Library once after entire batch
        if (succeeded.length > 0) {
          setDocumentRefreshKey(
            (currentKey) => currentKey + 1
          );
        }

        // Record summary for UI
        setUploadSummary({ succeeded, duplicates, failed });

        const usable =
          succeeded.length + duplicates.length;

        // If nothing is usable and no text → abort, no chat request
        if (usable === 0 && !text) {
          setChatError({
            title: "Upload failed",
            message:
              failed.length > 0
                ? `All PDFs failed to upload: ${failed.join(", ")}.`
                : "No PDFs could be uploaded.",
            canRetry: false,
          });
          setLoading(false);
          return;
        }

        // Build request text based on batch result
        // requestPayload.attachedFile stays null — retry will only replay chat
        if (text) {
          requestText =
            `Use the PDFs uploaded in this chat to answer this question:\n${text}`;
        } else if (succeeded.length === 1) {
          requestText =
            `Summarize the PDF "${succeeded[0]}" uploaded in this chat.`;
        } else {
          requestText =
            `Summarize the PDFs uploaded in this chat.`;
        }

        // Strip file refs from payload so retry never re-uploads
        requestPayload.attachedFile = null;
      }

      const result = await streamChat(
        requestText,
        currentChatId,
        (chunk) => {
          setMessages((previousMessages) => {
            const updatedMessages = [
              ...previousMessages,
            ];

            const lastIndex =
              updatedMessages.length - 1;

            updatedMessages[lastIndex] = {
              ...updatedMessages[lastIndex],
              content:
                updatedMessages[lastIndex].content +
                chunk,
            };

            return updatedMessages;
          });
        },
        requestModelId
      );

      setMessages((previousMessages) => {
        const updatedMessages = [
          ...previousMessages,
        ];

        const lastIndex =
          updatedMessages.length - 1;

        updatedMessages[lastIndex] = {
          ...updatedMessages[lastIndex],
          sources: result?.sources || [],
          modelId:
            result?.modelId || requestModelId,
        };

        return updatedMessages;
      });

      await syncLatestPersistedMessages(
  currentChatId
);

      if (result?.chatId) {
        setActiveChatId(result.chatId);
      }

      const chatsResponse = await getChats();

      setChats(
        chatsResponse.data.chats || []
      );

      lastFailedRequestRef.current = null;

      setChatError(null);
    } catch (error) {
      console.error(
        "Chat or PDF error:",
        error
      );

      // Store only chat-level details — no File objects
      lastFailedRequestRef.current = {
        ...requestPayload,
        attachedFile: null,
      };

      setChatError(createErrorDetails(error));

      setMessages((previousMessages) => {
        const updatedMessages = [
          ...previousMessages,
        ];

        const lastMessage =
          updatedMessages[
            updatedMessages.length - 1
          ];

        if (
          lastMessage?.role === "assistant" &&
          !lastMessage.content?.trim()
        ) {
          updatedMessages.pop();
        }

        return updatedMessages;
      });
    } finally {
      setUploadProgress(null);
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

await syncLatestPersistedMessages(
  activeChatId
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

    pendingFiles,
    removePendingFileAt,
    clearAllPendingFiles,

    uploadProgress,
    uploadSummary,
    dismissUploadSummary,

    chats,
    setChats,
   activeChatId,
setActiveChatId,

messageSearchTarget,
clearMessageSearchTarget,

documentRefreshKey,

messageActionLoadingId,

editMessage:
  handleEditMessage,

deleteMessage:
  handleDeleteMessage,

regenerateMessage:
  handleRegenerateMessage,

  saveMessageBookmark:
  handleSaveMessageBookmark,

removeMessageBookmark:
  handleRemoveMessageBookmark,
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
restoreChatBackup,
restoreFullChatBackup,
toggleChatPin,

    createChatFolder,
    renameChatFolder,
    deleteChatFolder,
    moveChatToFolder,

    uploadFile,
  };
}
