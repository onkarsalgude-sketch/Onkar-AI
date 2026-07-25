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
  "memory service uses only authenticated read and clear routes",
  () => {
    const source = read(
      "src/services/memoryService.js"
    );

    assert.ok(source.includes("api.get("));
    assert.ok(source.includes('"/memory"'));
    assert.ok(source.includes("api.delete("));
    assert.ok(source.includes("Authorization:"));
    assert.ok(source.includes("`Bearer ${token}`"));
    assert.ok(!source.includes("api.post("));
  }
);


test(
  "memory service keeps the response bounded to backend preview fields",
  () => {
    const source = read(
      "src/services/memoryService.js"
    );

    for (const field of [
      "role",
      "preview",
      "truncated",
    ]) {
      assert.ok(source.includes(field));
    }

    assert.ok(
      source.includes(
        "preview.length > 240"
      )
    );
    assert.ok(
      source.includes(
        "items.length > 20"
      )
    );
  }
);


test(
  "memory credential is session scoped and never stored locally",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        "onkar-ai-memory-credential"
      )
    );
    assert.ok(
      source.includes(
        "window.sessionStorage.getItem"
      )
    );
    assert.ok(
      source.includes(
        "window.sessionStorage.setItem"
      )
    );
    assert.ok(
      source.includes(
        "window.sessionStorage.removeItem"
      )
    );
    assert.ok(!source.includes("localStorage"));
    assert.ok(source.includes('type="password"'));
  }
);


test(
  "memory card exposes honest locked loading live empty unauthorized and unavailable states",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        "data-right-rail-memory={"
      )
    );

    for (const state of [
      '"locked"',
      '"loading"',
      '"live"',
      '"empty"',
      '"unauthorized"',
      '"unavailable"',
    ]) {
      assert.ok(
        source.includes(state),
        `Missing memory state: ${state}`
      );
    }
  }
);


test(
  "memory card renders backend previews without inventing profile facts",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      source.includes(
        'data-memory-preview="backend"'
      )
    );
    assert.ok(source.includes("item.preview"));
    assert.ok(source.includes("item.role"));
    assert.ok(!source.includes("item.content"));
    assert.ok(!source.includes("profileMemory"));
  }
);


test(
  "clear memory requires confirmation and reloads from backend",
  () => {
    const source = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(source.includes("window.confirm("));
    assert.ok(source.includes("await clearMemory("));
    assert.ok(source.includes("setMemoryRefreshKey"));
  }
);


test(
  "memory UI removes the old right rail fake-placeholder copy",
  () => {
    const rightRail = read(
      "src/components/Workspace/WorkspaceRightRail.jsx"
    );

    assert.ok(
      !rightRail.includes(
        'data-right-rail-memory="placeholder"'
      )
    );
    assert.ok(
      !rightRail.includes(
        "No memory data is shown until a"
      )
    );
    assert.ok(!rightRail.includes("Coming later"));
  }
);


test(
  "memory UI adds no new runtime dependency and stale navigation copy is corrected",
  () => {
    const packageJson =
      JSON.parse(read("package.json"));

    const sidebar = read(
      "src/components/Sidebar/Sidebar.jsx"
    );
    const settings = read(
      "src/components/Common/SettingsModal.jsx"
    );

    assert.ok(
      Object.prototype.hasOwnProperty.call(
        packageJson.dependencies,
        "react-icons"
      )
    );

    assert.ok(
      sidebar.includes(
        "Memory controls are available in the right utility rail"
      )
    );

    assert.ok(
      settings.includes(
        "Use the Memory card in the right utility rail to clear memory."
      )
    );

    assert.ok(
      !settings.includes(
        "Clear Memory feature will be added next."
      )
    );
  }
);
