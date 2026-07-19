import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildBranchMergeRequest,
  buildCanonicalMergeUnits,
  createPendingBranchMerge,
  evaluateCanonicalMergeSelection,
  getBranchMergeFailurePolicy,
  getMergedMessageNavigationTarget,
  isCompletedBranchMergeResponse,
  parsePendingBranchMerge,
  pendingMatchesPreview,
  selectedKeysFromPending,
  shouldKeepPendingMerge,
} from "../src/utils/branchMerge.js";


function comparisonFixture(messageCount = 2) {
  const messageIds = Array.from(
    { length: messageCount },
    (_, index) => index + 11
  );

  return {
    comparable: true,
    parent_chat: {
      id: 1,
      title: "Parent title",
    },
    branch_chat: {
      id: 2,
      title: "Branch title",
    },
    branched_from_message_id: 8,
    branch_message_id: 10,
    branch_source_message: {
      id: 10,
      role: "user",
      content: "Source content",
    },
    branch_only_messages: messageIds.map(
      (id, index) => ({
        id,
        role: index === 0 ? "user" : "assistant",
        content: `Message ${id}`,
      })
    ),
    parent_only_messages: [],
    merge_preview: {
      version: 1,
      preview_token: "a".repeat(64),
      expected_parent_last_message_id: 9,
      expected_branch_last_message_id:
        messageIds.at(-1),
      turns: [
        {
          turn_key: "turn:11",
          type: "turn",
          selectable: true,
          anchor_message_id: 11,
          message_ids: messageIds,
          reason: null,
        },
        {
          turn_key: "locked:99",
          type: "locked",
          selectable: false,
          anchor_message_id: null,
          message_ids: [99],
          reason: "orphan_messages",
        },
      ],
    },
  };
}


function canonicalSelectionFixture({
  messages,
  turn,
  parentOnlyMessages = [],
}) {
  const comparison = comparisonFixture(1);

  comparison.branch_only_messages = messages;
  comparison.parent_only_messages =
    parentOnlyMessages;
  comparison.merge_preview.expected_branch_last_message_id =
    messages.at(-1)?.id ||
    comparison.branch_message_id;
  comparison.merge_preview.turns = [turn];

  return comparison;
}


function requestFixture(comparison = comparisonFixture()) {
  return buildBranchMergeRequest({
    comparison,
    selectedTurnKeys: new Set(["turn:11"]),
    uuidFactory: () =>
      "00000000-0000-4000-8000-000000000001",
  });
}


test("request contains only strict allowed fields", () => {
  const request = requestFixture();

  assert.deepEqual(Object.keys(request), [
    "idempotency_key",
    "preview_token",
    "expected",
    "selected_turns",
  ]);
  assert.deepEqual(Object.keys(request.expected), [
    "parent_chat_id",
    "branched_from_message_id",
    "branch_message_id",
    "parent_last_message_id",
    "branch_last_message_id",
  ]);
  assert.deepEqual(Object.keys(request.selected_turns[0]), [
    "turn_key",
    "message_ids",
  ]);
});


test("new request obtains its key from the UUID factory", () => {
  let callCount = 0;
  const request = buildBranchMergeRequest({
    comparison: comparisonFixture(),
    selectedTurnKeys: new Set(["turn:11"]),
    uuidFactory: () => {
      callCount += 1;
      return "00000000-0000-4000-8000-000000000002";
    },
  });

  assert.equal(callCount, 1);
  assert.equal(
    request.idempotency_key,
    "00000000-0000-4000-8000-000000000002"
  );
});


test("selected canonical server order is preserved", () => {
  const comparison = comparisonFixture();
  comparison.merge_preview.turns.unshift({
    turn_key: "turn:7",
    type: "turn",
    selectable: true,
    anchor_message_id: 7,
    message_ids: [7, 8],
    reason: null,
  });
  const request = buildBranchMergeRequest({
    comparison,
    selectedTurnKeys: new Set([
      "turn:11",
      "turn:7",
    ]),
    uuidFactory: () => "key",
  });

  assert.deepEqual(
    request.selected_turns.map((turn) => turn.turn_key),
    ["turn:7", "turn:11"]
  );
});


test("source anchor is never submitted", () => {
  const comparison = comparisonFixture(1);
  comparison.merge_preview.turns = [
    {
      turn_key: "source:10",
      type: "source",
      selectable: true,
      anchor_message_id: 10,
      message_ids: [11],
      reason: null,
    },
  ];
  const request = buildBranchMergeRequest({
    comparison,
    selectedTurnKeys: new Set(["source:10"]),
    uuidFactory: () => "key",
  });

  assert.deepEqual(
    request.selected_turns[0].message_ids,
    [11]
  );
  assert.ok(
    !request.selected_turns[0].message_ids.includes(10)
  );
});


