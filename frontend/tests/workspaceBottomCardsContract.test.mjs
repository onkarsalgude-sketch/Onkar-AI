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
  "welcome renders exactly three bottom workspace cards",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      source.includes(
        'data-workspace-bottom-cards="3"'
      )
    );

    for (
      const label of [
        "Knowledge Base",
        "Recent Bookmarks",
        "Chat Branches",
      ]
    ) {
      assert.ok(
        source.includes(label),
        `Missing bottom card: ${label}`
      );
    }
  }
);


test(
  "knowledge shortcut targets the existing document library",
  () => {
    const chat = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      chat.includes(
        'id="workspace-document-library"'
      )
    );

    assert.ok(
      chat.includes(
        'data-workspace-feature="knowledge"'
      )
    );

    assert.ok(
      chat.includes(
        "<DocumentLibrary"
      )
    );

    assert.ok(
      chat.includes(
        "onOpenKnowledge={() =>"
      )
    );
  }
);


test(
  "branch shortcut targets the existing branch explorer",
  () => {
    const chat = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      chat.includes(
        'id="workspace-branch-explorer"'
      )
    );

    assert.ok(
      chat.includes(
        'data-workspace-feature="branches"'
      )
    );

    assert.ok(
      chat.includes(
        "<BranchExplorer"
      )
    );

    assert.ok(
      chat.includes(
        "onOpenBranches={() =>"
      )
    );
  }
);


test(
  "branch card uses real existing chat branch count",
  () => {
    const chat = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    const welcome = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      chat.includes(
        "activeChat?.branch_count"
      )
    );

    assert.ok(
      chat.includes(
        "branchCount={"
      )
    );

    assert.ok(
      welcome.includes(
        "branchCount > 0"
      )
    );

    assert.ok(
      !welcome.includes(
        "fake"
      )
    );
  }
);


test(
  "bookmarks card reuses the existing sidebar navigation",
  () => {
    const chat = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    const welcome = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      chat.includes(
        "onOpenSidebar={"
      )
    );

    assert.ok(
      welcome.includes(
        "onClick={onOpenSidebar}"
      )
    );

    assert.ok(
      welcome.includes(
        "existing bookmarks panel"
      )
    );
  }
);


test(
  "knowledge and branch shortcuts disable when real context is absent",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      source.includes(
        "disabled={!activeChatId}"
      )
    );

    assert.ok(
      source.includes(
        "branchCount <= 0"
      )
    );

    assert.ok(
      source.includes(
        "Open a saved chat before using document tools."
      )
    );

    assert.ok(
      source.includes(
        "Create a branch from a user message"
      )
    );
  }
);


test(
  "bottom cards add no runtime dependency",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      source.includes(
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
