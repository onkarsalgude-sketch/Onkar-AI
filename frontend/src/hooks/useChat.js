import { useEffect, useState } from "react";

import { streamChat, getChats } from "../services/chatService";
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

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function useChat() {
  const [messages, setMessages] = useState([
    welcomeMessage,
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  // Send करण्यापूर्वी निवडलेली PDF
  const [pendingFile, setPendingFile] = useState(null);

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
  } = useChats(setMessages, setInput);

  useEffect(() => {
    loadChats();
  }, []);

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

  /*
   * Attachment button वरून file निवडल्यानंतर:
   * PDF लगेच upload होणार नाही.
   * ती input जवळ preview म्हणून ठेवली जाईल.
   */
  async function uploadFile(event) {
    const file = event.target.files?.[0];

    if (!file) return;

    // Same file पुन्हा निवडता यावी
    event.target.value = "";

    if (file.type === "application/pdf") {
      setPendingFile({
        file,
        fileType: "pdf",
        fileName: file.name,
        fileSize: formatFileSize(file.size),
      });

      return;
    }

    // Image flow सध्या पूर्वीसारखाच ठेवला आहे
    if (file.type.startsWith("image/")) {
      setLoading(true);

      const imageUrl = URL.createObjectURL(file);

      setMessages((previousMessages) => [
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
      ]);

      try {
        const response = await analyzeImage(file);

        setMessages((previousMessages) => {
          const updatedMessages = [...previousMessages];
          const lastIndex = updatedMessages.length - 1;

          updatedMessages[lastIndex] = {
            ...updatedMessages[lastIndex],
            content:
              response.result ||
              "Image analyzed successfully.",
          };

          return updatedMessages;
        });
      } catch (error) {
        console.error("Image analysis error:", error);

        setMessages((previousMessages) => {
          const updatedMessages = [...previousMessages];
          const lastIndex = updatedMessages.length - 1;

          updatedMessages[lastIndex] = {
            ...updatedMessages[lastIndex],
            content: "❌ Image analysis failed.",
          };

          return updatedMessages;
        });
      } finally {
        setLoading(false);
      }

      return;
    }

    alert("Only PDF and image files are supported.");
  }

  async function sendMessage() {
    const text = input.trim();

    // Text किंवा PDF यापैकी किमान एक असणे आवश्यक
    if ((!text && !pendingFile) || loading) return;

    const attachedFile = pendingFile;
    const currentChatId =
      await createNewChatIfNeeded();

    const userMessage = {
      role: "user",
      content: text,
      sources: [],
    };

    if (attachedFile?.fileType === "pdf") {
      userMessage.fileType = "pdf";
      userMessage.fileName = attachedFile.fileName;
      userMessage.fileSize = attachedFile.fileSize;
    }

    setMessages((previousMessages) => [
      ...previousMessages,
      userMessage,
      {
        role: "assistant",
        content: "",
        sources: [],
      },
    ]);

    setInput("");
    setPendingFile(null);
    setLoading(true);

    try {
      let requestText = text;

      /*
       * PDF असेल तर Send दाबल्यावरच upload.
       * chat_id पुढे backend मध्ये PDF scope करण्यासाठी वापरणार.
       */
      if (attachedFile?.fileType === "pdf") {
        const formData = new FormData();

        formData.append("file", attachedFile.file);
        formData.append(
          "chat_id",
          String(currentChatId)
        );

        await uploadDocument(formData);

        requestText = text
          ? `Use the PDF uploaded in this chat to answer this question:\n${text}`
          : `Summarize the PDF "${attachedFile.fileName}" uploaded in this chat.`;
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
        }
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
        };

        return updatedMessages;
      });

      if (result?.chatId) {
        setActiveChatId(result.chatId);
      }

      const chatsResponse = await getChats();
      setChats(chatsResponse.data.chats || []);
    } catch (error) {
      console.error("Chat or PDF error:", error);

      setMessages((previousMessages) => {
        const updatedMessages = [
          ...previousMessages,
        ];
        const lastIndex =
          updatedMessages.length - 1;

        updatedMessages[lastIndex] = {
          ...updatedMessages[lastIndex],
          content:
            error.response?.data?.detail ||
            "❌ Message or PDF processing failed.",
          sources: [],
        };

        return updatedMessages;
      });
    } finally {
      setLoading(false);
    }
  }

  async function regenerateResponse() {
    const lastUserMessage = [...messages]
      .reverse()
      .find(
        (message) =>
          message.role === "user" &&
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

    try {
      const result = await streamChat(
        lastUserMessage.content,
        activeChatId,
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
        }
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
        };

        return updatedMessages;
      });

      const chatsResponse = await getChats();
      setChats(chatsResponse.data.chats || []);
    } catch (error) {
      console.error("Regenerate error:", error);

      setMessages((previousMessages) => {
        const updatedMessages = [
          ...previousMessages,
        ];
        const lastIndex =
          updatedMessages.length - 1;

        updatedMessages[lastIndex] = {
          ...updatedMessages[lastIndex],
          content: "❌ Regenerate failed.",
          sources: [],
        };

        return updatedMessages;
      });
    } finally {
      setLoading(false);
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

    loadChats,
    selectChat: handleSelectChat,
    newChat: handleNewChat,
    sendMessage,
    renameCurrentChat,
    deleteCurrentChat,
    regenerateResponse,
    uploadFile,
  };
}