import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const base = new URL(".", import.meta.url);
const read = (relative) => readFileSync(new URL(relative, base), "utf8");

test("student shell owns all eight real sections without importing administrative navigation", () => {
  const shell = read("./components/portal-shell.tsx");
  for (const section of ["home","journey","disciplines","calendar","requests","documents","financial","account"]) {
    assert.match(shell, new RegExp('id: "' + section + '"'));
  }
  assert.doesNotMatch(shell, /components\/layout\/navigation|components\/object-index/);
  assert.match(shell, /aria-current/);
  assert.match(shell, /focus-visible:ring/);
  assert.match(shell, /md:hidden/);
});

test("student sessions, claims and sign-out remain on the existing endpoint", () => {
  const page = read("./page.tsx");
  assert.match(page, /student-portal/);
  assert.match(page, /\/claim/);
  assert.match(page, /\/logout/);
  assert.match(page, /#invite=/);
  assert.match(page, /history\.replaceState/);
  assert.doesNotMatch(page, /localStorage|sessionStorage/);
});

test("service timelines omit private notes and financial widgets require API evidence", () => {
  const service = read("./student-services-panel.tsx");
  const history = service.slice(service.indexOf('async function openHistory'), service.indexOf('return (', service.indexOf('async function openHistory')));
  assert.match(history, /setHistory\(/);
  assert.doesNotMatch(history, /event\.note|\.note ?\+/);
  assert.match(service, /payment_received_verified/);
  assert.match(service, /split_settled_verified/);
  assert.match(service, /fetch\("/);
});

test("portal sections are separated without changing administrative app or shared data table", () => {
  const page = read("./page.tsx");
  assert.match(page, /PortalShell/);
  assert.match(page, /AcademicOperationsPanel/);
  assert.match(page, /StudentServicesPanel/);
  assert.match(page, /snapshot|Snapshot|snapshots/i);
  assert.doesNotMatch(page, /api\.students\(/);
});
