import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");

function load(path) {
  const src = readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
  const result = ts.transpileModule(src, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    reportDiagnostics: true,
  });
  assert.equal(result.diagnostics.filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
  const exports = {};
  vm.runInNewContext(result.outputText, { exports, RegExp, Set, Map, Number, Object });
  return exports;
}
const source = path => readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
const p = load("lib/search-providers.ts");
const ui = source("components/layout/command-palette.tsx");
const api = source("lib/universal-search-api.ts");
const work = source("components/work/work-inbox.tsx");
const campaign = source("app/(app)/campanhas/page.tsx");
const view = source("components/object-index/view-manager.tsx");

const id = "650c805f-bcd8-4ac9-ae35-9639336cb70f";
const groups = [{
  id: "records", label: "Registros", items: [
    { href: "/alunos", label: "Alunos", keywords: "estudantes", permission: "students.view" },
    { href: "/trabalho", label: "Meu Trabalho", keywords: "atividades fila", permission: "access.operator" },
    { href: "/campanhas", label: "Campanhas", keywords: "retenção", permission: "campaigns.view" },
  ],
}];
const hit = (category, href) => ({
  category, href, id, title: "Exemplo", subtitle: category + " · dado autorizado",
  score: 2.8, kind: "navigate",
});

test("all five domain providers have bounded, safe record and view resolvers", () => {
  const all = [
    hit("students", "/alunos/" + id),
    hit("collections", "/cobranca/casos/" + id),
    hit("work", "/trabalho?activity=" + id),
    hit("views", "/alunos?saved_view=" + id),
    hit("campaigns", "/campanhas?proposal=" + id),
  ];
  const only = p.authorizedResults(all, groups);
  assert.deepEqual(Array.from(only, item => item.category), [
    "students", "work", "views", "campaigns",
  ]);
  assert.deepEqual(Array.from(only, item => item.categoryLabel), [
    "Aluno", "Atividade humana", "Visualização", "Campanha",
  ]);
  const expanded = [...groups, { id: "billing", label: "Cobrança", items: [{
    href: "/cobranca", label: "Casos", permission: "audit.view",
  }] }];
  assert.equal(p.authorizedResults(all, expanded).length, 5);
});

test("server href may never inject external URLs, slashes or critical actions", () => {
  const malicious = [
    hit("students", "https://other.example/alunos/" + id),
    hit("work", "/trabalho?activity=" + id + "&confirm=send"),
    hit("views", "/alunos?saved_view=" + id + "&risk=private"),
    hit("campaigns", "/campanhas?execute=" + id),
    hit("students", "/alunos/../../config"),
    hit("collections", "/cobranca/casos/" + id),
  ];
  assert.equal(p.authorizedResults(malicious, groups).length, 0);
  assert.equal(ui.includes("workApi.resolve("), false);
  assert.equal(ui.includes("campaigns.execute"), false);
  assert.match(ui, /router\.push\(result\.href\)/);
});

test("authorized navigation remains available even if some providers fail", () => {
  const options = p.mergeSearchResults([], groups, "alunos");
  assert.equal(options.length, 1);
  assert.equal(options[0].href, "/alunos");
  assert.equal(options[0].category, "navigation");
  assert.equal(p.mergeSearchResults([], groups, "aluns")[0].href, "/alunos");
  assert.equal(p.mergeSearchResults([], groups, "acesso secreto").length, 0);
  assert.match(ui, /remote\.data\?\.partial/);
  assert.match(ui, /remote\.isError/);
  assert.match(ui, /Buscando em registros/);
});

test("Command Palette supports keyboard, focus trap, delayed query and scoped caching", () => {
  assert.match(ui, /event\.key === "ArrowDown"/);
  assert.match(ui, /event\.key === "ArrowUp"/);
  assert.match(ui, /event\.key === "Enter"/);
  assert.match(ui, /event\.key === "Escape"/);
  assert.match(ui, /event\.key !== "Tab"/);
  assert.match(ui, /event\.metaKey \|\| event\.ctrlKey/);
  assert.match(ui, /role="dialog" aria-modal="true"/);
  assert.match(ui, /role="combobox"/);
  assert.match(ui, /role="listbox"/);
  assert.match(ui, /aria-activedescendant/);
  assert.match(ui, /queryKey: \["universal-search", tenantId, userId, debouncedQuery\]/);
  assert.match(ui, /setTimeout\(\(\) => setDebouncedQuery\(query\.trim\(\)\), 180\)/);
  assert.match(ui, /maxLength=\{80\}/);
  assert.match(ui, /itemRefs\.current\[safeSelected\]\?\.scrollIntoView/);
});

test("session-only network search never uses service key or mutates data", () => {
  assert.match(api, /getAccessToken/);
  assert.equal(api.includes("getApiKey"), false);
  assert.match(api, /signal,/);
  assert.match(api, /method: "GET"/);
  assert.match(api, /cache: "no-store"/);
  assert.match(api, /limit=5/);
});

test("search result deep links resolve via domain owners, never direct mutations", () => {
  assert.match(work, /params\.get\("activity"\)/);
  assert.match(work, /setSelectedId\(deepLinkedId\)/);
  assert.match(campaign, /params\.get\("proposal"\)/);
  assert.match(campaign, /proposals\.some\(item => item\.id === linkedProposal\)/);
  assert.match(view, /active\.schema_status === "unsupported"/);
  assert.match(view, /onApply\(active\)/);
  assert.match(view, /hydrated\.current/);
});
