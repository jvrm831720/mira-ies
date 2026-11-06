import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const source = readFileSync(new URL("../src/components/layout/navigation.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;
const modules = { exports: {} };
const icons = new Proxy({}, { get: () => (() => null) });
vm.runInNewContext(compiled, {
  module: modules,
  exports: modules.exports,
  require: name => {
    if (name === "@/components/ui/icons") return icons;
    throw new Error("Unexpected navigation dependency: " + name);
  },
}, { filename: "navigation.js" });
const { getVisibleNavigation, searchNavigation, activeNavigationHref } = modules.exports;
const hrefs = groups => groups.flatMap(group => group.items.map(item => item.href));
const education = {
  role: "admin", operation_profile: "institution", permissions: null, custom_role_id: null,
  enabled_modules: ["workspace", "permanence", "data", "mira_plan"],
  available_features: { academic_catalog: true, academic_services: true, academic_operations: true },
};
const collection = {
  role: "admin", operation_profile: "collection", permissions: null, custom_role_id: null,
  enabled_modules: ["workspace", "billing", "data", "mira_plan"],
};

test("education groups expose only existing, authorized routes", () => {
  const groups = getVisibleNavigation(education);
  assert.equal(groups.map(group => group.label).join(","), "Início,Alunos,Inteligência,Operação,Acadêmico,Dados,Configurações");
  assert.equal(hrefs(groups).includes("/academico/servicos"), true);
  assert.equal(hrefs(groups).includes("/cobranca/carteiras"), false);
});

test("collection does not inherit student, permanence or academic screens", () => {
  const links = hrefs(getVisibleNavigation(collection));
  for (const page of ["/alunos", "/monitoramento", "/academico", "/retencao", "/resultados"]) {
    assert.equal(links.includes(page), false, page);
  }
  assert.equal(links.includes("/campanhas"), true);
  assert.equal(links.includes("/disparos"), true);
  assert.equal(links.includes("/conectores"), true);
});

test("runtime academic flags hide unavailable routes despite an active entitlement", () => {
  const gates = {
    ...education,
    available_features: { academic_catalog: true, academic_services: false, academic_operations: false },
  };
  const links = hrefs(getVisibleNavigation(gates));
  assert.equal(links.includes("/academico"), true);
  assert.equal(links.includes("/academico/jornadas"), false);
  assert.equal(links.includes("/academico/servicos"), false);
  assert.equal(hrefs(getVisibleNavigation({ ...education, available_features: undefined })).includes("/academico"), false);
});

test("server entitlement switches off disabled modules", () => {
  const links = hrefs(getVisibleNavigation({ ...education, enabled_modules: ["workspace"] }));
  assert.equal(links.includes("/academico"), false);
  assert.equal(links.includes("/campanhas"), false);
  assert.equal(links.includes("/importar"), false);
  assert.equal(links.includes("/"), true);
});

test("explicit custom role grants do not inherit admin privileges", () => {
  const me = {
    ...education,
    custom_role_id: "custom",
    permissions: ["data.view"],
    enabled_modules: ["data"],
  };
  const links = hrefs(getVisibleNavigation(me));
  assert.equal(links.includes("/conectores"), true);
  assert.equal(links.includes("/importacoes"), true);
  assert.equal(links.includes("/importar"), false);
  assert.equal(links.includes("/membros/cargos"), false);
  assert.equal(links.includes("/"), false);
});

test("failed profile resolution and pending session fail closed", () => {
  assert.equal(hrefs(getVisibleNavigation(null)).length, 0);
  assert.equal(hrefs(getVisibleNavigation({ ...education, permissions: [], custom_role_id: "custom" })).length, 0);
  assert.equal(hrefs(getVisibleNavigation({ ...education, operation_profile: "unknown" })).includes("/academico"), false);
});

test("command search and active route share the permission-filtered catalog", () => {
  const groups = getVisibleNavigation({ ...education, permissions: ["dashboard.view", "data.view"] });
  const results = searchNavigation(groups, "campanhas");
  assert.equal(results.length, 0);
  const data = searchNavigation(groups, "conex");
  assert.equal(data.some(result => result.href === "/conectores"), false);
  assert.equal(searchNavigation(groups, "integr").some(result => result.href === "/conectores"), true);
  assert.equal(activeNavigationHref(getVisibleNavigation(education), "/alunos/grupos/algum-id"), "/alunos/grupos");
  assert.equal(activeNavigationHref(getVisibleNavigation(education), "/academico/jornadas"), "/academico/jornadas");
});