test("nonselectable turn cannot be submitted", () => {
  assert.throws(() =>
    buildBranchMergeRequest({
      comparison: comparisonFixture(),
      selectedTurnKeys: new Set(["locked:99"]),
      uuidFactory: () => "key",
    })
  );
});


test("pending record contains no credential", () => {
  const pending = createPendingBranchMerge({
    branchChatId: 2,
    request: requestFixture(),
    selectedTurnCount: 1,
    selectedMessageCount: 2,
  });
  const serialized = JSON.stringify(pending);

  assert.ok(!serialized.includes("credential"));
  assert.ok(!serialized.includes("Authorization"));
  assert.ok(!serialized.includes("Bearer"));
});


test("pending record contains no content or title data", () => {
  const pending = createPendingBranchMerge({
    branchChatId: 2,
    request: requestFixture(),
    selectedTurnCount: 1,
    selectedMessageCount: 2,
  });
  const serialized = JSON.stringify(pending);

  assert.ok(!serialized.includes("Parent title"));
  assert.ok(!serialized.includes("Branch title"));
  assert.ok(!serialized.includes("Source content"));
  assert.ok(!serialized.includes("Message 11"));
});


test("same-key retry reuses the exact pending request", () => {
  const request = requestFixture();
  const pending = createPendingBranchMerge({
    branchChatId: 2,
    request,
    selectedTurnCount: 1,
    selectedMessageCount: 2,
  });

  assert.strictEqual(pending.request, request);
  assert.equal(
    pending.request.idempotency_key,
    request.idempotency_key
  );
});


test("401 preserves pending request policy", () => {
  const policy = getBranchMergeFailurePolicy({
    status: 401,
  });

  assert.equal(policy.keepPending, true);
  assert.equal(policy.clearCredential, true);
  assert.equal(policy.automaticRetry, false);
});


test("network, 500, and 503 preserve pending policy", () => {
  assert.equal(shouldKeepPendingMerge({}), true);
  assert.equal(shouldKeepPendingMerge({ status: 500 }), true);
  assert.equal(shouldKeepPendingMerge({ status: 503 }), true);
});


test("success and replay responses are definite completion", () => {
  assert.equal(
    isCompletedBranchMergeResponse({
      status: "completed",
      replayed: false,
      operation_id: 1,
    }),
    true
  );
  assert.equal(
    isCompletedBranchMergeResponse({
      status: "completed",
      replayed: true,
      operation_id: 1,
    }),
    true
  );
});


test("stale preview does not preserve pending policy", () => {
  const policy = getBranchMergeFailurePolicy({
      status: 409,
      code: "STALE_PREVIEW",
  });

  assert.equal(policy.keepPending, false);
  assert.equal(policy.clearSelection, true);
  assert.equal(policy.refreshPreview, true);
  assert.equal(policy.automaticRetry, false);
});


test("mismatched restored preview is discarded", () => {
  const comparison = comparisonFixture();
  const pending = createPendingBranchMerge({
    branchChatId: 2,
    request: requestFixture(comparison),
    selectedTurnCount: 1,
    selectedMessageCount: 2,
  });
  comparison.merge_preview.preview_token = "b".repeat(64);

  assert.equal(
    parsePendingBranchMerge(
      JSON.stringify(pending),
      2,
      comparison
    ),
    null
  );
});


test("matching restored preview can be resumed", () => {
  const comparison = comparisonFixture();
  const pending = createPendingBranchMerge({
    branchChatId: 2,
    request: requestFixture(comparison),
    selectedTurnCount: 1,
    selectedMessageCount: 2,
  });
  const restored = parsePendingBranchMerge(
    JSON.stringify(pending),
    2,
    comparison
  );

  assert.ok(restored);
  assert.equal(
    selectedKeysFromPending(restored).has("turn:11"),
    true
  );
});


test("completed conflict is not eligible for automatic retry", () => {
  const policy = getBranchMergeFailurePolicy({
      status: 409,
      code: "MERGE_ALREADY_COMPLETED",
  });

  assert.equal(policy.keepPending, false);
  assert.equal(policy.automaticRetry, false);
});


