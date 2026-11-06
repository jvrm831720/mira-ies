import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const source = readFileSync(new URL("../src/lib/navigation-context.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  reportDiagnostics: true,
});
const tsErrors = compiled.diagnostics?.filter(d => d.category === ts.DiagnosticCategory.Error) ?? [];
assert.equal(tsErrors.length, 0, tsErrors.map(d => String(d.messageText)).join("\n"));
const modules = { exports: {} };
vm.runInNewContext(compiled.outputText, {
  module: modules,
  exports: modules.exports,
  URL, URLSearchParams,
  require: name => { throw new Error("Unexpected dependency: " + name); },
}, { filename: "navigation-context.js" });

const { readObjectIndexState, readRecordId, buildIndexHref, studentDetailHref,
  studentReturnHref, navigationFingerprint } = modules.exports;
const fields = [
  { key: "nome", type: "text", primary: true, sortable: true, filterable: true },
  { key: "curso", type: "text", sortable: true, filterable: true },
  { key: "risk_level", type: "status", filterable: true },
  { key: "risk_score", type: "number", filterable: true, sortable: true },
];
const views = [{ id: "todos" }, { id: "risco" }];
const defaults = {
  query: "", view: "todos", filters: [], sort: null,
  columns: ["nome", "curso", "risk_level", "risk_score"], pageIndex: 0, pageSize: 50,
};
const uuid = "1ad6fdef-41ce-4770-9e61-9e97ea96a529";
const decode = search => readObjectIndexState(new URLSearchParams(search), fields, views, defaults);
const plain = item => JSON.parse(JSON.stringify(item));

test("legacy deep links preserve the requested student view, text and risk filter", () => {
  const parsed = decode("tab=risco&q=ana&risk=critico");
  assert.equal(parsed.view, "risco");
  assert.equal(parsed.query, "ana");
  assert.deepEqual(plain(parsed.filters), [{ key: "risk_level", op: "eq", value: "critico" }]);
});

test("index context round-trips view, filters, sort, columns, page and size", () => {
  const state = { ...defaults, view: "risco", query: "João", pageIndex: 3, pageSize: 25,
    filters: [{ key: "risk_level", op: "eq", value: "critico" }],
    sort: { key: "risk_score", desc: true }, columns: ["nome", "risk_score"] };
  const href = buildIndexHref("/alunos", new URLSearchParams("source=external&tab=todos"), state, uuid);
  assert.equal(href.startsWith("/alunos?"), true);
  assert.equal(href.includes("source=external"), true);
  const restored = decode(href.split("?")[1]);
  assert.deepEqual(plain(restored), plain(state));
  assert.equal(readRecordId(new URLSearchParams(href.split("?")[1])), uuid);
  assert.equal(href.includes("tab="), false);
});

test("unknown filters, sorts, columns, sizes and views never activate", () => {
  const malicious = JSON.stringify([
    { key: "tenant_id", op: "eq", value: "not-authorized" },
    { key: "nome", op: "contains", value: { injected: true } },
    { key: "risk_level", op: "gt", value: 100 },
  ]);
  const params = new URLSearchParams({
    v: "secret", f: malicious, sort: "tenant_id:desc",
    cols: "tenant_id,curso", page: "-1", size: "500",
    record: "not-a-uuid",
  });
  const restored = decode(params.toString());
  assert.equal(restored.view, "todos");
  assert.deepEqual(plain(restored.filters), []);
  assert.equal(restored.sort, null);
  assert.deepEqual(plain(restored.columns), ["nome", "curso"]);
  assert.equal(restored.pageIndex, 0);
  assert.equal(restored.pageSize, 50);
  assert.equal(readRecordId(params), null);
});

test("URL filters cannot bypass an adapter field allowlist", () => {
  const risk = JSON.stringify([{ key: "risk_score", op: "gt", value: 70 }]);
  const publicFields = fields.filter(field => field.key === "nome" || field.key === "curso");
  const restored = readObjectIndexState(new URLSearchParams("f=" + encodeURIComponent(risk)),
    publicFields, views, defaults);
  assert.deepEqual(plain(restored.filters), []);
});

test("back link remains same-origin and only targets the student list", () => {
  assert.equal(studentReturnHref("/alunos?q=ana&page=2"), "/alunos?q=ana&page=2");
  assert.equal(studentReturnHref("//evil.example/alunos"), "/alunos");
  assert.equal(studentReturnHref("/alunos/../admin"), "/alunos");
  assert.equal(studentReturnHref("/alunos/123"), "/alunos");
  assert.equal(studentReturnHref("https://evil.example/alunos"), "/alunos");
  assert.equal(studentReturnHref("/alunos?record=" + uuid), "/alunos");
});

test("full-page student URL carries the filtered list, not a selected overlay", () => {
  const href = studentDetailHref(uuid, "/alunos?v=risco&page=3&record=" + uuid);
  const url = new URL(href, "https://mira.invalid");
  assert.equal(url.pathname, "/alunos/" + uuid);
  assert.equal(studentReturnHref(url.searchParams.get("from")), "/alunos?v=risco&page=3");
});

test("scroll fingerprints differ by tenant and view and don't embed identifiers or search terms", () => {
  const first = navigationFingerprint("tenant-A:user-A", "/alunos?q=personal-name");
  assert.equal(first, navigationFingerprint("tenant-A:user-A", "/alunos?q=personal-name"));
  assert.notEqual(first, navigationFingerprint("tenant-B:user-A", "/alunos?q=personal-name"));
  assert.notEqual(first, navigationFingerprint("tenant-A:user-A", "/alunos?q=another-name"));
  assert.equal(first.includes("personal-name"), false);
});

test("the shell and both operational object routes use one navigation provider", () => {
  const file = path => readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
  assert.match(file("app/(app)/layout.tsx"), /<NavigationContextProvider>/);
  assert.match(file("components/students/students-list-page.tsx"), /useObjectNavigationState/);
  assert.match(file("components/collections/collections-experience.tsx"), /useObjectNavigationState/);
  assert.match(file("components/students/students-list-page.tsx"), /useObjectScrollRestoration/);
  assert.match(file("components/collections/collections-experience.tsx"), /useObjectScrollRestoration/);
  assert.match(file("app/(app)/alunos/[id]/page.tsx"), /studentReturnHref/);
  assert.match(file("components/layout/sidebar.tsx"), /clearScroll\(\)/);
});
