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
  "sidebar exposes the screenshot navigation structure",
  () => {
    const source = read(
      "src/components/Sidebar/Sidebar.jsx"
    );

    assert.ok(
      source.includes(
        'data-sidebar-navigation="v2.40"'
      )
    );

    for (
      const label of [
        "Chats",
        "Branches",
        "Bookmarks",
        "Knowledge Base",
        "Agents",
        "Memory",
        "Profile",
        "Settings",
      ]
    ) {
      assert.ok(
        source.includes(label),
        `Missing sidebar item: ${label}`
      );
    }
  }
);


test(
  "sidebar live navigation reuses existing workspace targets",
  () => {
    const source = read(
      "src/components/Sidebar/Sidebar.jsx"
    );

    for (
      const target of [
        "sidebar-chat-list",
        "sidebar-bookmarks-panel",
        "workspace-branch-explorer",
        "workspace-document-library",
        "agentPicker",
      ]
    ) {
      assert.ok(
        source.includes(target),
        `Missing live navigation target: ${target}`
      );
    }

    assert.ok(
      source.includes(
        "scrollIntoView"
      )
    );
  }
);


test(
  "memory and profile remain transparent disabled placeholders",
  () => {
    const source = read(
      "src/components/Sidebar/Sidebar.jsx"
    );

    assert.ok(
      source.includes(
        'title="Memory is not available yet"'
      )
    );

    assert.ok(
      source.includes(
        'title="Profile is not available yet"'
      )
    );
  }
);


test(
  "sidebar user card links to the real admin dashboard",
  () => {
    const source = read(
      "src/components/Sidebar/Sidebar.jsx"
    );

    assert.ok(
      source.includes(
        'data-sidebar-user-card="real-dashboard-link"'
      )
    );

    assert.ok(
      source.includes(
        "setShowDashboard(true)"
      )
    );

    assert.ok(
      source.includes(
        "📊 Dashboard"
      )
    );

    assert.ok(
      source.includes(
        "System & usage"
      )
    );

    assert.ok(
      source.includes(
        "<AdminDashboard"
      )
    );

    assert.ok(
      !source.includes(
        "10 GB"
      )
    );
  }
);


test(
  "topbar search opens the existing sidebar search surface",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        'data-workspace-topbar="v2.40"'
      )
    );

    assert.ok(
      source.includes(
        "Search chats & bookmarks..."
      )
    );

    assert.ok(
      source.includes(
        "onClick={onOpenSidebar}"
      )
    );

    assert.ok(
      source.includes(
        'event.key.toLowerCase() === "k"'
      )
    );
  }
);


test(
  "notification and profile controls do not pretend to work",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        'title="Notifications are not available yet"'
      )
    );

    assert.ok(
      source.includes(
        'title="Profile is not available yet"'
      )
    );
  }
);


test(
  "welcome quick actions are compact without changing prompt behavior",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      source.includes(
        'data-reference-polish="v2.40"'
      )
    );

    assert.ok(
      source.includes(
        "How can I help you today?"
      )
    );

    assert.ok(
      source.includes(
        "min-h-[82px]"
      )
    );

    assert.ok(
      source.includes(
        "setInput?.(action.prompt)"
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
