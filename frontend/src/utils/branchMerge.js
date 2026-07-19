export const BRANCH_MERGE_PENDING_KEY =
  "onkar-ai:branch-merge:pending:v1";


export function toPositiveBranchMergeId(value) {
  const numericValue = Number(value);

  return Number.isInteger(numericValue) &&
    numericValue > 0
    ? numericValue
    : null;
}


function freezeDeep(value) {
  if (
    value === null ||
    typeof value !== "object" ||
    Object.isFrozen(value)
  ) {
    return value;
  }

  Object.freeze(value);

  for (const nestedValue of Object.values(value)) {
    freezeDeep(nestedValue);
  }

  return value;
}


function canonicalTurnIds(turn) {
  if (!Array.isArray(turn?.message_ids)) {
    return null;
  }

  const messageIds = turn.message_ids.map(
    toPositiveBranchMergeId
  );

  if (
    messageIds.some((id) => id === null) ||
    new Set(messageIds).size !== messageIds.length
  ) {
    return null;
  }

  return messageIds;
}


function reasonLabel(reason) {
  const labels = {
    already_merged:
      "This canonical turn was already merged into the immediate parent.",
    incomplete_turn:
      "This incomplete turn is locked by the server.",
    orphan_messages:
      "These messages have no safe canonical user anchor.",
    unknown_role:
      "This unit contains a role that cannot be merged safely.",
    duplicate_id:
      "This unit has duplicate message identity and is locked.",
    invalid_id:
      "This unit has invalid message identity and is locked.",
  };

  return labels[reason] ||
    (reason
      ? `This canonical unit is locked (${reason}).`
      : null);
}


export function buildCanonicalMergeUnits(comparison) {
  const preview = comparison?.merge_preview;
  const serverTurns = Array.isArray(preview?.turns)
    ? preview.turns
    : [];
  const branchMessages = Array.isArray(
    comparison?.branch_only_messages
  )
    ? comparison.branch_only_messages
    : [];
  const messagesById = new Map();

  for (const message of branchMessages) {
    const id = toPositiveBranchMergeId(
      message?.id
    );

    if (id === null) continue;

    const records = messagesById.get(id) || [];
    records.push({
      ...message,
      id,
    });
    messagesById.set(id, records);
  }

  const branchSource =
    comparison?.branch_source_message || null;

  return serverTurns.map((turn, index) => {
    const turnKey =
      typeof turn?.turn_key === "string" &&
      turn.turn_key.length > 0
        ? turn.turn_key
        : `invalid-canonical-turn:${index}`;
    const messageIds = canonicalTurnIds(turn);
    const messages = [];
    let hasExactMessages = messageIds !== null;

    for (const messageId of messageIds || []) {
      const records = messagesById.get(messageId);

      if (!records || records.length !== 1) {
        hasExactMessages = false;
        continue;
      }

      messages.push(records[0]);
    }

    const anchorId = toPositiveBranchMergeId(
      turn?.anchor_message_id
    );
    const isSourceUnit = turn?.type === "source";
    const sourceId = toPositiveBranchMergeId(
      comparison?.branch_message_id
    );
    const sourceAnchorIsExact =
      !isSourceUnit ||
      (
        anchorId !== null &&
        sourceId === anchorId &&
        toPositiveBranchMergeId(
          branchSource?.id
        ) === anchorId &&
        branchSource?.role === "user" &&
        !messageIds?.includes(anchorId)
      );
    const turnAnchor =
      turn?.type === "turn" &&
      anchorId !== null &&
      messageIds?.[0] === anchorId
        ? messages.find(
            (message) =>
              message.id === anchorId
          ) || null
        : null;
    const selectable =
      turn?.selectable === true &&
      turn?.type !== "locked" &&
      messageIds !== null &&
      messageIds.length > 0 &&
      hasExactMessages &&
      sourceAnchorIsExact;
    const serverReason = reasonLabel(turn?.reason);
    const localReason = selectable
      ? null
      : serverReason ||
        "This canonical unit cannot be selected because its exact message identity is unavailable.";

    return {
      key: turnKey,
      type: ["source", "turn", "locked"].includes(
        turn?.type
      )
        ? turn.type
        : "locked",
      selectable,
      anchor:
        isSourceUnit && sourceAnchorIsExact
          ? {
              ...branchSource,
              id: anchorId,
            }
          : turnAnchor,
      messages,
      messageIds: messageIds || [],
      reason: localReason,
      canonicalIndex: index,
    };
  });
}


