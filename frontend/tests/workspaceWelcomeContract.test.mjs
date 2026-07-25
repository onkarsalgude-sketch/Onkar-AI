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
  "workspace welcome replaces the legacy welcome surface",
  () => {
    const source = read(
      "src/components/Chat/ChatWindow.jsx"
    );

    assert.ok(
      source.includes(
        'import WorkspaceWelcome from "../Workspace/WorkspaceWelcome";'
      )
    );

    assert.ok(
      source.includes(
        "<WorkspaceWelcome"
      )
    );

    assert.ok(
      !source.includes(
        "<WelcomeScreen"
      )
    );
  }
);


test(
  "workspace welcome exposes the personalized greeting",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      source.includes(
        'data-workspace-welcome="v2.39"'
      )
    );

    assert.ok(
      source.includes(
        "Good morning"
      )
    );

    assert.ok(
      source.includes(
        "Good afternoon"
      )
    );

    assert.ok(
      source.includes(
        "Good evening"
      )
    );

    assert.ok(
      source.includes(
        "Onkar"
      )
    );
  }
);


test(
  "workspace welcome renders exactly six quick actions",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    for (
      const label of [
        "Study",
        "Code",
        "Research",
        "Write",
        "Analyze",
        "Create",
      ]
    ) {
      assert.ok(
        source.includes(
          `label: "${label}"`
        ),
        `Missing quick action: ${label}`
      );
    }

    assert.ok(
      source.includes(
        'data-workspace-quick-actions="6"'
      )
    );

    const actionIds =
      source.match(
        /id: "(study|code|research|write|analyze|create)"/g
      ) || [];

    assert.equal(
      actionIds.length,
      6
    );
  }
);


test(
  "quick actions only prefill the existing composer",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      source.includes(
        "setInput?.(action.prompt)"
      )
    );

    assert.ok(
      !source.includes(
        "sendMessage"
      )
    );

    assert.ok(
      !source.includes(
        "fetch("
      )
    );

    assert.ok(
      !source.includes(
        "axios"
      )
    );
  }
);


test(
  "workspace welcome preserves dark and light theme styling",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceWelcome.jsx"
    );

    assert.ok(
      source.includes(
        'theme = "dark"'
      )
    );

    assert.ok(
      source.includes(
        'theme === "dark"'
      )
    );
  }
);


test(
  "workspace welcome uses only existing react-icons dependency",
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
