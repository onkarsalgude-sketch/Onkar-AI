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

const frontendRoot = path.resolve(
  here,
  ".."
);

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
  "workspace shell owns the v2.39 desktop frame",
  () => {
    const source = read(
      "src/App.jsx"
    );

    assert.ok(
      source.includes(
        'data-workspace-shell="v2.39"'
      )
    );

    assert.ok(
      source.includes(
        'data-workspace-main="primary"'
      )
    );

    assert.ok(
      source.includes(
        "h-screen overflow-hidden"
      )
    );

    assert.ok(
      source.includes(
        "md:rounded-[28px]"
      )
    );
  }
);


test(
  "workspace sidebar preserves behavior inside the new rail",
  () => {
    const source = read(
      "src/components/Sidebar/Sidebar.jsx"
    );

    assert.ok(
      source.includes(
        'data-workspace-sidebar="primary"'
      )
    );

    for (
      const behavior of [
        "handleNewChat",
        "GlobalChatSearch",
        "BookmarksPanel",
        "AdminDashboard",
        "SettingsModal",
        "toggleChatPin",
        "moveChatToFolder",
      ]
    ) {
      assert.ok(
        source.includes(behavior),
        `Missing sidebar behavior: ${behavior}`
      );
    }

    assert.ok(
      source.includes(
        "md:hidden"
      )
    );

    assert.ok(
      source.includes(
        "Personal AI Workspace"
      )
    );
  }
);


test(
  "chat surface fits the shell without losing chat tools",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        'data-workspace-chat="primary"'
      )
    );

    assert.ok(
      source.includes(
        "relative flex h-full"
      )
    );

    for (
      const behavior of [
        "<BranchExplorer",
        "<DocumentLibrary",
        "<WelcomeScreen",
        "<Message",
        "<MessageInput",
        "onOpenSidebar",
      ]
    ) {
      assert.ok(
        source.includes(behavior),
        `Missing chat behavior: ${behavior}`
      );
    }
  }
);


test(
  "workspace shell keeps the existing theme contract",
  () => {
    const source = read(
      "src/App.jsx"
    );

    assert.ok(
      source.includes(
        '"onkar-ai-theme"'
      )
    );

    assert.ok(
      source.includes(
        "document.documentElement.dataset.theme"
      )
    );

    assert.ok(
      source.includes(
        "document.documentElement.style.colorScheme"
      )
    );
  }
);


test(
  "workspace shell adds no runtime dependency",
  () => {
    const packageJson =
      JSON.parse(
        read("package.json")
      );

    assert.deepEqual(
      Object.keys(
        packageJson.dependencies
      ).sort(),
      [
        "axios",
        "jspdf",
        "react",
        "react-dom",
        "react-icons",
        "react-markdown",
        "react-syntax-highlighter",
        "remark-gfm",
      ].sort()
    );
  }
);