export function evaluateCanonicalMergeSelection(
  comparison,
  selectedTurnKeys
) {
  const preview = comparison?.merge_preview;
  const serverTurns = Array.isArray(preview?.turns)
    ? preview.turns
    : [];
  const units = preview
    ? buildCanonicalMergeUnits(comparison)
    : [];
  const selectedKeys = new Set(
    selectedTurnKeys || []
  );
  const blocking = [];
  const warning = [];
  const selectedUnits = [];
  const unitsByKey = new Map(
    units.map((unit) => [unit.key, unit])
  );
  const serverTurnsByKey = new Map();

  for (const serverTurn of serverTurns) {
    const turnKey = serverTurn?.turn_key;
    const matchingTurns =
      serverTurnsByKey.get(turnKey) || [];

    matchingTurns.push(serverTurn);
    serverTurnsByKey.set(
      turnKey,
      matchingTurns
    );
  }

  if (!preview || !Array.isArray(preview.turns)) {
    blocking.push({
      id: "missing-merge-preview",
      message:
        "A fresh server-provided merge-capable preview is unavailable. Execution is disabled.",
    });
  }

  if (selectedKeys.size === 0) {
    blocking.push({
      id: "empty-selection",
      message:
        "Nothing is selected. Select at least one eligible conversation turn to build a preview.",
    });
  }

  for (const selectedKey of selectedKeys) {
    const matchingServerTurns =
      serverTurnsByKey.get(selectedKey) || [];
    const unit = unitsByKey.get(selectedKey);

    if (matchingServerTurns.length !== 1 || !unit) {
      blocking.push({
        id: `selected-unit-mismatch:${selectedKey}`,
        message:
          "A selected canonical unit no longer matches the current server preview.",
      });
      continue;
    }

    const serverTurn = matchingServerTurns[0];

    if (
      serverTurn.selectable !== true ||
      unit.selectable !== true
    ) {
      blocking.push({
        id: `selected-unit-locked:${selectedKey}`,
        message:
          "A selected canonical unit is locked by the server and cannot be executed.",
      });
      continue;
    }

    if (
      JSON.stringify(unit.messageIds) !==
      JSON.stringify(serverTurn.message_ids)
    ) {
      blocking.push({
        id: `selected-unit-mismatch:${selectedKey}`,
        message:
          "A selected canonical unit no longer matches the current server preview.",
      });
      continue;
    }

    selectedUnits.push(unit);
  }

  selectedUnits.sort(
    (left, right) =>
      left.canonicalIndex - right.canonicalIndex
  );

  const selectedMessages = selectedUnits
    .flatMap((unit) => unit.messages)
    .slice()
    .sort(
      (left, right) =>
        toPositiveBranchMergeId(left.id) -
        toPositiveBranchMergeId(right.id)
    );
  const selectedIdCounts = new Map();

  for (const message of selectedMessages) {
    const id = toPositiveBranchMergeId(message?.id);

    if (id === null) {
      blocking.push({
        id:
          "invalid-selected-id:" +
          blocking.length,
        message:
          "A selected message has a missing or nonpositive ID.",
      });
      continue;
    }

    selectedIdCounts.set(
      id,
      (selectedIdCounts.get(id) || 0) + 1
    );
  }

  for (const [id, count] of selectedIdCounts) {
    if (count > 1) {
      blocking.push({
        id: "duplicate-selected-id:" + id,
        message:
          "Multiple selected messages share message ID " +
          id +
          ".",
      });
    }
  }

  const parentContentKeys = new Set(
    (
      comparison?.parent_only_messages || []
    ).map((message) =>
      JSON.stringify([
        message?.role,
        message?.content,
      ])
    )
  );
  const duplicateContentCount =
    selectedMessages.filter((message) =>
      parentContentKeys.has(
        JSON.stringify([
          message?.role,
          message?.content,
        ])
      )
    ).length;

  if (duplicateContentCount > 0) {
    warning.push({
      id: "duplicate-parent-content",
      message:
        duplicateContentCount +
        " selected message(s) have the same raw role and content as a parent-only message. They remain separate and selected.",
    });
  }

  return {
    units,
    selectedUnits,
    selectedMessages,
    blocking,
    warning,
    canEnterConfirmation:
      Boolean(preview) &&
      selectedUnits.length > 0 &&
      blocking.length === 0,
  };
}


