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
        'data-right-rail-memory="placeholder"'
      );
    const activity =
      source.indexOf(
        'data-right-rail-activity="no-timeseries"'
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
  "memory stays explicitly unavailable rather than fabricated",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        'data-right-rail-memory="placeholder"'
      )
    );

    assert.ok(
      source.includes(
        "No memory data is shown"
      )
    );
  }
);


test(
  "todays activity has no invented time series",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        'data-right-rail-activity="no-timeseries"'
      )
    );

    assert.ok(
      source.includes(
        "No fabricated chart data"
      )
    );

    assert.ok(
      source.includes(
        "No real time-series source is"
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
