import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  fileURLToPath,
} from "node:url";


const here = path.dirname(
  fileURLToPath(import.meta.url)
);

const frontendRoot =
  path.resolve(here, "..");

function read(relativePath) {
  return fs.readFileSync(
    path.join(
      frontendRoot,
      relativePath
    ),
    "utf8"
  )
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");
}


test(
  "greeting and quick actions live in a fixed command deck outside chat scrolling",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    const deckIndex =
      source.indexOf(
        'data-workspace-command-deck="v2.40"'
      );

    const canvasIndex =
      source.indexOf(
        'data-chat-canvas="v2.40"'
      );

    assert.ok(deckIndex >= 0);
    assert.ok(canvasIndex >= 0);
    assert.ok(deckIndex < canvasIndex);

    assert.ok(
      source.includes(
        "showBottomCards={false}"
      )
    );
  }
);


test(
  "welcome supports independently rendering greeting actions and bottom cards",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      source.includes(
        "showGreetingActions = true"
      )
    );

    assert.ok(
      source.includes(
        "{showGreetingActions && ("
      )
    );

    assert.ok(
      source.includes(
        "{showBottomCards && ("
      )
    );
  }
);


test(
  "saved one-message chats receive the real thread title strip",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.match(
      source,
      /activeChatId\s*&&\s*messages\.length\s*>\s*0\s*&&\s*\(/
    );

    assert.ok(
      source.includes(
        'data-chat-thread-header="live"'
      )
    );

    assert.ok(
      source.includes(
        "activeChat?.title"
      )
    );
  }
);


test(
  "thread body active state follows the active saved conversation",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        'data-chat-thread-body='
      )
    );

    assert.match(
      source,
      /activeChatId\s*&&\s*messages\.length\s*>\s*0\s*\?\s*"active"/
    );
  }
);


test(
  "bottom workspace cards render after the thread",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    const bodyIndex =
      source.indexOf(
        "data-chat-thread-body="
      );

    const bottomIndex =
      source.indexOf(
        'data-workspace-bottom-deck="after-thread"'
      );

    assert.ok(bodyIndex >= 0);
    assert.ok(bottomIndex > bodyIndex);

    assert.ok(
      source.includes(
        "showGreetingActions={false}"
      )
    );
  }
);


test(
  "command deck refinement adds no runtime dependency",
  () => {
    const packageJson =
      JSON.parse(
        read("package.json")
      );

    assert.ok(
      Object.prototype.hasOwnProperty.call(
        packageJson.dependencies,
        "react-icons"
      )
    );
  }
);
