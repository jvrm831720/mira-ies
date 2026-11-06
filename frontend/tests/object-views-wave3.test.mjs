import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
function loadPure(path) {
  const source = readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
  const result = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    reportDiagnostics: true,
  });
  assert.deepEqual((result.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error), []);
  const holder = { exports: {} };
  vm.runInNewContext(result.outputText, {
    module: holder, exports: holder.exports, URL, URLSearchParams, Intl,
    require: name => { throw new Error("Unexpected import: " + name); },
  });
  return holder.exports;
}

const { defaultViewSpec, validateObjectView } = loadPure("components/object-index/object-index-types.ts");
const { readObjectIndexState, buildIndexHref } = loadPure("lib/navigation-context.ts");
const plain = item => JSON.parse(JSON.stringify(item));
const fields = [
  { key: "nome", title: "Nome", type: "text", primary: true, sortable: true, filterable: true },
  { key: "curso", title: "Curso", type: "text", sortable: true, filterable: true },
  { key: "risk_score", title: "Risco", type: "number", sortable: true, filterable: true, sensitive: true },
];

test("legacy V1 view specs without property labels remain valid", () => {
  const legacy = {
    version: 1, filters: [], sort: { key: "nome", desc: false },
    columns: ["nome", "curso"], page_size: 50,
  };
  const normalized = validateObjectView(fields, legacy);
  assert.equal(normalized.version, 1);
  assert.deepEqual(plain(normalized.property_labels), {});
  assert.deepEqual(plain(normalized.columns), ["nome", "curso"]);
  assert.deepEqual(plain(normalized.sorts), [{ key: "nome", desc: false }]);
});

test("aliases only address known visible columns and do not rewrite actual data keys", () => {
  const current = { ...defaultViewSpec(fields), property_labels: {
    curso: "Programa", nome: "Nome preferido", hidden: "Interno", risk_score: "Risco real",
  }, columns: ["nome", "curso"] };
  const valid = validateObjectView(fields, current);
  assert.deepEqual(plain(valid.property_labels), { curso: "Programa", nome: "Nome preferido" });
  assert.deepEqual(plain(valid.columns), ["nome", "curso"]);
  assert.equal(fields[0].key, "nome");
});

test("saved-view ID and aliases survive filter/pagination/shareable URL roundtrip", () => {
  const uuid = "5c202ad6-c6c1-4ed5-8090-12b0c13e9843";
  const fallback = {
    query: "", view: "todos", savedViewId: null, propertyLabels: {},
    filters: [], sort: null, sorts: [], density: "comfortable", pinned: [],
    columnWidths: {}, columns: ["nome", "curso"], pageIndex: 0, pageSize: 50,
  };
  const state = { ...fallback, savedViewId: uuid,
    propertyLabels: { curso: "Programa", nome: "Nome completo" },
    filters: [{ key: "nome", op: "contains", value: "Ana" }],
    pageIndex: 4,
  };
  const href = buildIndexHref("/alunos", new URLSearchParams("source=internal"), state, null);
  const parsed = readObjectIndexState(new URLSearchParams(href.split("?")[1]), fields,
    [{ id: "todos" }], fallback);
  assert.equal(parsed.savedViewId, uuid);
  assert.deepEqual(plain(parsed.propertyLabels), plain(state.propertyLabels));
  assert.deepEqual(plain(parsed.filters), plain(state.filters));
  assert.equal(parsed.pageIndex, 4);
  assert.match(href, /source=internal/);
});

test("unapproved view IDs and labels are ignored before index is rendered", () => {
  const fallback = {
    query: "", view: "todos", savedViewId: null, propertyLabels: {},
    filters: [], sort: null, sorts: [], columns: ["nome", "curso"],
    density: "comfortable", pinned: [], columnWidths: {}, pageIndex: 0, pageSize: 50,
  };
  const params = new URLSearchParams({
    saved_view: "javascript:alert(1)",
    labels: JSON.stringify({ tenant_id: "Admin", nome: "x", curso: "Programa", risk_score: "Personal" }),
  });
  const publicFields = fields.filter(field => !field.sensitive);
  const state = readObjectIndexState(params, publicFields, [{ id: "todos" }], fallback);
  assert.equal(state.savedViewId, null);
  assert.deepEqual(plain(state.propertyLabels), { curso: "Programa" });
});

test("ViewManager and ObjectIndex integrate server revisions and native catalog", () => {
  const file = path => readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
  const api = file("lib/object-index-api.ts");
  const index = file("components/object-index/object-index.tsx");
  const manager = file("components/object-index/view-manager.tsx");
  assert.match(index, /<ViewManager /);
  assert.match(manager, /expectedRevision|managed\.revision/);
  assert.match(manager, /favoriteSavedObjectView/);
  assert.match(manager, /restoreSavedObjectView/);
  assert.match(manager, /shareSavedObjectView/);
  assert.match(manager, /getObjectSchema/);
  assert.match(api, /class ViewApiError extends Error/);
  assert.match(api, /current_revision/);
  assert.match(index, /propertyLabels: spec\.property_labels/);
});
