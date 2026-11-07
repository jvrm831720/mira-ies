import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const source = readFileSync(new URL("../src/lib/experience-rollout.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
const exports = {};
vm.runInNewContext(js, { exports, process: { env: {} } });
const enabled = exports.isUnifiedExperienceEnabled;
const own = "650c805f-bcd8-4ac9-ae35-9639336cb70f";
const foreign = "f75f1b09-2e6e-4df4-b745-dd47b4ae61e8";

test("off suppresses remote search and unified WorkInbox in every workspace", () => {
  assert.equal(enabled(own, { mode: "off" }), false);
  assert.equal(enabled(foreign, { mode: "off" }), false);
});

test("on preserves integrated Wave 6 experience without cross-workspace bypass", () => {
  assert.equal(enabled(own, { mode: "on" }), true);
  assert.equal(enabled(foreign, { mode: "on" }), true);
});

test("canary exposes only explicitly authorized valid tenant UUIDs", () => {
  const config = { mode: "canary", tenantIds: " " + own.toUpperCase() + ",broken" };
  assert.equal(enabled(own, config), true);
  assert.equal(enabled(foreign, config), false);
  assert.equal(enabled(undefined, config), false);
  assert.equal(enabled("not-a-uuid", config), false);
  assert.equal(enabled(foreign, { mode: "canary", tenantIds: "" }), false);
});

test("unknown rollout modes and missing canary lists fail closed", () => {
  assert.equal(enabled(own, { mode: "invalid-mode" }), false);
  assert.equal(enabled(own, { mode: "canary" }), false);
});

test("feature flags never replace the server's authorization decision", () => {
  const command = readFileSync(new URL("../src/components/layout/command-palette.tsx", import.meta.url), "utf8");
  const workPage = readFileSync(new URL("../src/app/(app)/trabalho/page.tsx", import.meta.url), "utf8");
  assert.match(command, /enabled: federated && open && !!tenantId && !!userId/);
  assert.match(workPage, /open=\{!unified\}/);
  assert.match(workPage, /<WorkInbox \/>/);
  assert.match(command, /mergeSearchResults/);
});
