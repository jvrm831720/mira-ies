import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import vm from "node:vm";
import ts from "typescript";

const folder = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(folder, "data-hub-model.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const model = {};
vm.runInNewContext(output, { exports: model, require() { throw new Error("Unexpected runtime dependency"); } });

test("configured does not imply connected, authenticated or synchronized", () => {
  assert.equal(model.connectionState({ configured: true }).key, "configured");
  assert.equal(model.connectionState({ configured: false, last_sync_status: "success" }).key, "unconfigured");
  assert.equal(model.connectionState({ configured: true, status: "authenticated" }).key, "authenticated");
  assert.equal(model.connectionState({ configured: true, last_sync_status: "success" }).key, "configured");
  assert.equal(model.connectionState({ configured: true, last_sync_status: "success", last_sync_at: "2026-11-06T11:00:00Z" }).key, "synced");
});

test("failed and active states remain separate from scheduled or completed", () => {
  assert.equal(model.runState("failed").key, "error");
  assert.equal(model.runState("running").key, "syncing");
  assert.equal(model.runState("scheduled").key, "configured");
  assert.equal(model.runState("cancelled").key, "disabled");
  assert.equal(model.runState("strange-provider-code").key, "unknown");
});

test("only verifiable failures and partial completed uploads are flagged", () => {
  const rows = [
    { id: "one", filename: "first.csv", status: "completed", total_rows: 10, processed_rows: 10 },
    { id: "two", filename: "second.csv", status: "failed", total_rows: 12, processed_rows: 0 },
    { id: "three", filename: "third.csv", status: "completed", total_rows: 20, processed_rows: 15 },
    { id: "four", filename: "fourth.csv", status: "processing", total_rows: 100, processed_rows: 3 },
  ];
  const issues = model.importIssues(rows);
  assert.equal(issues.length, 2);
  assert.equal(issues[0].kind, "failed");
  assert.equal(issues[1].kind, "partial");
  assert.equal(model.importIssues([]).length, 0);
});

test("Data Hub never triggers imports, payments or remote tools by itself", () => {
  const jsx = readFileSync(resolve(folder, "data-hub-experience.tsx"), "utf8");
  assert.doesNotMatch(jsx, /api\.(ingestConnector|configureJacad|configureSponte|syncJacad|syncSponte|retryJacadSync|retrySponteSync)\s*\(/);
  assert.doesNotMatch(jsx, /dispatchApi\.(action|importComposio|stageFromComposio|approve|execute)\s*\(/);
  assert.doesNotMatch(jsx, /method:\s*["'](?:POST|PUT|PATCH|DELETE)["']/);
  assert.match(jsx, /hasNavigationPermission\(me\.data, "data\.view"\)/);
});

test("catalog categories are descriptive, not inferred connection state", () => {
  assert.equal(model.categoryLabel("finance"), "Financeiro e ERP");
  assert.equal(model.categoryLabel("lms"), "Sistemas acadêmicos");
  assert.equal(model.categoryLabel(undefined), "Outros sistemas");
});
