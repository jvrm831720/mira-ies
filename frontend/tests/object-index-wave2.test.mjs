import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const compile = (path) => {
  const src = readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
  const result = ts.transpileModule(src, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    reportDiagnostics: true,
  });
  assert.deepEqual((result.diagnostics ?? []).filter(d => d.category === ts.DiagnosticCategory.Error), []);
  const sandboxModule = { exports: {} };
  vm.runInNewContext(result.outputText, {
    module: sandboxModule, exports: sandboxModule.exports, URL, URLSearchParams, Intl,
    require: name => { throw new Error("Unexpected import: " + name); },
  });
  return sandboxModule.exports;
};

const { activeSorts, encodeSorts, sortObjectRows, pageSelection, verifiedCount } =
  compile("components/object-index/object-index-experience.ts");
const { readObjectIndexState, buildIndexHref } = compile("lib/navigation-context.ts");
const fields = [
  { key: "nome", title: "Nome", type: "text", primary: true, sortable: true, filterable: true,
    getValue: row => row.nome },
  { key: "curso", title: "Curso", type: "text", sortable: true, filterable: true,
    getValue: row => row.curso },
  { key: "score", title: "Score", type: "number", sortable: true, filterable: true,
    getValue: row => row.score },
];
const defaultState = {
  query: "", view: "todos", filters: [], sort: null, sorts: [],
  columns: ["nome", "curso", "score"], density: "comfortable", pinned: [], columnWidths: {},
  pageIndex: 0, pageSize: 50,
};

const plain = object => JSON.parse(JSON.stringify(object));

test("10k records: stable multisort ranks nulls last with ID tie break", () => {
  const rows = Array.from({ length: 10000 }, (_, i) => ({
    id: String(i).padStart(6, "0"), nome: i % 3 ? "Ana" : "Bruno",
    curso: i % 2 ? "Direito" : "Administração",
    score: i % 7 ? i % 100 : null,
  }));
  const sorts = [{ key: "nome", desc: false }, { key: "curso", desc: true },
    { key: "score", desc: true }];
  const result = sortObjectRows(rows, fields, sorts);
  assert.equal(result.length, 10000);
  assert.equal(rows[0].id, "000000");
  for (let i = 1; i < result.length; i++) {
    const a = result[i - 1], b = result[i];
    if (a.nome !== b.nome) assert.ok(a.nome.localeCompare(b.nome, "pt-BR") <= 0);
    if (a.nome === b.nome && a.curso !== b.curso) {
      assert.ok(a.curso.localeCompare(b.curso, "pt-BR") >= 0);
    }
    if (a.nome === b.nome && a.curso === b.curso &&
      a.score !== null && b.score !== null) assert.ok(a.score >= b.score);
  }
});

test("safe counters reject fabricated global totals for partial and remote previews", () => {
  assert.equal(verifiedCount(true, false, 2744), 2744);
  assert.equal(verifiedCount(true, false, undefined), null);
  assert.equal(verifiedCount(true, true, 2744), null);
  assert.equal(verifiedCount(true, false, -1), null);
  assert.equal(verifiedCount(true, false, Infinity), null);
});

test("page selection excludes stale and off-page IDs", () => {
  const page = [{ id: "1" }, { id: "2" }, { id: "3" }];
  const selected = pageSelection(page, { "1": true, "9": true, "2": false });
  assert.deepEqual(plain(selected), [{ id: "1" }]);
});

test("multisort deduplicates keys and caps the configured criteria at three", () => {
  const items = [{ key: "nome", desc: false }, { key: "nome", desc: true },
    { key: "curso", desc: true }, { key: "score", desc: false }, { key: "other", desc: false }];
  assert.deepEqual(plain(activeSorts({ sort: null, sorts: items })), plain([
    items[0], items[2], items[3],
  ]));
  assert.equal(encodeSorts(items.slice(0, 3)), "nome:asc,nome:desc,curso:desc");
});

test("URL round-trips density, pinned columns, widths and multisort without unsafe fields", () => {
  const state = {
    ...defaultState, sorts: [{ key: "nome", desc: false }, { key: "score", desc: true }],
    sort: { key: "nome", desc: false }, density: "compact",
    pinned: ["nome"], columnWidths: { nome: 280, score: 140 }, pageIndex: 2,
  };
  const href = buildIndexHref("/alunos", new URLSearchParams(), state, null);
  const result = readObjectIndexState(new URLSearchParams(href.split("?")[1]), fields,
    [{ id: "todos" }], defaultState);
  assert.equal(result.density, "compact");
  assert.deepEqual(plain(result.sorts), plain(state.sorts));
  assert.deepEqual(plain(result.pinned), ["nome"]);
  assert.deepEqual(plain(result.columnWidths), plain(state.columnWidths));
  assert.equal(result.pageIndex, 2);
  const hostile = readObjectIndexState(new URLSearchParams({
    sorts: "tenant_id:desc,score:asc", pinned: "tenant_id,nome",
    widths: JSON.stringify({ tenant_id: 500, score: 1200, nome: 250 }),
  }), fields, [{ id: "todos" }], defaultState);
  assert.deepEqual(plain(hostile.sorts), [{ key: "score", desc: false }]);
  assert.deepEqual(plain(hostile.pinned), ["nome"]);
  assert.deepEqual(plain(hostile.columnWidths), { nome: 250 });
});

test("UI uses accessible keyboard rows, pinned resizing and page-scoped selection", () => {
  const file = path => readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
  const table = file("components/object-index/object-data-table.tsx");
  const index = file("components/object-index/object-index.tsx");
  assert.match(table, /data-record-row tabIndex=\{0\}/);
  assert.match(table, /event\.key === "ArrowDown"/);
  assert.match(table, /event\.key === "Enter"/);
  assert.match(table, /role="separator"/);
  assert.match(table, /getResizeHandler/);
  assert.match(table, /getIsPinned/);
  assert.match(table, /getIsAllPageRowsSelected/);
  assert.match(index, /pageSelection\(visibleRows, selected\)/);
  assert.match(index, /verifiedCount\(true, partial, total\)/);
});
