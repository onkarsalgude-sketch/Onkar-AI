import assert from "node:assert/strict";
import {
  readFile,
} from "node:fs/promises";
import test from "node:test";

import {
  normalizeAgentCatalog,
  resolveAgentBadge,
} from "../src/utils/agentChat.js";


const root = new URL("../", import.meta.url);


async function source(relativePath) {
  return readFile(
    new URL(relativePath, root),
    "utf8"
  );
}


test(
  "known catalog agent resolves to a safe badge",
  () => {
    const catalog = normalizeAgentCatalog([
      {
        agent_id: "study",
        name: "Study",
        description: "Study help",
        capabilities: [],
      },
    ]);

    assert.deepEqual(
      resolveAgentBadge(
        " study ",
        catalog
      ),
      {
        agent_id: "study",
        name: "Study",
      }
    );
  }
);


test(
  "legacy and stale agents do not create fake badges",
  () => {
    const catalog = normalizeAgentCatalog([
      {
        agent_id: "coding",
        name: "Coding",
        description: "Coding help",
        capabilities: [],
      },
    ]);

    assert.equal(
      resolveAgentBadge(null, catalog),
      null
    );

    assert.equal(
      resolveAgentBadge("", catalog),
      null
    );

    assert.equal(
      resolveAgentBadge(
        "removed-agent",
        catalog
      ),
      null
    );
  }
);


test(
  "history metadata reaches assistant Message badge",
  async () => {
    const [
      useChats,
      chatWindow,
      message,
    ] = await Promise.all([
      source("src/hooks/useChats.js"),
      source(
        "src/components/Chat/ChatWindow.jsx"
      ),
      source(
        "src/components/Chat/Message.jsx"
      ),
    ]);

    assert.match(
      useChats,
      /agentId:\s*\n\s*message\.agent_id \?\?\s*\n\s*message\.agentId \?\?\s*\n\s*null/
    );

    assert.match(
      chatWindow,
      /resolveAgentBadge\(\s*\n\s*message\.agentId,\s*\n\s*agents\s*\n\s*\)\?\.name/
    );

    assert.match(
      chatWindow,
      /agentName=\{\s*\n\s*message\.role === "assistant"/
    );

    assert.match(
      message,
      /agentName = null/
    );

    assert.match(
      message,
      /!isUser &&\s*\n\s*agentName &&/
    );

    assert.match(
      message,
      /aria-label=\{`Agent: \$\{agentName\}`\}/
    );
  }
);


test(
  "stream metadata converges on agentId",
  async () => {
    const [
      service,
      hook,
    ] = await Promise.all([
      source("src/services/chatService.js"),
      source("src/hooks/useChat.js"),
    ]);

    assert.match(
      service,
      /response\.headers\.get\(\s*\n\s*"X-Agent-Id"\s*\n\s*\)/
    );

    assert.match(
      service,
      /agentId: returnedAgentId/
    );

    assert.match(
      hook,
      /agentId:\s*\n\s*result\?\.agentId \|\|\s*\n\s*requestPayload\.agentId \|\|\s*\n\s*null/
    );

    assert.match(
      hook,
      /agentId:\s*\n\s*result\?\.agentId \|\|\s*\n\s*originalAgentId \|\|\s*\n\s*null/
    );
  }
);