test("more than one thousand canonical IDs are preserved", () => {
  const comparison = comparisonFixture(1001);
  const request = requestFixture(comparison);

  assert.equal(
    request.selected_turns[0].message_ids.length,
    1001
  );
  assert.equal(
    request.selected_turns[0].message_ids.at(-1),
    1011
  );
});


test("navigation chooses first created ID for at most 1000", () => {
  assert.equal(
    getMergedMessageNavigationTarget({
      inserted_message_count: 1000,
      first_created_parent_message_id: 30,
      last_created_parent_message_id: 1029,
    }),
    30
  );
});


test("navigation chooses last created ID above 1000", () => {
  assert.equal(
    getMergedMessageNavigationTarget({
      inserted_message_count: 1001,
      first_created_parent_message_id: 30,
      last_created_parent_message_id: 1030,
    }),
    1030
  );
});


test("canonical units keep locked turns unselectable", () => {
  const units = buildCanonicalMergeUnits(
    comparisonFixture()
  );

  assert.equal(units[1].selectable, false);
});


test("canonical user and assistant turn can reach confirmation", () => {
  const comparison = canonicalSelectionFixture({
    messages: [
      {
        id: 223,
        role: "user",
        content: "Canonical prompt",
      },
      {
        id: 224,
        role: "assistant",
        content: "Canonical answer",
      },
    ],
    turn: {
      turn_key: "user:223",
      type: "turn",
      selectable: true,
      anchor_message_id: 223,
      message_ids: [223, 224],
      reason: null,
    },
  });
  const evaluation =
    evaluateCanonicalMergeSelection(
      comparison,
      new Set(["user:223"])
    );
  const request = buildBranchMergeRequest({
    comparison,
    selectedTurnKeys: new Set(["user:223"]),
    uuidFactory: () =>
      "00000000-0000-4000-8000-000000000010",
  });

  assert.equal(evaluation.units[0].selectable, true);
  assert.equal(evaluation.units[0].anchor.id, 223);
  assert.equal(evaluation.units[0].anchor.role, "user");
  assert.deepEqual(evaluation.blocking, []);
  assert.equal(evaluation.canEnterConfirmation, true);
  assert.deepEqual(
    request.selected_turns[0].message_ids,
    [223, 224]
  );
});


test("canonical user system assistant turn has no orphan blocker", () => {
  const comparison = canonicalSelectionFixture({
    messages: [
      {
        id: 223,
        role: "user",
        content: "Canonical prompt",
      },
      {
        id: 224,
        role: "system",
        content: "Canonical system context",
      },
      {
        id: 225,
        role: "assistant",
        content: "Canonical answer",
      },
    ],
    turn: {
      turn_key: "user:223",
      type: "turn",
      selectable: true,
      anchor_message_id: 223,
      message_ids: [223, 224, 225],
      reason: null,
    },
  });
  const evaluation =
    evaluateCanonicalMergeSelection(
      comparison,
      new Set(["user:223"])
    );

  assert.deepEqual(evaluation.blocking, []);
  assert.equal(evaluation.canEnterConfirmation, true);
});


test("canonical source continuation excludes prompt without orphan blocker", () => {
  const comparison = canonicalSelectionFixture({
    messages: [
      {
        id: 223,
        role: "system",
        content: "Source continuation context",
      },
      {
        id: 224,
        role: "assistant",
        content: "Source continuation answer",
      },
    ],
    turn: {
      turn_key: "source:10",
      type: "source",
      selectable: true,
      anchor_message_id: 10,
      message_ids: [223, 224],
      reason: null,
    },
  });
  const evaluation =
    evaluateCanonicalMergeSelection(
      comparison,
      new Set(["source:10"])
    );
  const request = buildBranchMergeRequest({
    comparison,
    selectedTurnKeys: new Set(["source:10"]),
    uuidFactory: () =>
      "00000000-0000-4000-8000-000000000011",
  });

  assert.equal(evaluation.units[0].anchor.id, 10);
  assert.deepEqual(evaluation.blocking, []);
  assert.equal(evaluation.canEnterConfirmation, true);
  assert.deepEqual(
    request.selected_turns[0].message_ids,
    [223, 224]
  );
  assert.ok(
    !request.selected_turns[0].message_ids.includes(10)
  );
});


