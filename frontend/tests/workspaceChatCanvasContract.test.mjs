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
  "chat canvas uses the compact v2.40 thread surface",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        'data-chat-canvas="v2.40"'
      )
    );

    assert.ok(
      source.includes(
        'data-chat-thread-header="live"'
      )
    );

    assert.ok(
      source.includes(
        'data-chat-thread-body='
      )
    );
  }
);


test(
  "thread header is grounded in the active chat metadata",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        "activeChat?.title"
      )
    );

    assert.ok(
      source.includes(
        "activeChat?.is_pinned"
      )
    );

    assert.ok(
      source.includes(
        "workspaceBranchCount"
      )
    );
  }
);


test(
  "reference-only thread actions remain disabled",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    for (
      const notice of [
        "Thread bookmark shortcut is not available here yet",
        "Share conversation is not available yet",
        "More conversation actions are not available yet",
      ]
    ) {
      assert.ok(
        source.includes(notice),
        `Missing transparent disabled action: ${notice}`
      );
    }
  }
);


test(
  "composer is docked inside the reference chat workspace",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        'data-chat-composer-dock="v2.40"'
      )
    );

    assert.ok(
      source.includes(
        "max-w-5xl"
      )
    );

    assert.ok(
      source.includes(
        "<MessageInput"
      )
    );
  }
);


test(
  "bottom workspace cards are compact reference cards",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      source.includes(
        'data-reference-bottom-cards="v2.40"'
      )
    );

    assert.ok(
      source.includes(
        "min-h-[116px]"
      )
    );

    assert.ok(
      source.includes(
        "No branches"
      )
    );
  }
);


test(
  "chat canvas polish adds no runtime dependency",
  () => {
    const chatSource = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      chatSource.includes(
        'from "react-icons/fi"'
      )
    );

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
