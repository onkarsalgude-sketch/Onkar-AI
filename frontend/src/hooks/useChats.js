import { useState } from "react";

import {
  createChat,
  deleteChat,
  getChatMessages,
  getChats,
  importChatBackup as importChatBackupRequest,
  renameChat,
} from "../services/chatService";

const welcomeMessage = {
  role: "assistant",
  content: "Hello! How can I help you today?",
  sources: [],
};

function normalizeMessages(messages = []) {
  return messages.map((message) => {
    const attachment =
      message.attachment || null;

    return {
      role: message.role,
      content: message.content,
      sources: message.sources || [],

      modelId:
        message.model_id ||
        message.modelId ||
        null,

      created_at:
        message.created_at || null,

      fileName:
        message.fileName ||
        attachment?.filename ||
        null,

      fileType:
        message.fileType ||
        attachment?.type ||
        null,

      fileSize:
        message.fileSize ||
        attachment?.size ||
        null,
    };
  });
}

export default function useChats(
  setMessages,
  setInput
) {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] =
    useState(null);

  async function loadMessages(chatId) {
    const response =
      await getChatMessages(chatId);

    setMessages(
      normalizeMessages(
        response?.data?.messages || []
      )
    );
  }

  async function loadChats() {
    try {
      const response = await getChats();

      const loadedChats =
        response?.data?.chats || [];

      setChats(loadedChats);

      if (loadedChats.length === 0) {
        setActiveChatId(null);
        setMessages([welcomeMessage]);
        setInput("");
        return;
      }

      const activeChatStillExists =
        loadedChats.some(
          (chat) =>
            chat.id === activeChatId
        );

      if (
        activeChatId &&
        activeChatStillExists
      ) {
        return;
      }

      const fallbackChat =
        loadedChats[0];

      setActiveChatId(
        fallbackChat.id
      );

      await loadMessages(
        fallbackChat.id
      );
    } catch (error) {
      console.error(
        "Load chats error:",
        error
      );
    }
  }

  async function selectChat(chatId) {
    if (!chatId) {
      return;
    }

    try {
      const response =
        await getChatMessages(chatId);

      setActiveChatId(chatId);

      setMessages(
        normalizeMessages(
          response?.data?.messages || []
        )
      );
    } catch (error) {
      console.error(
        "Select chat error:",
        error
      );

      window.alert(
        "Unable to open this chat."
      );
    }
  }

  function newChat() {
    setActiveChatId(null);
    setMessages([welcomeMessage]);
    setInput("");
  }

  async function createNewChatIfNeeded() {
    if (activeChatId) {
      return activeChatId;
    }

    const response =
      await createChat();

    const chatId =
      response.data.chat_id;

    const newChatItem = {
      id: chatId,
      title:
        response.data.title ||
        "New Chat",
      last_message: "",
      created_at:
        response.data.created_at ||
        new Date().toISOString(),
      is_pinned: false,
      folder_id: null,
      folder_name: null,
    };

    setActiveChatId(chatId);

    setChats((currentChats) => [
      newChatItem,
      ...currentChats,
    ]);

    return chatId;
  }

  async function restoreChatBackup(
    backup
  ) {
    if (
      !backup ||
      typeof backup !== "object" ||
      Array.isArray(backup)
    ) {
      window.alert(
        "Invalid chat backup data."
      );

      return null;
    }

    try {
      const response =
        await importChatBackupRequest(
          backup
        );

      const result =
        response?.data;

      const importedChatId =
        result?.chat_id;

      if (!importedChatId) {
        throw new Error(
          "The backend did not return an imported chat ID."
        );
      }

      const chatsResponse =
        await getChats();

      setChats(
        chatsResponse?.data?.chats ||
          []
      );

      setActiveChatId(
        importedChatId
      );

      await loadMessages(
        importedChatId
      );

      setInput("");

      return result;
    } catch (error) {
      console.error(
        "Chat backup import error:",
        error
      );

      window.alert(
        error?.response?.data?.detail ||
          error?.message ||
          "Unable to import the chat backup."
      );

      return null;
    }
  }

  async function renameCurrentChat(
    chatId
  ) {
    const chat = chats.find(
      (item) => item.id === chatId
    );

    const enteredTitle =
      window.prompt(
        "Enter new chat title:",
        chat?.title || "New Chat"
      );

    if (enteredTitle === null) {
      return false;
    }

    const title =
      enteredTitle.trim();

    if (!title) {
      window.alert(
        "Chat title cannot be empty."
      );

      return false;
    }

    if (title === chat?.title) {
      return true;
    }

    try {
      await renameChat(
        chatId,
        title
      );

      setChats((currentChats) =>
        currentChats.map((item) =>
          item.id === chatId
            ? {
                ...item,
                title,
              }
            : item
        )
      );

      return true;
    } catch (error) {
      console.error(
        "Rename chat error:",
        error
      );

      window.alert(
        error?.response?.data?.detail ||
          "Unable to rename the chat."
      );

      return false;
    }
  }

  async function deleteCurrentChat(
    chatId
  ) {
    const chat = chats.find(
      (item) => item.id === chatId
    );

    const title =
      chat?.title || "New Chat";

    const confirmed =
      window.confirm(
        `Delete "${title}"?\n\nThis action cannot be undone.`
      );

    if (!confirmed) {
      return false;
    }

    try {
      await deleteChat(chatId);

      const response =
        await getChats();

      const remainingChats =
        response?.data?.chats || [];

      setChats(remainingChats);

      if (chatId !== activeChatId) {
        return true;
      }

      if (remainingChats.length > 0) {
        const deletedIndex =
          chats.findIndex(
            (item) =>
              item.id === chatId
          );

        const fallbackIndex =
          Math.min(
            Math.max(
              deletedIndex,
              0
            ),
            remainingChats.length - 1
          );

        const fallbackChat =
          remainingChats[
            fallbackIndex
          ];

        setActiveChatId(
          fallbackChat.id
        );

        await loadMessages(
          fallbackChat.id
        );

        return true;
      }

      setActiveChatId(null);
      setMessages([welcomeMessage]);
      setInput("");

      return true;
    } catch (error) {
      console.error(
        "Delete chat error:",
        error
      );

      window.alert(
        error?.response?.data?.detail ||
          "Unable to delete the chat."
      );

      return false;
    }
  }

  return {
    chats,
    setChats,

    activeChatId,
    setActiveChatId,

    loadChats,
    selectChat,
    newChat,
    createNewChatIfNeeded,
    restoreChatBackup,
    renameCurrentChat,
    deleteCurrentChat,
  };
}