test("canonical locked orphan unit remains non-executable", () => {
  const comparison = canonicalSelectionFixture({
    messages: [
      {
        id: 223,
        role: "assistant",
        content: "Orphan answer",
      },
      {
        id: 224,
        role: "system",
        content: "Orphan system context",
      },
    ],
    turn: {
      turn_key: "locked:orphan:223",
      type: "locked",
      selectable: false,
      anchor_message_id: null,
      message_ids: [223, 224],
      reason: "orphan_messages",
    },
  });
  const evaluation =
    evaluateCanonicalMergeSelection(
      comparison,
      new Set(["locked:orphan:223"])
    );

  assert.equal(evaluation.units[0].selectable, false);
  assert.equal(evaluation.selectedUnits.length, 0);
  assert.ok(
    evaluation.blocking.some((issue) =>
      issue.id.startsWith("selected-unit-locked:")
    )
  );
  assert.equal(evaluation.canEnterConfirmation, false);
  assert.throws(() =>
    buildBranchMergeRequest({
      comparison,
      selectedTurnKeys: new Set([
        "locked:orphan:223",
      ]),
      uuidFactory: () => "unused",
    })
  );
});


test("duplicate parent content warns without blocking confirmation", () => {
  const comparison = canonicalSelectionFixture({
    messages: [
      {
        id: 223,
        role: "user",
        content: "Canonical prompt",
      },
      {
        id: 224,
        role: "assistant",
        content: "Duplicate answer",
      },
    ],
    parentOnlyMessages: [
      {
        id: 90,
        role: "assistant",
        content: "Duplicate answer",
      },
    ],
    turn: {
      turn_key: "user:223",
      type: "turn",
      selectable: true,
      anchor_message_id: 223,
      message_ids: [223, 224],
      reason: null,
    },
  });
  const evaluation =
    evaluateCanonicalMergeSelection(
      comparison,
      new Set(["user:223"])
    );

  assert.ok(
    evaluation.warning.some(
      (issue) =>
        issue.id === "duplicate-parent-content"
    )
  );
  assert.deepEqual(evaluation.blocking, []);
  assert.equal(evaluation.canEnterConfirmation, true);
});


test("empty canonical selection still blocks confirmation", () => {
  const evaluation =
    evaluateCanonicalMergeSelection(
      comparisonFixture(),
      new Set()
    );

  assert.ok(
    evaluation.blocking.some(
      (issue) => issue.id === "empty-selection"
    )
  );
  assert.equal(evaluation.canEnterConfirmation, false);
});


test("missing merge preview keeps execution disabled", () => {
  const comparison = comparisonFixture();
  comparison.merge_preview = null;
  const evaluation =
    evaluateCanonicalMergeSelection(
      comparison,
      new Set(["turn:11"])
    );

  assert.ok(
    evaluation.blocking.some(
      (issue) =>
        issue.id === "missing-merge-preview"
    )
  );
  assert.equal(evaluation.canEnterConfirmation, false);
  assert.throws(() =>
    buildBranchMergeRequest({
      comparison,
      selectedTurnKeys: new Set(["turn:11"]),
      uuidFactory: () => "unused",
    })
  );
});


test("selected canonical unit mismatch blocks execution", () => {
  const comparison = comparisonFixture();
  const evaluation =
    evaluateCanonicalMergeSelection(
      comparison,
      new Set(["user:missing"])
    );

  assert.ok(
    evaluation.blocking.some((issue) =>
      issue.id.startsWith("selected-unit-mismatch:")
    )
  );
  assert.equal(evaluation.canEnterConfirmation, false);
  assert.throws(() =>
    buildBranchMergeRequest({
      comparison,
      selectedTurnKeys: new Set(["user:missing"]),
      uuidFactory: () => "unused",
    })
  );
});


test("pending compatibility rejects extra serialized fields", () => {
  const comparison = comparisonFixture();
  const pending = {
    ...createPendingBranchMerge({
      branchChatId: 2,
      request: requestFixture(comparison),
      selectedTurnCount: 1,
      selectedMessageCount: 2,
    }),
    credential: "must-not-exist",
  };

  assert.equal(
    pendingMatchesPreview(pending, 2, comparison),
    false
  );
});


test("chat service does not mutate global authorization defaults", async () => {
  const source = await readFile(
    new URL(
      "../src/services/chatService.js",
      import.meta.url
    ),
    "utf8"
  );

  assert.ok(!source.includes("api.defaults.headers"));
  assert.ok(!source.includes("axios.defaults.headers"));
  assert.ok(source.includes("Authorization:"));
});


test("production request generation uses crypto randomUUID", async () => {
  const source = await readFile(
    new URL(
      "../src/utils/branchMerge.js",
      import.meta.url
    ),
    "utf8"
  );

  assert.ok(
    source.includes("globalThis.crypto.randomUUID()")
  );
  assert.ok(!source.includes("Math.random()"));
});
