import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const root = new URL(".", import.meta.url);
const read = relative => readFileSync(new URL(relative, root), "utf8");

test("Wave 1 has dedicated CPF, email, WhatsApp and one-time-code flow", () => {
  const page = read("./acesso/page.tsx");
  for (const expected of ["/auth/register/request", "/auth/login/request", "/auth/verify", "/auth/me", "/auth/logout"]) {
    assert.ok(page.includes(expected), expected);
  }
  assert.match(page, /type="email"/);
  assert.match(page, /type="tel"/);
  assert.match(page, /inputMode="numeric"/);
  assert.match(page, /requires_identity_verification|identity_verified/);
  assert.doesNotMatch(page, /localStorage|sessionStorage/);
});

test("global student cookie never reaches other workspace APIs", () => {
  const proxy = read("../api/v1/[...path]/route.ts");
  const globalBlock = proxy.slice(proxy.indexOf("if (isGlobalPortal) {"), proxy.indexOf("const hasBody"));
  assert.match(globalBlock, /mira_global_student_session/);
  assert.match(globalBlock, /x-mira-global-portal-action/);
  assert.match(proxy, /if \(isStudentPortal \|\| isGlobalPortal\)/);
  assert.match(proxy, /if \(isStudentPortal\)/);
});

test("legacy institutional academic portal is not reclassified as global", () => {
  const legacy = read("./page.tsx");
  assert.match(legacy, /student-portal/);
  assert.match(legacy, /#invite=/);
  const global = read("./acesso/page.tsx");
  assert.doesNotMatch(global, /student-portal|#invite=|api\.students\(/);
});
