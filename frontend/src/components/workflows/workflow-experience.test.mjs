import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import vm from "node:vm";
import ts from "typescript";

const folder = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(folder, "workflow-model.ts"), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exportsObject = {};
vm.runInNewContext(output, { exports: exportsObject, require() { throw new Error("No runtime dependency expected"); } });
const { blocksForWorkflow, mayEditProposal, statusLabel, workflowRecords } = exportsObject;

const proposal = {
  id: "p-one", tenant_id: "tenant-a", title: "Jornada de permanência",
  status: "approved", revision: 2, updated_at: "2026-11-05T09:00:00Z",
  created_at: "2026-11-05T08:00:00Z", created_by: "one",
  objective: "Evitar evasão", strategy: "Ações internas", message_brief: "Não enviar sem autorização",
  source_group_ids: ["group-a"], source_catalog_version: "catalog-1",
  audience_total: 18, outreach_eligible_count: 6, blocked_count: 12, internal_action_count: 12,
  recommended_channels: ["operacao_interna"],
  reviewed_at: "2026-11-05T08:30:00Z", reviewed_by: "two",
  authorization_status: "institution_attested", authorization_attested_at: "2026-11-05T08:40:00Z",
  approved_at: "2026-11-05T08:50:00Z", approved_by: "three",
  scheduled_for: null, schedule_timezone: null, execution_enabled: false,
};
const dispatch = {
  id: "d-one", name: "Atendimento segmentado", purpose: "retention", delivery_mode: "targeted",
  channel: "email", status: "draft", template_ref: "template-a", created_at: "2026-11-05T12:00:00Z",
  scheduled_for: null, approved_at: null, approved_by: null, total: 0, pending: 0,
  accepted: 0, simulated: 0, problems: 0, replied: 0, paused_reason: null,
  origin_proposal_id: null,
};

test("approved proposal does not imply dispatch or completed run", () => {
  const record = workflowRecords([proposal], [])[0];
  const blocks = blocksForWorkflow(record);
  assert.equal(blocks.find(b => b.id === "approval").state, "verified");
  assert.equal(blocks.find(b => b.id === "schedule").state, "pending");
  assert.equal(blocks.find(b => b.id === "handoff").state, "unavailable");
  assert.equal(blocks.find(b => b.id === "outcome").state, "unavailable");
  assert.equal(blocks.find(b => b.id === "eligibility").details[1].value, "12");
  assert.equal(statusLabel("approved", "proposal"), "Aprovada");
});

test("scheduled proposal is only schedule metadata, not a run", () => {
  const record = workflowRecords([{ ...proposal, status: "scheduled", scheduled_for: "2026-11-06T10:00:00Z" }], [])[0];
  const blocks = blocksForWorkflow(record);
  assert.equal(blocks.find(b => b.id === "schedule").state, "verified");
  assert.equal(blocks.find(b => b.id === "outcome").state, "unavailable");
});

test("only real correlated dispatch can complete handoff and outcome evidence", () => {
  const record = workflowRecords([proposal], [])[0];
  const unrelated = { ...dispatch, id: "d-foreign", origin_proposal_id: "someone-else", status: "completed", accepted: 30 };
  const linked = { ...dispatch, origin_proposal_id: proposal.id, status: "running", accepted: 2 };
  assert.equal(blocksForWorkflow(record, [unrelated]).find(b => b.id === "handoff").state, "unavailable");
  const blocks = blocksForWorkflow(record, [linked]);
  assert.equal(blocks.find(b => b.id === "handoff").state, "verified");
  assert.equal(blocks.find(b => b.id === "outcome").state, "verified");
  assert.equal(blocks.find(b => b.id === "outcome").details[1].value, "2");
});

test("edit permission is state constrained and dispatch cannot be edited as proposal", () => {
  const draft = workflowRecords([{ ...proposal, status: "draft" }], [])[0];
  const approved = workflowRecords([proposal], [])[0];
  const camp = workflowRecords([], [dispatch])[0];
  assert.equal(mayEditProposal(draft, true), true);
  assert.equal(mayEditProposal(draft, false), false);
  assert.equal(mayEditProposal(approved, true), false);
  assert.equal(mayEditProposal(camp, true), false);
});

test("workflow index keeps real source IDs; statuses never translated to published", () => {
  const result = workflowRecords([proposal], [dispatch]);
  assert.equal(result[0].id, "d-one");
  assert.equal(result[1].id, "p-one");
  assert.equal(statusLabel("scheduled", "proposal"), "Agendada (metadados)");
});

test("canvas is only presentation; execution POST, Composio write and payment hooks are absent", () => {
  const files = ["workflow-experience.tsx", "workflow-canvas.tsx", "workflow-inspector.tsx"];
  const texts = files.map(name => readFileSync(resolve(folder, name), "utf8"));
  const joined = texts.join("\n");
  assert.doesNotMatch(joined, /dispatchApi\.(action|schedule|approve|create|stage|importComposio|materializeRetentionProposal)\(/);
  assert.doesNotMatch(joined, /method:\s*["']POST["']/);
  assert.doesNotMatch(joined, /(?:payments|asaas|webhook).*\(/i);
  assert.match(joined, /updateRetentionCampaignProposal/);
  assert.match(joined, /window\.confirm/);
  assert.match(joined, /getVisibleNavigation/);
  assert.match(joined, /hasNavigationPermission/);
  assert.match(joined, /origin_proposal_id/);
  assert.match(joined, /composioImportHistory/);
});

test("access, typing and empty-state experience remain explicit", () => {
  const ui = readFileSync(resolve(folder, "workflow-experience.tsx"), "utf8");
  const canvas = readFileSync(resolve(folder, "workflow-canvas.tsx"), "utf8");
  assert.match(ui, /!allowed/);
  assert.match(ui, /role="alert"/);
  assert.match(ui, /Sem permissão/);
  assert.match(ui, /Nenhum processo encontrado/);
  assert.match(canvas, /ArrowDown/);
  assert.match(canvas, /aria-pressed/);
  assert.match(canvas, /aria-label="Canvas do processo"/);
});
