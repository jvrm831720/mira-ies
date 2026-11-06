import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
const require = createRequire(import.meta.url);
const ts = require("typescript");

function source(path) { return readFileSync(new URL(path, import.meta.url), "utf8"); }
function transpile(path) {
  const result = ts.transpileModule(source(path), {
    fileName: path,
    reportDiagnostics: true,
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
    },
  });
  const errors = (result.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error);
  assert.equal(errors.length, 0,
    path + ": " + errors.map(d => ts.flattenDiagnosticMessageText(d.messageText, " ")).join("; "));
  return result.outputText;
}

test("new experience TSX modules transpile without syntax diagnostics", () => {
  const paths = [
    "../src/components/students/student-drawer.tsx",
    "../src/components/students/students-list-page.tsx",
    "../src/components/students/student-risk-factors.tsx",
    "../src/components/students/student-campaigns-panel.tsx",
    "../src/components/students/risk-movements-feed.tsx",
    "../src/components/students/risk-trend.tsx",
    "../src/components/work/work-activities-panel.tsx",
    "../src/components/work/work-queue-filters.tsx",
    "../src/components/work/work-queue-summary.tsx",
    "../src/components/layout/command-palette.tsx",
    "../src/app/(app)/retencao/page.tsx",
  ];
  for (const path of paths) transpile(path);
});

test("a risk change is only displayed for comparable model/semantics", () => {
  const code = transpile("../src/components/students/risk-trend.tsx");
  const exports = {};
  vm.runInNewContext(code, { exports, require: () => ({}) }, { filename: "risk-trend.js" });
  const delta = exports.comparableRiskDelta;
  const a = { score: 74, model_version: "v2", model_scope: "tenant", score_semantics_version: "s2" };
  const b = { score: 61, model_version: "v2", model_scope: "tenant", score_semantics_version: "s2" };
  assert.equal(delta(a, b), 13);
  assert.equal(delta({ ...a, score: 49 }, b), -12);
  assert.equal(delta(a, { ...b, model_version: "v1" }), null);
  assert.equal(delta(a, { ...b, model_scope: "global" }), null);
  assert.equal(delta(a, { ...b, score_semantics_version: "s1" }), null);
  assert.equal(delta(a, undefined), null);
});

test("product light colors use one Tailwind token system", () => {
  const tailwind = source("../tailwind.config.ts");
  const css = source("../src/app/globals.css");
  assert.doesNotMatch(tailwind, /hsl\\(var\\(--/);
  assert.doesNotMatch(css, /--primary:\\s*233\\s+56%\\s+53%/);
  assert.match(tailwind, /primary:\\s*\\{\\s*DEFAULT:\\s*"var\\(--color-ink\\)"/);
});

test("retention handoff never defaults to a real send", () => {
  const selection = source("../src/lib/retention-selection.ts");
  const planner = source("../src/app/(app)/retencao/page.tsx");
  assert.match(selection, /MAX_AGE_MS = 10 \\* 60 \\* 1000/);
  assert.match(planner, /setDryRun\\(true\\)/);
  assert.match(planner, /parseRetentionSelection/);
});
