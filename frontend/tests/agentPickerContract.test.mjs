import assert from "node:assert/strict";
import {
  readFile,
} from "node:fs/promises";
import test from "node:test";

import {
  buildChatPayload,
  normalizeAgentCatalog,
} from "../src/utils/agentChat.js";


const root = new URL("../", import.meta.url);

async function source(relativePath) {
  return readFile(
    new URL(relativePath, root),
    "utf8"
  );
}


test(
  "legacy payload omits agent_id",
  () => {
    const payload = buildChatPayload({
      message: "hello",
      chatId: 7,
      modelId: "model-a",
      agentId: "",
    });

    assert.deepEqual(payload, {
      message: "hello",
      chat_id: 7,
      model_id: "model-a",
    });

    assert.equal(
      Object.hasOwn(
        payload,
        "agent_id"
      ),
      false
    );
  }
);


test(
  "explicit payload includes normalized agent_id",
  () => {
    const payload = buildChatPayload({
      message: "debug this",
      chatId: 9,
      modelId: null,
      agentId: "  coding  ",
    });

    assert.equal(
      payload.agent_id,
      "coding"
    );
  }
);


test(
  "catalog normalization preserves safe server order",
  () => {
    const catalog =
      normalizeAgentCatalog([
        {
          agent_id: "study",
          name: "Study",
          description: "Study help",
          capabilities: [
            "notes",
            " revision ",
          ],
        },
        {
          agent_id: "",
          name: "Invalid",
          description: "Ignored",
          capabilities: [],
        },
        {
          agent_id: "coding",
          name: "Coding",
          description: "Coding help",
          capabilities: [
            "debugging",
          ],
        },
      ]);

    assert.deepEqual(
      catalog.map(
        (agent) => agent.agent_id
      ),
      [
        "study",
        "coding",
      ]
    );

    assert.deepEqual(
      catalog[0].capabilities,
      [
        "notes",
        "revision",
      ]
    );
  }
);


test(
  "chat service wires catalog and both chat transports",
  async () => {
    const service =
      await source(
        "src/services/chatService.js"
      );

    assert.match(
      service,
      /export const getAgents = \(\) =>\s+api\.get\("\/agents"\);/
    );

    assert.match(
      service,
      /export const sendChat = \([\s\S]*?buildChatPayload\(\{[\s\S]*?agentId,[\s\S]*?\}\)/
    );

    assert.match(
      service,
      /export async function streamChat\([\s\S]*?buildChatPayload\(\{[\s\S]*?agentId,[\s\S]*?\}\)/
    );
  }
);


test(
  "useChat captures agent choice for streaming retry",
  async () => {
    const hook =
      await source(
        "src/hooks/useChat.js"
      );

    assert.match(
      hook,
      /await getAgents\(\)/
    );

    assert.match(
      hook,
      /agentId: requestAgentId/
    );

    assert.match(
      hook,
      /requestPayload\.agentId\s*\n\s*\);/
    );

    assert.match(
      hook,
      /lastFailedRequestRef\.current = \{\s*\n\s*\.\.\.requestPayload/
    );

    assert.equal(
      hook.includes("sendChat("),
      false
    );
  }
);


test(
  "agent state flows to a server-driven picker",
  async () => {
    const [
      app,
      chatWindow,
      messageInput,
      packageJson,
    ] = await Promise.all([
      source("src/App.jsx"),
      source(
        "src/components/Chat/ChatWindow.jsx"
      ),
      source(
        "src/components/Chat/MessageInput.jsx"
      ),
      source("package.json"),
    ]);

    assert.match(
      app,
      /selectedAgentId/
    );

    assert.match(
      chatWindow,
      /onAgentChange=\{onAgentChange\}/
    );

    assert.match(
      messageInput,
      /agents\.map\(\(agent\) =>/
    );

    assert.match(
      messageInput,
      /Automatic \(no agent\)/
    );

    assert.match(
      messageInput,
      /\{agent\.name\}/
    );

    assert.match(
      messageInput,
      /selectedAgent\.description/
    );

    const manifest =
      JSON.parse(packageJson);

    assert.equal(
      manifest.scripts[
        "test:agent-picker"
      ],
      "node --test ./tests/agentPickerContract.test.mjs"
    );
  }
);
