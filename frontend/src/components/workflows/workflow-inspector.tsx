"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, LockKeyhole, ShieldCheck } from "@/components/ui/icons";
import { api } from "@/lib/api";
import type { WorkflowBlock, WorkflowRecord } from "./workflow-model";
import { mayEditProposal } from "./workflow-model";

const stateNames = {
  verified: "Registrado na MIRA",
  pending: "Aguardando etapa",
  attention: "Requer atenção",
  unavailable: "Sem capacidade/evidência disponível",
};

export function WorkflowInspector({
  record, node, canEdit, permissions, onSaved,
}: {
  record: WorkflowRecord;
  node: WorkflowBlock | undefined;
  canEdit: boolean;
  permissions: string[];
  onSaved: () => Promise<unknown>;
}) {
  const [title, setTitle] = useState("");
  const [objective, setObjective] = useState("");
  const [strategy, setStrategy] = useState("");
  const [messageBrief, setMessageBrief] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    setTitle(record.kind === "proposal" ? record.source.title : "");
    setObjective(record.kind === "proposal" ? record.source.objective : "");
    setStrategy(record.kind === "proposal" ? record.source.strategy : "");
    setMessageBrief(record.kind === "proposal" ? record.source.message_brief : "");
    setError(""); setSuccess("");
  }, [record]);

  if (!node) return <aside aria-label="Propriedades do bloco" className="rounded-xl border border-[var(--color-legacy-e6e8ec)] bg-white p-5 text-sm text-[var(--color-legacy-747a86)]">Selecione um bloco do fluxo para consultar suas propriedades.</aside>;

  const canPersist = node.id === "proposal" && mayEditProposal(record, canEdit);
  async function save() {
    if (!canPersist || record.kind !== "proposal" || saving) return;
    setError(""); setSuccess("");
    if (title.trim().length < 3 || objective.trim().length < 3 || strategy.trim().length < 3 || messageBrief.trim().length < 3) {
      setError("Preencha todos os campos com pelo menos 3 caracteres."); return;
    }
    // Native human confirmation; changes can reset previous review/authorization.
    if (!window.confirm("Salvar a alteração na proposta real? A revisão e autorização anteriores podem ser invalidadas pelo backend.")) return;
    setSaving(true);
    try {
      const changes = {
        title: title.trim(), objective: objective.trim(),
        strategy: strategy.trim(), message_brief: messageBrief.trim(),
      };
      await api.updateRetentionCampaignProposal(record.id, changes);
      await onSaved();
      setSuccess("Proposta atualizada no serviço de permanência.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível salvar a proposta.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside aria-label="Propriedades do bloco" className="min-w-0 overflow-hidden rounded-xl border border-[var(--color-legacy-e7e9ee)] bg-white">
      <div className="border-b border-[var(--color-legacy-edf0f2)] px-5 py-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[length:var(--type-overline)] font-semibold uppercase tracking-[0.11em] text-[var(--color-legacy-8a929e)]">Propriedades do bloco</span>
          <span className="rounded-md bg-[var(--color-legacy-f3f5f8)] px-2 py-1 text-[length:var(--type-overline)] text-[var(--color-legacy-626975)]"> {canPersist ? "Persistível" : "Somente leitura"} </span>
        </div>
        <h2 className="text-[length:var(--type-body-comfort)] font-semibold tracking-tight text-[var(--color-legacy-181b21)]">{node.title}</h2>
        <p className="mt-1 text-xs leading-5 text-[var(--color-legacy-737b87)]">{node.description}</p>
      </div>
      <div className="space-y-5 p-5">
        <div className="rounded-lg border border-[var(--color-legacy-edf0f2)] bg-[var(--color-legacy-fafbfc)] p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-[var(--color-legacy-343b45)]">
            {node.state === "verified" ? <CheckCircle2 className="h-4 w-4 text-[var(--color-legacy-287347)]" /> : <LockKeyhole className="h-4 w-4 text-[var(--color-legacy-848b95)]" />}
            {stateNames[node.state]}
          </div>
          <p className="mt-1.5 text-[length:var(--type-caption)] text-[var(--color-legacy-717984)]">Evidência: {node.source}</p>
        </div>
        <div>
          <h3 className="mb-3 text-[length:var(--type-caption)] font-semibold uppercase tracking-[0.09em] text-[var(--color-legacy-818a96)]">Dados verificados</h3>
          <dl className="space-y-3">
            {node.details.map(item => (
              <div key={item.label} className="border-b border-[var(--color-legacy-f0f1f4)] pb-2 last:border-0">
                <dt className="text-[length:var(--type-caption)] text-[var(--color-legacy-858c97)]">{item.label}</dt>
                <dd className="mt-1 break-words text-xs font-medium leading-5 text-[var(--color-legacy-262a31)]">{item.value}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="border-t border-[var(--color-legacy-eef0f3)] pt-4">
          <h3 className="flex items-center gap-2 text-xs font-semibold text-[var(--color-legacy-353943)]"><ShieldCheck className="h-4 w-4 text-[var(--color-legacy-727a88)]" /> Permissão da etapa</h3>
          <p className="mt-2 rounded-md bg-[var(--color-legacy-f6f8fa)] px-2 py-1.5 font-mono text-[length:var(--type-caption)] text-[var(--color-legacy-3f4753)]">{node.requiredPermission}</p>
          <p className="mt-2 text-[length:var(--type-caption)] leading-5 text-[var(--color-legacy-818994)]">
            {permissions.includes(node.requiredPermission) ? "Concedida na sessão do workspace. O serviço valida novamente ao receber a ação." : "Não concedida nesta sessão ou indisponível. Nada pode ser executado aqui."}
          </p>
        </div>
        {canPersist && record.kind === "proposal" && (
          <form onSubmit={event => { event.preventDefault(); void save(); }} className="space-y-3 border-t border-[var(--color-legacy-eef0f3)] pt-4">
            <div>
              <p className="text-xs font-semibold text-[var(--color-legacy-222730)]">Editar configuração persistível</p>
              <p className="mt-1 text-[length:var(--type-caption)] leading-5 text-[var(--color-legacy-7b828d)]">Somente proposta em rascunho/ajustes. A API controla MFA, versão e segregação de funções.</p>
            </div>
            <label className="block text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-59616c)]">Título
              <input name="title" required minLength={3} maxLength={160} value={title} onChange={e => setTitle(e.target.value)}
                className="mt-1 w-full rounded-md border border-[var(--color-legacy-dce1e7)] px-3 py-2 text-xs text-[var(--color-legacy-20242b)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-legacy-2563eb)]" />
            </label>
            <label className="block text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-59616c)]">Objetivo
              <textarea name="objective" required minLength={3} maxLength={4000} rows={3} value={objective} onChange={e => setObjective(e.target.value)}
                className="mt-1 w-full resize-y rounded-md border border-[var(--color-legacy-dce1e7)] px-3 py-2 text-xs text-[var(--color-legacy-20242b)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-legacy-2563eb)]" />
            </label>
            <label className="block text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-59616c)]">Estratégia
              <textarea name="strategy" required minLength={3} maxLength={4000} rows={3} value={strategy} onChange={e => setStrategy(e.target.value)}
                className="mt-1 w-full resize-y rounded-md border border-[var(--color-legacy-dce1e7)] px-3 py-2 text-xs text-[var(--color-legacy-20242b)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-legacy-2563eb)]" />
            </label>
            <label className="block text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-59616c)]">Brief de comunicação
              <textarea name="brief" required minLength={3} maxLength={8000} rows={3} value={messageBrief} onChange={e => setMessageBrief(e.target.value)}
                className="mt-1 w-full resize-y rounded-md border border-[var(--color-legacy-dce1e7)] px-3 py-2 text-xs text-[var(--color-legacy-20242b)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-legacy-2563eb)]" />
            </label>
            {error && <p role="alert" className="text-xs text-[var(--color-legacy-b3261e)]">{error}</p>}
            {success && <p role="status" className="text-xs text-[var(--color-legacy-276749)]">{success}</p>}
            <button type="submit" disabled={saving} className="w-full rounded-lg bg-[var(--color-legacy-202124)] px-3 py-2.5 text-xs font-semibold text-white hover:bg-black disabled:opacity-40">
              {saving ? "Salvando..." : "Salvar na proposta"}
            </button>
          </form>
        )}
        <div className="border-t border-[var(--color-legacy-eef0f3)] pt-4">
          <p className="mb-3 text-[length:var(--type-caption)] text-[var(--color-legacy-868d99)]">Operações críticas continuam no fluxo institucional existente.</p>
          <Link href={record.kind === "proposal" ? "/campanhas" : "/disparos"}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--color-legacy-2563eb)] hover:underline">
            Abrir operação original <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </aside>
  );
}
