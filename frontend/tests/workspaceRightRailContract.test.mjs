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
  "app mounts the v2.39 right utility rail",
  () => {
    const source = read(
      "src/App.jsx"
    );

    assert.ok(
      source.includes(
        'import WorkspaceRightRail from "./components/Workspace/WorkspaceRightRail";'
      )
    );

    assert.ok(
      source.includes(
        "<WorkspaceRightRail"
      )
    );

    for (
      const prop of [
        "agents={agents}",
        "agentsLoading={agentsLoading}",
        "agentsAvailable={agentsAvailable}",
        "selectedAgentId={selectedAgentId}",
        "onAgentChange={changeSelectedAgent}",
        "theme={theme}",
      ]
    ) {
      assert.ok(
        source.includes(prop),
        `Missing right rail prop: ${prop}`
      );
    }
  }
);


test(
  "right rail uses the real existing agent catalog",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        'data-right-rail-agents="live"'
      )
    );

    assert.ok(
      source.includes(
        "agents.map((agent)"
      )
    );

    assert.ok(
      source.includes(
        "onAgentChange?.("
      )
    );

    assert.ok(
      source.includes(
        "agent.agent_id"
      )
    );
  }
);


test(
  "right rail network status is explicitly browser-only",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        'data-right-rail-network="live"'
      )
    );

    assert.ok(
      source.includes(
        "navigator.onLine"
      )
    );

    assert.ok(
      source.includes(
        "not backend system health"
      )
    );
  }
);


test(
  "memory card uses real backend previews and explicit controls",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        "data-right-rail-memory={"
      )
    );

    assert.ok(
      source.includes(
        'data-memory-preview="backend"'
      )
    );

    assert.ok(
      source.includes(
        "handleClearMemory"
      )
    );

    assert.ok(
      !source.includes(
        "No memory data is shown"
      )
    );
  }
);
test(
  "analytics is reserved for v2.40 without fabricated metrics",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        'data-right-rail-analytics="placeholder"'
      )
    );

    assert.ok(
      source.includes(
        "Planned for v2.40"
      )
    );

    assert.ok(
      source.includes(
        "No fabricated chart data"
      )
    );
  }
);


test(
  "right rail is desktop-only and adds no runtime dependency",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        "2xl:flex"
      )
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
