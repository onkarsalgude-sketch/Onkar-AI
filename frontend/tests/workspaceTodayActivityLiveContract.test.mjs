import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, "..");

function read(relativePath) {
  return fs
    .readFileSync(path.join(frontendRoot, relativePath), "utf8")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");
}

test("1. Dashboard service exports getDashboardActivityToday", () => {
  const source = read("src/services/dashboardService.js");
  assert.ok(
    source.includes("export async function getDashboardActivityToday")
  );
});

test("2. It uses GET /admin/dashboard/activity/today", () => {
  const source = read("src/services/dashboardService.js");
  assert.ok(source.includes('"/admin/dashboard/activity/today"'));
});

test("3. It uses bearer Authorization", () => {
  const source = read("src/services/dashboardService.js");
  assert.ok(source.includes("Authorization:"));
  assert.ok(source.includes("Bearer ${token}"));
});

test("4. Activity reuses onkar-ai-dashboard-credential", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(source.includes("DASHBOARD_CREDENTIAL_KEY"));
  assert.ok(source.includes('"onkar-ai-dashboard-credential"'));
  assert.ok(source.includes("readSessionCredential"));
});

test("5. No Activity credential key exists", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(!source.includes("onkar-ai-activity-credential"));
  assert.ok(!source.includes("ACTIVITY_CREDENTIAL_KEY"));
});

test("6. No localStorage is used", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(!source.includes("localStorage"));
});

test("7. Activity has locked/loading/live/empty/unauthorized/unavailable states", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  for (const state of [
    "locked",
    "loading",
    "live",
    "empty",
    "unauthorized",
    "unavailable",
  ]) {
    assert.ok(
      source.includes(`"${state}"`),
      `Missing state: ${state}`
    );
  }
});

test("8. Activity renders backend counts only", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(source.includes("messages?.total"));
  assert.ok(source.includes("messages?.user"));
  assert.ok(source.includes("messages?.assistant"));
  assert.ok(source.includes("activityData.messages"));
});

test("9. Activity renders backend bucket message_count values", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(source.includes("activityData.buckets"));
  assert.ok(source.includes("b.message_count"));
});

test("10. Activity source marker identifies backend data", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(source.includes('data-activity-source="dashboard-backend"'));
  assert.ok(source.includes("data-right-rail-activity={"));
});

test("11. Old placeholder text is gone", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(!source.includes("No fabricated chart data"));
  assert.ok(!source.includes("No real time-series source is"));
});

test("12. No chart dependency is added", () => {
  const pkgJson = read("package.json");
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");

  assert.ok(!pkgJson.includes("recharts"));
  assert.ok(!pkgJson.includes("chart.js"));
  assert.ok(!pkgJson.includes("apexcharts"));
  assert.ok(!source.includes("<LineChart"));
  assert.ok(!source.includes("<BarChart"));
});

test("13. No periodic Activity polling is introduced", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  const activityEffectIndex = source.indexOf("async function loadActivity");
  assert.ok(activityEffectIndex >= 0);
  const memoryEffectIndex = source.indexOf("async function loadMemory");
  const activityBlock = source.slice(activityEffectIndex, memoryEffectIndex);
  assert.ok(!activityBlock.includes("setInterval"));
});

test("14. Activity refresh remains separate from health polling", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(source.includes("RIGHT_RAIL_HEALTH_REFRESH_MS"));
  assert.ok(!source.includes("RIGHT_RAIL_ACTIVITY_REFRESH_MS"));
});

test("15. Card order remains Agents -> Memory -> Today's Activity -> System Status", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  const agents = source.indexOf('data-right-rail-agents="live"');
  const memory = source.indexOf("data-right-rail-memory={");
  const activity = source.indexOf("data-right-rail-activity={");
  const system = source.indexOf("data-right-rail-system-status=");

  assert.ok(agents >= 0);
  assert.ok(memory > agents);
  assert.ok(activity > memory);
  assert.ok(system > activity);
});

test("16. Server-local semantics are visible", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(source.includes("Conversation activity"));
  assert.ok(source.includes("Server-local day"));
});

test("17. Empty state is truthful", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(
    source.includes(
      "No conversation messages recorded for this server-local day."
    )
  );
});

test("18. No fabricated productivity/session/time metrics appear", () => {
  const source = read("src/components/Workspace/WorkspaceRightRail.jsx");
  assert.ok(!source.includes("screen time"));
  assert.ok(!source.includes("productivity score"));
  assert.ok(!source.includes("session duration"));
  assert.ok(!source.includes("active minutes"));
});
