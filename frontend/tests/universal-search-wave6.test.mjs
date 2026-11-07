import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const source = path => readFileSync(new URL("../src/" + path, import.meta.url), "utf8");

function loadHelper(path) {
  const compiled = ts.transpileModule(source(path), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    reportDiagnostics: true,
  });
  assert.equal((compiled.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
  const exports = {};
  vm.runInNewContext(compiled.outputText, {
    exports, URL, URLSearchParams, Object, Set, RegExp,
    require: name => { throw new Error("Unexpected runtime dependency: " + name); },
  });
  return exports;
}
const { safeSearchDestination } = loadHelper("lib/search-destinations.ts");
const id = "f68329a7-2b85-4f8c-a4a9-2416fd99e593";
const roots = ["/alunos", "/trabalho", "/cobranca", "/campanhas", "/academico"];
const hit = (provider, href, action = "navigate") => ({
  provider, id, title: "Registro", subtitle: "", href, action, rank: 90, match: "contains",
});

test("the palette permits only grounded in-product destinations", () => {
  assert.equal(safeSearchDestination(hit("students", "/alunos/" + id), roots), true);
  assert.equal(safeSearchDestination(hit("collections", "/cobranca/casos/" + id), roots), true);
  assert.equal(safeSearchDestination(hit("work", "/trabalho?activity=" + id), roots), true);
  assert.equal(safeSearchDestination(hit("views", "/cobranca?saved_view=" + id), roots), true);
  assert.equal(safeSearchDestination(hit("campaigns", "/campanhas?proposal=" + id), roots), true);
  assert.equal(safeSearchDestination(hit("students", "/alunos/" + id), ["/campanhas"]), false);
  assert.equal(safeSearchDestination(hit("views", "/academico?saved_view=" + id), ["/academico"]), true);
});

test("external URLs, malformed IDs, mutation links and forged categories fail closed", () => {
  for (const candidate of [
    hit("students", "https://evil.example/alunos/" + id),
    hit("students", "//evil.example/alunos/" + id),
    hit("students", "/alunos/not-a-uuid"),
    hit("students", "/alunos/" + id + "?run_campaign=1"),
    hit("collections", "/cobranca/casos/" + id + "#preview"),
    hit("work", "/trabalho?activity=" + id + "&execute=1"),
    hit("views", "/cobranca?saved_view=invalid"),
    hit("campaigns", "/api/v1/agents/retention/campaigns/execute"),
    hit("campaigns", "/campanhas"),
    hit("campaigns", "/campanhas?proposal=" + id + "&approve=1"),
    hit("campaigns", "/campanhas", "execute"),
    hit("unknown", "/campanhas"),
  ]) assert.equal(safeSearchDestination(candidate, roots), false, candidate.href);
});

test("federated results are grouped by identity and preserve navigation semantics", () => {
  const palette = source("components/layout/command-palette.tsx");
  assert.match(palette, /searchUniversal\(debouncedQuery, signal\)/);
  assert.match(palette, /tenantId, userId, debouncedQuery/);
  assert.match(palette, /safeSearchDestination\(item, allowedRoots\)/);
  assert.match(palette, /id: item\.provider \+ ":" \+ item\.id/);
  assert.match(palette, /onInputKeyDown/);
  assert.match(palette, /event\.key === "ArrowDown"/);
  assert.match(palette, /event\.key === "ArrowUp"/);
  assert.match(palette, /event\.key === "Enter"/);
  assert.match(palette, /event\.key === "Escape"/);
  assert.match(palette, /event\.key !== "Tab"/);
  assert.match(palette, /role="combobox"/);
  assert.match(palette, /aria-activedescendant/);
  assert.match(palette, /role="listbox"/);
  assert.match(palette, /role="option"/);
  assert.match(palette, /partial/);
  assert.match(palette, /Tentar novamente/);
  assert.match(palette, /router\.push\(href\)/);
  assert.equal(palette.includes("method: \"POST\""), false);
});

test("API client is GET-only, cancelable, bearer-scoped and bounded", () => {
  const api = source("lib/universal-search-api.ts");
  assert.match(api, /getAccessToken\(\)/);
  assert.match(api, /method: "GET"/);
  assert.match(api, /signal,/);
  assert.match(api, /cache: "no-store"/);
  assert.match(api, /q\.length < 2 \|\| q\.length > 80/);
  assert.match(api, /count_scope !== "bounded_matches"/);
  assert.equal(api.includes("getApiKey"), false);
});

test("searching WorkActivity opens an inspector but does not claim or resolve", () => {
  const inbox = source("components/work/work-inbox.tsx");
  const page = source("app/(app)/trabalho/page.tsx");
  assert.match(inbox, /search\.get\("activity"\)/);
  assert.match(inbox, /setSelectedId\(requestedId\)/);
  assert.match(page, /<Suspense fallback=/);
  assert.match(page, /<WorkInbox \/>/);
  const campaigns = source("app/(app)/campanhas/page.tsx");
  assert.match(campaigns, /searchParams\.get\("proposal"\)/);
  assert.match(campaigns, /setPreviewId\(requestedProposal\)/);
  assert.match(campaigns, /<Suspense fallback=/);
});
