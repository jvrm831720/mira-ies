import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const directory = dirname(fileURLToPath(import.meta.url));
const read = path => readFileSync(resolve(directory,path),"utf8");

test("every catalog tile opens a dedicated route, not a drawer", () => {
  const catalog = read("apps-catalog-experience.tsx");
  assert.match(catalog,/href=\{\x60\/apps\/\$\{encodeURIComponent\(item\.id\)\}\x60\}/);
  assert.doesNotMatch(catalog,/setSelected\(|aria-modal="true".*Detalhes de/);
  assert.match(read("../../app/(app)/apps/[slug]/page.tsx"),/AppDetailExperience/);
});

test("detail pages show the Attio-style sections and use permission-scoped live data", () => {
  const detail = read("app-detail-experience.tsx");
  for (const text of ["Visão geral","Como funciona","Como configurar","Sobre o aplicativo","Outros apps em"])
    assert.ok(detail.includes(text),text);
  assert.match(detail,/hasNavigationPermission\(me\.data,"data\.view"\)/);
  assert.match(detail,/hasNavigationPermission\(me\.data,"settings\.manage"\)/);
  assert.match(detail,/startComposioOnboardingConnection/);
  assert.match(detail,/Uma conta registrada ou configurada não garante/);
});

test("vendor logos have a consistent asset chain and never fall back to text initials", () => {
  const logo = read("app-brand-icon.tsx");
  const profiles = read("apps-brand-profiles.ts");
  const catalogModel = read("apps-catalog-model.ts");
  const api = read("../../lib/api.ts");
  assert.match(logo,/localLogos\[item\.id\]/);
  assert.match(logo,/safeHttpsUrl\(item\.logoUrl\)/);
  assert.match(logo,/cdn\.simpleicons\.org/);
  assert.match(logo,/www\.google\.com\/s2\/favicons/);
  assert.doesNotMatch(logo,/item\.initials/);
  assert.doesNotMatch(profiles,/logo:""/);
  for(const id of ["jacad","sponte","sophia"]) {
    assert.match(profiles,new RegExp(id+":\\{about:.*website:"));
  }
  assert.match(catalogModel,/logoUrl:source\.logo/);
  assert.match(api,/logo\?: string \| null; app_url\?: string \| null;/);
});
