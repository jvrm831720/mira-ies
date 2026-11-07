import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");

function loadPure(path, imports = {}) {
  const source = readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    reportDiagnostics: true,
  });
  assert.equal((compiled.diagnostics || []).filter(item => item.category === ts.DiagnosticCategory.Error).length, 0);
  const exports = {};
  vm.runInNewContext(compiled.outputText, {
    exports, URL, URLSearchParams, Intl, Date, Number, Object,
    require: name => {
      if (Object.hasOwn(imports, name)) return imports[name];
      throw new Error("Undeclared runtime dependency: " + name);
    },
  });
  return exports;
}
const plain = value => JSON.parse(JSON.stringify(value));
const adapter = loadPure("components/record/collection-record-data.ts");
const navigation = loadPure("lib/navigation-context.ts");
const { canReadCollectionRecord } = loadPure("components/collections/collection-record-access.ts", {
  "@/components/layout/navigation": {
    hasNavigationPermission: (me, permission) => Array.isArray(me?.permissions) &&
      me.permissions.includes(permission),
  },
});
const example = {
  id: "3dd66c18-39f1-433d-96b9-b4c7fdddb629",
  external_ref: "CASE-057", subject_type: "student", subject_ref: "S-007",
  status: "open", balance: "109.90", source: "ERP verified", source_version: 3,
  evidence_ref: "EV-38", verified_at: "2026-11-05T14:05:00Z",
  updated_at: "2026-11-05T15:20:00Z",
};

test("student and collection have compatible RecordIdentity and distinct domain properties", () => {
  const id = adapter.collectionRecordIdentity(example.id, example);
  assert.equal(id.kind, "case");
  assert.equal(id.id, example.id);
  assert.equal(id.title, "CASE-057");
  const groups = adapter.collectionRecordProperties(example);
  assert.deepEqual(plain(groups.map(group => group.id)), ["identification", "financial"]);
  const props = groups.flatMap(group => group.properties);
  assert.equal(props.find(prop => prop.key === "balance").value, 109.90);
  assert.equal(props.find(prop => prop.key === "verified_at").type, "datetime");
  assert.equal(props.find(prop => prop.key === "status").value, "Aberta");
  assert.equal(props.some(prop => prop.editable || prop.onEdit), false);
  assert.deepEqual(plain(adapter.COLLECTION_RECORD_EDITABLE_FIELDS), []);
  const relations = adapter.collectionRecordRelations(example);
  assert.equal(relations.length, 1);
  assert.equal(relations[0].href, undefined, "External refs may not be assumed to be student UUIDs");
});

test("missing/invalid data is not fabricated, and source-defined paid status is qualified", () => {
  const missing = { ...example, balance: null, verified_at: null, status: "unknown",
    external_ref: "", source: "", subject_ref: "" };
  const record = adapter.collectionRecordIdentity(example.id, missing);
  assert.equal(record.title, "Caso financeiro");
  const props = adapter.collectionRecordProperties(missing).flatMap(g => g.properties);
  assert.equal(props.find(p => p.key === "balance").value, null);
  assert.equal(props.find(p => p.key === "verified_at").value, null);
  assert.equal(props.find(p => p.key === "status").value, "Não determinada");
  assert.equal(adapter.collectionRecordProperties({ ...example, status: "paid" })
    .flatMap(g => g.properties).find(p => p.key === "status").value, "Paga (origem)");
});

test("financial timeline caps source events, flags incomplete data and never forwards evidence payloads", () => {
  const input = Array.from({ length: 121 }, (_, i) => ({
    id: String(i), source: "provider", source_event_id: "src-" + i, source_version: 1,
    amount_paid: "10.50", obligation_status: "open", remaining_balance: "90.00",
    paid_at: "2026-11-05T14:05:00Z", payload: { confidential: "private" },
  }));
  const normalized = adapter.collectionRecordTimeline({
    case: example, payment_events: input, payment_events_limited: false,
  });
  assert.equal(normalized.events.length, adapter.COLLECTION_TIMELINE_LIMIT);
  assert.equal(normalized.truncated, true);
  assert.equal(normalized.events[0].kind, "finance");
  assert.match(normalized.events[0].description, /Valor informado/);
  assert.equal(JSON.stringify(normalized).includes("confidential"), false);
  const none = adapter.collectionRecordTimeline({ case: example, payment_events: [], payment_events_limited: false });
  assert.equal(none.events.length, 0);
  assert.equal(none.truncated, false);
  const limited = adapter.collectionRecordTimeline({ case: example, payment_events: input.slice(0, 2), payment_events_limited: true });
  assert.equal(limited.truncated, true);
});

test("read permissions are consistently denied for unentitled profile or module", () => {
  const read = { operation_profile: "collection", enabled_modules: ["billing"], permissions: ["audit.view"] };
  assert.equal(canReadCollectionRecord(read), true);
  assert.equal(canReadCollectionRecord({ ...read, permissions: [] }), false);
  assert.equal(canReadCollectionRecord({ ...read, operation_profile: "institution" }), true);
  assert.equal(canReadCollectionRecord({ ...read, enabled_modules: ["retention"] }), false);
  assert.equal(canReadCollectionRecord({ ...read, operation_profile: "other" }), false);
  assert.equal(canReadCollectionRecord(null), false);
});

test("expand and return keep list search/sort/page but reject open redirects and other modules", () => {
  const from = "/cobranca?q=Ana&f=%5B%5D&sort=updated_at%3Adesc&page=3&record=" + example.id;
  const safe = navigation.collectionReturnHref(from);
  assert.match(safe, /q=Ana/);
  assert.match(safe, /page=3/);
  assert.equal(safe.includes("record="), false);
  const full = navigation.collectionDetailHref(example.id, from);
  assert.match(full, /\/cobranca\/casos\//);
  assert.equal(new URL(full, "https://mira.invalid").searchParams.get("from"), safe);
  assert.equal(navigation.collectionReturnHref("//evil.example/cobranca"), "/cobranca");
  assert.equal(navigation.collectionReturnHref("/cobranca/casos/" + example.id), "/cobranca");
  assert.equal(navigation.collectionReturnHref("/alunos?x=1"), "/cobranca");
  assert.equal(navigation.collectionReturnHref("https://evil.example"), "/cobranca");
  assert.equal(navigation.collectionDetailHref("not-uuid", from), "/cobranca");
});

test("the student legacy page, student drawer and new case surfaces reuse Record360 primitives", () => {
  const read = path => readFileSync(new URL("../src/" + path, import.meta.url), "utf8");
  const caseSrc = read("components/collections/collection-record-experience.tsx");
  const listing = read("components/collections/collections-experience.tsx");
  const studentPage = read("app/(app)/alunos/[id]/page.tsx");
  const studentDrawer = read("components/students/student-drawer.tsx");
  const legacy = read("components/collections/collection-case-detail.tsx");
  assert.ok(legacy.includes("export function CaseDetail"));
  assert.match(caseSrc, /<RecordDrawer/);
  assert.match(caseSrc, /<RecordPage/);
  assert.match(caseSrc, /<RecordActivity/);
  assert.match(caseSrc, /<RecordLoadState/);
  assert.match(caseSrc, /allowed && Boolean/);
  assert.match(caseSrc, /collectionReturnHref/);
  assert.match(listing, /<CollectionCaseDrawer/);
  assert.match(studentPage, /<Record360Overview/);
  assert.match(studentDrawer, /<Record360Overview/);
  assert.match(studentDrawer, /ConsentPreferencesPanel/);
  assert.ok(existsSync(new URL("../src/app/(app)/cobranca/casos/[id]/page.tsx", import.meta.url)));
});
