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
  "sidebar exposes dashboard navigation",
  () => {
    const source = read(
      "src/components/Sidebar/Sidebar.jsx"
    );

    assert.ok(
      source.includes(
        "📊 Dashboard"
      )
    );

    assert.ok(
      source.includes(
        "<AdminDashboard"
      )
    );
  }
);


test(
  "dashboard uses session-only credential storage",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    assert.ok(
      source.includes(
        "window.sessionStorage"
      )
    );

    assert.ok(
      source.includes(
        "onkar-ai-dashboard-credential"
      )
    );

    assert.ok(
      !source.includes(
        "localStorage"
      )
    );
  }
);


test(
  "dashboard credential is never hard-coded",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    assert.ok(
      source.includes(
        'type="password"'
      )
    );

    assert.ok(
      source.includes(
        "Forget credential"
      )
    );

    assert.ok(
      !source.includes(
        "v2.37-dashboard-token"
      )
    );
  }
);


test(
  "dashboard service uses per-request bearer auth",
  () => {
    const source = read(
      "src/services/dashboardService.js"
    );

    assert.ok(
      source.includes(
        '"/admin/dashboard/summary"'
      )
    );

    assert.ok(
      source.includes(
        "Authorization:"
      )
    );

    assert.ok(
      source.includes(
        "`Bearer ${token}`"
      )
    );

    assert.ok(
      !source.includes(
        "axios.defaults.headers"
      )
    );

    assert.ok(
      !source.includes(
        "api.defaults.headers"
      )
    );
  }
);


test(
  "dashboard renders all v2.37 metric groups",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    for (
      const label of [
        "Usage & Storage",
        "Agent Usage",
        "Recovery",
        "Incidents",
      ]
    ) {
      assert.ok(
        source.includes(label)
      );
    }
  }
);


test(
  "dashboard handles auth and availability states",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    assert.ok(
      source.includes(
        "error?.status === 401"
      )
    );

    assert.ok(
      source.includes(
        "error?.status === 404"
      )
    );

    assert.ok(
      source.includes(
        "error?.status === 503"
      )
    );

    assert.ok(
      source.includes(
        "Recovery metrics"
      )
    );

    assert.ok(
      source.includes(
        "Incident metrics"
      )
    );
  }
);


test(
  "dashboard adds no new runtime dependency contract",
  () => {
    const packageJson =
      JSON.parse(
        read(
          "package.json"
        )
      );

    assert.equal(
      packageJson.scripts[
        "test:dashboard"
      ],
      "node --test ./tests/dashboardContract.test.mjs"
    );

    assert.ok(
      packageJson.dependencies.react
    );

    assert.ok(
      packageJson.dependencies.axios
    );
  }
);

test(
  "dashboard service exposes read-only live health request",
  () => {
    const source = read(
      "src/services/dashboardService.js"
    );

    assert.ok(
      source.includes(
        "getDashboardHealth"
      )
    );

    assert.ok(
      source.includes(
        '"/admin/dashboard/health"'
      )
    );

    assert.ok(
      source.includes(
        "Authorization:"
      )
    );

    assert.ok(
      source.includes(
        "`Bearer ${token}`"
      )
    );
  }
);


test(
  "dashboard renders live system health contract",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    for (
      const label of [
        "System Health",
        "Last checked",
        "Database",
        "Document Storage",
        "Document Recovery",
        "Knowledge / RAG",
        "Healthy",
        "Warning",
        "Critical",
        "Initializing",
        "Unavailable",
        "Disabled",
      ]
    ) {
      assert.ok(
        source.includes(label)
      );
    }
  }
);


test(
  "dashboard refresh loads metrics and health independently",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    assert.ok(
      source.includes(
        "getDashboardSummary(token)"
      )
    );

    assert.ok(
      source.includes(
        "getDashboardHealth(token)"
      )
    );

    assert.ok(
      source.includes(
        "Promise.allSettled"
      )
    );

    assert.ok(
      source.includes(
        "healthErrorMessage"
      )
    );

    assert.ok(
      source.includes(
        'summaryResult.status ==='
      )
    );

    assert.ok(
      source.includes(
        'healthResult.status ==='
      )
    );
  }
);


test(
  "dashboard auto refresh uses a bounded 30 second interval",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    assert.ok(
      source.includes(
        "DASHBOARD_AUTO_REFRESH_MS"
      )
    );

    assert.ok(
      source.includes(
        "30_000"
      )
    );

    assert.ok(
      source.includes(
        "window.setInterval("
      )
    );

    assert.ok(
      source.includes(
        "window.clearInterval("
      )
    );

    assert.ok(
      source.includes(
        "activeCredential"
      )
    );
  }
);


test(
  "dashboard auto refresh prevents overlapping cycles",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    assert.ok(
      source.includes(
        "useRef"
      )
    );

    assert.ok(
      source.includes(
        "refreshInFlightRef.current"
      )
    );

    assert.ok(
      source.includes(
        "background = false"
      )
    );

    assert.ok(
      source.includes(
        "setRefreshing(true)"
      )
    );

    assert.ok(
      source.includes(
        "setRefreshing(false)"
      )
    );
  }
);


test(
  "dashboard preserves manual refresh and forget stops polling",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    assert.ok(
      source.includes(
        '"Refresh"'
      )
    );

    assert.ok(
      source.includes(
        "loadDashboard(\n      credential"
      )
    );

    assert.ok(
      source.includes(
        'setActiveCredential("")'
      )
    );

    assert.ok(
      source.includes(
        "requestEpochRef.current += 1"
      )
    );
  }
);


test(
  "dashboard keeps backend Last checked timestamp distinct from auto refresh",
  () => {
    const source = read(
      "src/components/Dashboard/AdminDashboard.jsx"
    );

    assert.ok(
      source.includes(
        "health?.checked_at"
      )
    );

    assert.ok(
      source.includes(
        "Auto refresh: every 30 seconds"
      )
    );

    assert.ok(
      !source.includes(
        "lastRefreshed"
      )
    );
  }
);
