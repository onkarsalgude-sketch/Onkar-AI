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
  "active chats keep the greeting and six quick actions visible",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        "<WorkspaceWelcome"
      )
    );

    assert.ok(
      source.includes(
        "showBottomCards="
      )
    );

    assert.ok(
      !source.includes(
        "messages.length <= 1 && (\n            <WorkspaceWelcome"
      )
    );
  }
);


test(
  "bottom cards remain optional and are separated from the command deck",
  () => {
    const chat = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    const welcome = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      chat.includes(
        'data-workspace-bottom-deck="after-thread"'
      )
    );

    assert.ok(
      chat.includes(
        "showGreetingActions={false}"
      )
    );

    assert.ok(
      welcome.includes(
        "showBottomCards = true"
      )
    );

    assert.ok(
      welcome.includes(
        "{showBottomCards && ("
      )
    );
  }
);


test(
  "branch and knowledge tools are no longer permanent top bars",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        "data-workspace-tool-overlay"
      )
    );

    assert.match(
      source,
      /workspacePanel\s*===\s*"branches"/
    );

    assert.ok(
      source.includes(
        'id="workspace-branch-explorer"'
      )
    );

    assert.ok(
      source.includes(
        'id="workspace-document-library"'
      )
    );
  }
);


test(
  "sidebar navigation opens the real workspace tool overlay",
  () => {
    const source = read(
      "src/components/Sidebar/Sidebar.jsx"
    );

    assert.ok(
      source.includes(
        '"onkar-ai:open-workspace-panel"'
      )
    );

    assert.ok(
      source.includes(
        "new CustomEvent"
      )
    );

    assert.match(
      source,
      /\?\s*"branches"\s*:\s*"knowledge"/
    );
  }
);


test(
  "desktop shell preserves the proven frame while narrowing the sidebar",
  () => {
    const app = read(
      "src/App.jsx"
    );

    const sidebar = read(
      "src/components/Sidebar/Sidebar.jsx"
    );

    assert.ok(
      app.includes(
        'data-workspace-shell="v2.39"'
      )
    );

    assert.ok(
      app.includes(
        "md:gap-3 md:p-3"
      )
    );

    assert.ok(
      app.includes(
        "md:rounded-[28px]"
      )
    );

    assert.ok(
      sidebar.includes(
        "w-[252px]"
      )
    );
  }
);


test(
  "layout hierarchy polish adds no runtime dependency",
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
