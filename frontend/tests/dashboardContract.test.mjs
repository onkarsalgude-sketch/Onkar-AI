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
  );
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
