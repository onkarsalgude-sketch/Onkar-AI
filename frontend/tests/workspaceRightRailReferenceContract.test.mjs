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
  "right rail follows the reference card order",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    const agents =
      source.indexOf(
        'data-right-rail-agents="live"'
      );
    const memory =
      source.indexOf(
        'data-right-rail-memory={'
      );
    const activity =
      source.indexOf(
        'data-right-rail-activity={'
      );
    const system =
      source.indexOf(
        "data-right-rail-system-status="
      );

    assert.ok(agents >= 0);
    assert.ok(memory > agents);
    assert.ok(activity > memory);
    assert.ok(system > activity);
  }
);


test(
  "agents remain grounded in the server catalog",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        "agents.map((agent)"
      )
    );

    assert.ok(
      source.includes(
        "agent.agent_id"
      )
    );

    assert.ok(
      source.includes(
        "onAgentChange?.("
      )
    );
  }
);


test(
  "memory is grounded in the authenticated backend preview contract",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        'from "../../services/memoryService"'
      )
    );

    assert.ok(
      source.includes(
        "getMemory"
      )
    );

    assert.ok(
      source.includes(
        'data-memory-preview="backend"'
      )
    );

    assert.ok(
      source.includes(
        "item.preview"
      )
    );
  }
);
test(
  "todays activity uses real backend activity source",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        'data-right-rail-activity={'
      )
    );

    assert.ok(
      source.includes(
        'data-activity-source="dashboard-backend"'
      )
    );

    assert.ok(
      !source.includes(
        "No fabricated chart data"
      )
    );

    assert.ok(
      !source.includes(
        "<LineChart"
      )
    );
  }
);


test(
  "system status reuses authenticated dashboard health",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        'from "../../services/dashboardService"'
      )
    );

    assert.ok(
      source.includes(
        "getDashboardHealth"
      )
    );

    assert.ok(
      source.includes(
        "onkar-ai-dashboard-credential"
      )
    );

    assert.ok(
      source.includes(
        "window.sessionStorage.getItem"
      )
    );

    assert.ok(
      !source.includes(
        "localStorage"
      )
    );

    assert.ok(
      source.includes(
        'response?.service ==='
      )
    );

    assert.ok(
      source.includes(
        '"dashboard_health"'
      )
    );

    assert.ok(
      source.includes(
        '"system_health"'
      )
    );
  }
);


test(
  "browser connectivity remains separate from backend health",
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
  "live health refresh is bounded and adds no runtime dependency",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        "RIGHT_RAIL_HEALTH_REFRESH_MS"
      )
    );

    assert.ok(
      source.includes(
        "30_000"
      )
    );

    assert.ok(
      source.includes(
        "healthInFlightRef.current"
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
