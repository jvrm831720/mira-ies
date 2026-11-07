import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = path => readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
const inbox = source("components/work/work-inbox.tsx");
const inspect = source("components/work/work-item-inspector.tsx");
const reason = source("components/work/work-priority-reason.tsx");
const api = source("lib/work-api.ts");
const types = source("types/work.ts");
const center = source("app/(app)/trabalho/page.tsx");

test("WorkInbox exposes four server-backed perspectives with independent full counts", () => {
  for (const perspective of ["mine", "team", "unassigned", "history"]) {
    assert.match(inbox, new RegExp('id: "' + perspective + '"'));
  }
  assert.match(inbox, /workApi\.inbox\(view, offset, PAGE_SIZE\)/);
  assert.match(inbox, /workApi\.inboxCounts\(\)/);
  assert.match(inbox, /has_more/);
  assert.match(inbox, /total\.toLocaleString/);
  assert.match(types, /total_scope: "filtered_workspace_perspective"/);
  assert.equal(inbox.includes("slice(0, 100)"), false);
});

test("sequential outcome processing preserves queue position and moves to next human task", () => {
  assert.match(inbox, /rows\.find\(item => item\.id !== activity\.id/);
  assert.match(inbox, /setSelectedId\(next\?\.id \|\| null\)/);
  assert.match(inbox, /setOffset\(value => Math\.max\(0, value - PAGE_SIZE\)\)/);
  assert.match(inbox, /invalidateQueries\(\{ queryKey: \["work-inbox"/);
  assert.match(inbox, /pendingOperation\.current/);
  assert.match(inbox, /crypto\.randomUUID/);
  assert.match(inbox, /expected_revision/);
  assert.match(inbox, /operation_key/);
});

test("inspector asks for explicit human outcome and authorizes based on assignment", () => {
  assert.match(inspect, /activity\.assignee_user_id === activeUserId/);
  assert.match(inspect, /canEdit && mine/);
  assert.match(inspect, /canEdit && !activity\.assignee_user_id/);
  assert.match(inspect, /<WorkPriorityReason activity=\{activity\}/);
  assert.match(inspect, /<option key=\{item.value\}/);
  assert.match(inspect, /kind === "deferred"/);
  assert.match(inspect, /required value=\{deferUntil\}/);
  assert.match(inspect, /required disabled=\{busy\}/);
  assert.match(inspect, /role="alert"/);
  assert.match(inspect, /events\.data/);
  assert.match(inspect, /history\.slice\(-50\)/);
});

test("priority reasoning never invents a score or financial recovery estimate", () => {
  assert.match(reason, /activity\.priority_reasons \|\| \[\]/);
  assert.match(reason, /Justificativa não disponibilizada/);
  assert.match(reason, /não é score de evasão, chance de pagamento/);
  assert.equal(reason.includes("Math.random"), false);
});

test("new work entry keeps legacy interventions and old activity management available", () => {
  assert.match(center, /<WorkInbox \/>/);
  assert.match(center, /<WorkActivitiesPanel createDraft=/);
  assert.match(center, /<details key=\{unified \? "unified" : "legacy"\} open=\{!unified\}/);
  assert.match(center, /<StudentDrawer studentId=/);
  assert.match(center, /Explorar diagnósticos legados/);
});

test("API mutation routes are separate from intervention dispatch and financial side effects", () => {
  assert.match(api, /\/api\/v1\/work\/activities\/\$\{encodeURIComponent\(id\)\}\/resolve/);
  assert.match(api, /\/api\/v1\/work\/activities\/\$\{encodeURIComponent\(id\)\}\/claim/);
  assert.match(types, /result_semantics\?: "human_work_only"/);
  assert.equal(inbox.includes("updateInterventionLog"), false);
  assert.equal(inbox.includes("payment"), false);
});
