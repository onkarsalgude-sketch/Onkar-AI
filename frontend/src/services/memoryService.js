import api from "./api";


function memoryCredential(
  credential
) {
  const token = String(
    credential || ""
  ).trim();

  if (token) {
    return token;
  }

  const error = new Error(
    "Memory credential is required."
  );

  error.code =
    "credential_required";

  throw error;
}


function memoryRequestError(
  requestError
) {
  const error = new Error(
    "Memory request failed."
  );

  error.status = Number(
    requestError?.response?.status ||
      0
  );

  return error;
}


function normalizeMemoryItem(
  item
) {
  const role = String(
    item?.role || ""
  ).trim();

  const preview = String(
    item?.preview || ""
  );

  if (
    !role ||
    role.length > 100 ||
    !preview ||
    preview.length > 240 ||
    typeof item?.truncated !==
      "boolean"
  ) {
    throw new Error(
      "Memory response was invalid."
    );
  }

  return {
    role,
    preview,
    truncated: item.truncated,
  };
}


function normalizeMemoryPayload(
  payload
) {
  if (
    payload?.service !== "memory" ||
    !Array.isArray(payload?.items)
  ) {
    throw new Error(
      "Memory response was invalid."
    );
  }

  const items =
    payload.items.map(
      normalizeMemoryItem
    );

  if (items.length > 20) {
    throw new Error(
      "Memory response was invalid."
    );
  }

  return {
    service: "memory",
    items,
    returned: items.length,
    limit: Number(
      payload?.limit || 0
    ),
  };
}


export async function getMemory(
  credential,
  {
    limit = 6,
    signal,
  } = {}
) {
  const token =
    memoryCredential(
      credential
    );

  const resolvedLimit =
    Number(limit);

  if (
    !Number.isInteger(
      resolvedLimit
    ) ||
    resolvedLimit < 1 ||
    resolvedLimit > 20
  ) {
    throw new Error(
      "Memory limit is invalid."
    );
  }

  try {
    const response =
      await api.get(
        "/memory",
        {
          signal,
          params: {
            limit:
              resolvedLimit,
          },
          headers: {
            Authorization:
              `Bearer ${token}`,
          },
        }
      );

    return normalizeMemoryPayload(
      response.data
    );
  } catch (requestError) {
    if (
      requestError?.message ===
        "Memory response was invalid." ||
      requestError?.message ===
        "Memory limit is invalid."
    ) {
      throw requestError;
    }

    throw memoryRequestError(
      requestError
    );
  }
}


export async function clearMemory(
  credential,
  {
    signal,
  } = {}
) {
  const token =
    memoryCredential(
      credential
    );

  try {
    const response =
      await api.delete(
        "/memory",
        {
          signal,
          headers: {
            Authorization:
              `Bearer ${token}`,
          },
        }
      );

    if (
      response?.data?.service !==
        "memory" ||
      response?.data?.cleared !==
        true
    ) {
      throw new Error(
        "Memory response was invalid."
      );
    }

    return {
      service: "memory",
      cleared: true,
      message: String(
        response.data.message || ""
      ),
    };
  } catch (requestError) {
    if (
      requestError?.message ===
      "Memory response was invalid."
    ) {
      throw requestError;
    }

    throw memoryRequestError(
      requestError
    );
  }
}