function requirePositiveId(value, fieldName) {
  const id = toPositiveBranchMergeId(value);

  if (id === null) {
    throw new Error(
      `Missing authoritative ${fieldName}.`
    );
  }

  return id;
}


export function buildBranchMergeRequest({
  comparison,
  selectedTurnKeys,
  uuidFactory = () => globalThis.crypto.randomUUID(),
}) {
  const preview = comparison?.merge_preview;

  if (!preview || !Array.isArray(preview.turns)) {
    throw new Error(
      "A fresh merge-capable preview is unavailable."
    );
  }

  if (
    !/^[0-9a-f]{64}$/.test(
      String(preview.preview_token || "")
    )
  ) {
    throw new Error(
      "The authoritative preview token is invalid."
    );
  }

  const selectedKeys = new Set(selectedTurnKeys || []);

  if (selectedKeys.size === 0) {
    throw new Error(
      "Select at least one canonical turn."
    );
  }

  const selectedTurns = [];
  const seenKeys = new Set();

  for (const turn of preview.turns) {
    const turnKey = turn?.turn_key;

    if (!selectedKeys.has(turnKey)) continue;

    const messageIds = canonicalTurnIds(turn);
    const anchorId = toPositiveBranchMergeId(
      turn?.anchor_message_id
    );

    if (
      typeof turnKey !== "string" ||
      !turnKey ||
      seenKeys.has(turnKey) ||
      turn?.selectable !== true ||
      messageIds === null ||
      messageIds.length === 0 ||
      (
        turn?.type === "source" &&
        anchorId !== null &&
        messageIds.includes(anchorId)
      )
    ) {
      throw new Error(
        "A selected canonical turn is not executable."
      );
    }

    seenKeys.add(turnKey);
    selectedTurns.push({
      turn_key: turnKey,
      message_ids: [...messageIds],
    });
  }

  if (seenKeys.size !== selectedKeys.size) {
    throw new Error(
      "A selected canonical turn is no longer available."
    );
  }

  const idempotencyKey = uuidFactory();

  if (
    typeof idempotencyKey !== "string" ||
    idempotencyKey.length === 0
  ) {
    throw new Error(
      "A secure idempotency key could not be generated."
    );
  }

  return freezeDeep({
    idempotency_key: idempotencyKey,
    preview_token: String(
      preview.preview_token || ""
    ),
    expected: {
      parent_chat_id: requirePositiveId(
        comparison?.parent_chat?.id,
        "parent chat ID"
      ),
      branched_from_message_id: requirePositiveId(
        comparison?.branched_from_message_id,
        "parent boundary"
      ),
      branch_message_id: requirePositiveId(
        comparison?.branch_message_id,
        "branch boundary"
      ),
      parent_last_message_id: requirePositiveId(
        preview.expected_parent_last_message_id,
        "parent snapshot"
      ),
      branch_last_message_id: requirePositiveId(
        preview.expected_branch_last_message_id,
        "branch snapshot"
      ),
    },
    selected_turns: selectedTurns,
  });
}


export function createPendingBranchMerge({
  branchChatId,
  request,
  selectedTurnCount,
  selectedMessageCount,
  createdAt = new Date().toISOString(),
}) {
  return freezeDeep({
    branch_chat_id: requirePositiveId(
      branchChatId,
      "branch chat ID"
    ),
    request,
    created_at: createdAt,
    counts: {
      selected_turns: Number(selectedTurnCount) || 0,
      selected_messages:
        Number(selectedMessageCount) || 0,
    },
  });
}


function hasExactKeys(value, expectedKeys) {
  if (
    value === null ||
    typeof value !== "object" ||
    Array.isArray(value)
  ) {
    return false;
  }

  const actualKeys = Object.keys(value).sort();
  const sortedExpected = [...expectedKeys].sort();

  return JSON.stringify(actualKeys) ===
    JSON.stringify(sortedExpected);
}


