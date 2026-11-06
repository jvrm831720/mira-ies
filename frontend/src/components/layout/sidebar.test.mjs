import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import vm from "node:vm";
import ts from "typescript";

const folder = dirname(fileURLToPath(import.meta.url));
const file = name => readFileSync(resolve(folder, name), "utf8");
const navJs = ts.transpileModule(file("navigation.ts"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exportsObject = {};
vm.runInNewContext(navJs, {
  exports: exportsObject,
  require() { return new Proxy({}, { get: () => () => null }); },
});
const routes = me => Array.from(exportsObject.getVisibleNavigation(me), group => group.items).flat().map(i => i.href);
const base = {
  operation_profile: "institution",
  permissions: ["dashboard.view", "students.view", "audit.view", "data.view"],
  enabled_modules: ["workspace", "permanence", "data", "billing"],
  available_features: { academic_catalog: true, academic_operations: true, academic_services: true },
};

test("education with billing entitlement and audit permission sees collections", () => {
  assert.equal(routes(base).includes("/cobranca"), true);
  assert.equal(routes({ ...base, enabled_modules: ["workspace", "permanence", "data"] }).includes("/cobranca"), false);
  assert.equal(routes({ ...base, permissions: ["dashboard.view"] }).includes("/cobranca"), false);
});

test("collection-only workspace and unknown custom roles remain permission gated", () => {
  const collection = {
    ...base,
    operation_profile: "collection",
    available_features: {},
    permissions: ["dashboard.view", "audit.view"],
  };
  assert.equal(routes(collection).includes("/cobranca"), true);
  assert.equal(routes({ ...collection, custom_role_id: "custom", permissions: undefined, role: "viewer" }).includes("/cobranca"), false);
  assert.equal(routes({ ...base, available_features: {} }).includes("/academico"), false);
});

test("Attio-style sidebar keeps existing functional contracts instead of fake controls", () => {
  const sidebar = file("sidebar.tsx");
  assert.match(sidebar, /bg-\[var\(--mira-sidebar-bg\)\]/);
  assert.match(file("../../app/globals.css"), /--mira-sidebar-bg: #0B0C0D;/);
  assert.match(sidebar, /md:w-\[275px\]/);
  assert.match(sidebar, /getVisibleNavigation\(me\.data\)/);
  assert.match(sidebar, /switcher\.mutate\(item\)/);
  assert.match(sidebar, /CommandPalette/);
  assert.match(sidebar, /getItem|item\.href|byPath/);
  assert.doesNotMatch(sidebar, /No notifications|Fictitious notification|13 days left on trial!/);
});
