export function normalizeAgentId(
  agentId
) {
  if (typeof agentId !== "string") {
    return null;
  }

  const normalized = agentId.trim();

  return normalized || null;
}


export function buildChatPayload({
  message,
  chatId,
  modelId = null,
  agentId = null,
}) {
  const payload = {
    message,
    chat_id: chatId,
    model_id: modelId,
  };

  const normalizedAgentId =
    normalizeAgentId(agentId);

  if (normalizedAgentId) {
    payload.agent_id =
      normalizedAgentId;
  }

  return payload;
}


export function normalizeAgentCatalog(
  catalog
) {
  if (!Array.isArray(catalog)) {
    return [];
  }

  return catalog.flatMap((item) => {
    const agentId =
      normalizeAgentId(
        item?.agent_id
      );

    const name =
      typeof item?.name === "string"
        ? item.name.trim()
        : "";

    const description =
      typeof item?.description ===
      "string"
        ? item.description.trim()
        : "";

    if (
      !agentId ||
      !name ||
      !description
    ) {
      return [];
    }

    const capabilities =
      Array.isArray(
        item.capabilities
      )
        ? item.capabilities
            .filter(
              (capability) =>
                typeof capability ===
                "string" &&
                capability.trim()
            )
            .map(
              (capability) =>
                capability.trim()
            )
        : [];

    return [
      {
        agent_id: agentId,
        name,
        description,
        capabilities,
      },
    ];
  });
}
