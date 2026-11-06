import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const dir = path.dirname(fileURLToPath(import.meta.url));

function loadPureTypescript(filename) {
  const input = readFileSync(path.join(dir, filename), "utf8");
  const output = ts.transpileModule(input, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const exports = {};
  vm.runInNewContext(output, { exports, Intl, Date, Number, String, Array, Set, Map, console });
  return exports;
}

const { matchesObjectFilters, formatPropertyValue } = loadPureTypescript("object-index-utils.ts");
const { defaultViewSpec, validateObjectView } = loadPureTypescript("object-index-types.ts");

test("missing student risk is not low risk and does not match numeric criteria", () => {
  const student = { id: "a", score: null, risk: null, nome: "Ana" };
  const fields = [
    { key: "nome", title: "Nome", type: "text", primary: true, filterable: true, getValue: row => row.nome },
    { key: "score", title: "Score", type: "number", filterable: true, sortable: true, getValue: row => row.score },
    { key: "risk", title: "Risco", type: "select", filterable: true, getValue: row => row.risk },
  ];
  assert.equal(matchesObjectFilters(student, fields, [{ key: "risk", op: "eq", value: "baixo" }]), false);
  assert.equal(matchesObjectFilters(student, fields, [{ key: "score", op: "gt", value: 0 }]), false);
  assert.equal(matchesObjectFilters(student, fields, [{ key: "score", op: "empty", value: null }]), true);
});

test("filters use AND and prohibit undeclared properties", () => {
  const row = { id: "1", nome: "Gabriela", score: 82 };
  const fields = [
    { key: "nome", title: "Nome", type: "text", filterable: true, getValue: x => x.nome },
    { key: "score", title: "Score", type: "number", filterable: true, getValue: x => x.score },
  ];
  assert.equal(matchesObjectFilters(row, fields, [
    { key: "nome", op: "contains", value: "Bri" },
    { key: "score", op: "between", value: [80, 90] },
  ]), true);
  assert.equal(matchesObjectFilters(row, fields, [
    { key: "nome", op: "contains", value: "Gab" },
    { key: "score", op: "lt", value: 60 },
  ]), false);
  assert.equal(matchesObjectFilters(row, fields, [
    { key: "email", op: "contains", value: "@" },
  ]), false);
});

test("date-only value remains local calendar date and null never fabricates money", () => {
  assert.equal(formatPropertyValue("date", "2026-11-06"), "06/11/2026");
  assert.equal(formatPropertyValue("currency", null), "—");
  assert.equal(formatPropertyValue("boolean", null), "—");
  assert.equal(formatPropertyValue("boolean", false), "Não");
});

test("view definitions preserve required primary column and drop hidden unknown columns", () => {
  const fields = [
    { key: "nome", title: "Nome", type: "text", primary: true, getValue: row => row.nome },
    { key: "curso", title: "Curso", type: "text", getValue: row => row.curso },
  ];
  const initial = defaultViewSpec(fields);
  assert.deepEqual(JSON.parse(JSON.stringify(initial.columns)), ["nome", "curso"]);
  const validated = validateObjectView(fields, {
    version: 1, filters: [], sort: null, columns: ["malicious", "curso"], page_size: 50,
  });
  assert.deepEqual(JSON.parse(JSON.stringify(validated.columns)), ["nome", "curso"]);
});
