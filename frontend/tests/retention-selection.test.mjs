import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const source = readFileSync(new URL("../src/lib/retention-selection.ts", import.meta.url), "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
const exports = {};
vm.runInNewContext(transpiled, { exports, JSON, Date, Error, Set }, { filename: "retention-selection.js" });
const { serializeRetentionSelection, parseRetentionSelection } = exports;
const start = Date.parse("2026-11-06T12:00:00Z");
function make(override = {}) {
  return { tenantId: "tenant-a", userId: "user-a",
    ids: ["student-1", "student-2"], campaign: "Acompanhamento", createdAt: start, ...override };
}

test("selection is round-tripped only for its owner and tenant", () => {
  const encoded = serializeRetentionSelection(make());
  assert.deepEqual(Array.from(parseRetentionSelection(encoded, "tenant-a", "user-a", start + 100).ids),
    ["student-1", "student-2"]);
  assert.equal(parseRetentionSelection(encoded, "tenant-b", "user-a", start + 100), null);
  assert.equal(parseRetentionSelection(encoded, "tenant-a", "user-b", start + 100), null);
});

test("expired, future and corrupt selections fail closed", () => {
  const encoded = serializeRetentionSelection(make());
  assert.equal(parseRetentionSelection(encoded, "tenant-a", "user-a", start + 600_001), null);
  assert.equal(parseRetentionSelection(encoded, "tenant-a", "user-a", start - 1), null);
  assert.equal(parseRetentionSelection("not-json", "tenant-a", "user-a", start), null);
});

test("selection ids are bounded and deduplicated", () => {
  const encoded = serializeRetentionSelection(make({ ids: ["student-1", "student-1", "student-2"] }));
  assert.deepEqual(Array.from(parseRetentionSelection(encoded, "tenant-a", "user-a", start).ids),
    ["student-1", "student-2"]);
  assert.throws(() => serializeRetentionSelection(make({ ids: [] })), /Seleção inválida/);
  assert.throws(() => serializeRetentionSelection(make({ ids: Array.from({ length: 101 }, (_, i) => String(i)) })), /Seleção inválida/);
});