export function pendingMatchesPreview(
  pending,
  branchChatId,
  comparison
) {
  if (
    !hasExactKeys(pending, [
      "branch_chat_id",
      "request",
      "created_at",
      "counts",
    ]) ||
    toPositiveBranchMergeId(
      pending.branch_chat_id
    ) !== toPositiveBranchMergeId(branchChatId)
  ) {
    return false;
  }

  const request = pending.request;
  const expected = request?.expected;
  const preview = comparison?.merge_preview;
  const counts = pending.counts;

  if (
    !hasExactKeys(request, [
      "idempotency_key",
      "preview_token",
      "expected",
      "selected_turns",
    ]) ||
    !hasExactKeys(expected, [
      "parent_chat_id",
      "branched_from_message_id",
      "branch_message_id",
      "parent_last_message_id",
      "branch_last_message_id",
    ]) ||
    !hasExactKeys(counts, [
      "selected_turns",
      "selected_messages",
    ]) ||
    typeof pending.created_at !== "string" ||
    typeof request.idempotency_key !== "string" ||
    !request.idempotency_key ||
    !preview ||
    !/^[0-9a-f]{64}$/.test(
      String(request.preview_token || "")
    ) ||
    request.preview_token !== preview.preview_token ||
    expected.parent_chat_id !== comparison?.parent_chat?.id ||
    expected.branched_from_message_id !==
      comparison?.branched_from_message_id ||
    expected.branch_message_id !==
      comparison?.branch_message_id ||
    expected.parent_last_message_id !==
      preview.expected_parent_last_message_id ||
    expected.branch_last_message_id !==
      preview.expected_branch_last_message_id ||
    !Array.isArray(preview.turns) ||
    !Array.isArray(request.selected_turns) ||
    request.selected_turns.length === 0
  ) {
    return false;
  }

  const canonicalByKey = new Map(
    preview.turns
      .filter((turn) => turn?.selectable === true)
      .map((turn) => [turn.turn_key, turn])
  );
  const executableUnitKeys = new Set(
    buildCanonicalMergeUnits(comparison)
      .filter((unit) => unit.selectable)
      .map((unit) => unit.key)
  );
  const submittedTurnKeys = request.selected_turns.map(
    (turn) => turn?.turn_key
  );

  if (
    new Set(submittedTurnKeys).size !==
    submittedTurnKeys.length
  ) {
    return false;
  }

  return request.selected_turns.every(
    (selectedTurn) => {
      if (
        !hasExactKeys(selectedTurn, [
          "turn_key",
          "message_ids",
        ])
      ) {
        return false;
      }

      const canonicalTurn = canonicalByKey.get(
        selectedTurn.turn_key
      );

      return Boolean(
        canonicalTurn &&
        executableUnitKeys.has(
          selectedTurn.turn_key
        ) &&
        JSON.stringify(selectedTurn.message_ids) ===
          JSON.stringify(canonicalTurn.message_ids)
      );
    }
  );
}


export function parsePendingBranchMerge(
  serialized,
  branchChatId,
  comparison
) {
  if (!serialized) return null;

  try {
    const pending = JSON.parse(serialized);

    return pendingMatchesPreview(
      pending,
      branchChatId,
      comparison
    )
      ? freezeDeep(pending)
      : null;
  } catch {
    return null;
  }
}


export function selectedKeysFromPending(pending) {
  return new Set(
    pending?.request?.selected_turns?.map(
      (turn) => turn.turn_key
    ) || []
  );
}


export function getMergedMessageNavigationTarget(
  response
) {
  const messageCount = Number(
    response?.inserted_message_count
  );

  return messageCount > 1000
    ? toPositiveBranchMergeId(
        response?.last_created_parent_message_id
      )
    : toPositiveBranchMergeId(
        response?.first_created_parent_message_id
      );
}


export function shouldKeepPendingMerge(error) {
  const status = Number(error?.status) || null;

  return (
    status === null ||
    status === 401 ||
    status === 429 ||
    status === 500 ||
    status === 503
  );
}


export function getBranchMergeFailurePolicy(error) {
  const status = Number(error?.status) || null;
  const code = error?.code || null;
  const refreshPreview =
    status === 409 &&
    [
      "STALE_PREVIEW",
      "IDEMPOTENCY_KEY_REUSED",
      "MERGE_ALREADY_COMPLETED",
    ].includes(code);

  return {
    keepPending: shouldKeepPendingMerge(error),
    clearCredential: status === 401,
    clearSelection: refreshPreview,
    refreshPreview,
    automaticRetry: false,
  };
}


export function isCompletedBranchMergeResponse(response) {
  return (
    response?.status === "completed" &&
    typeof response?.replayed === "boolean" &&
    toPositiveBranchMergeId(
      response?.operation_id
    ) !== null
  );
}
