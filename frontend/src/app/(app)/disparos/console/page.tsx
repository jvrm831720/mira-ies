"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Activity, AlertTriangle, CheckCircle2, Clock3, MessageCircle, Pause, Play, Plus, ShieldCheck } from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import {
  dispatchApi, type DispatchCampaign, type DispatchMetrics,
  type DispatchPaymentResults, type CampaignDraft, type DispatchTemplate,
  type DispatchSource,
} from "@/lib/dispatch-api";

const initialDraft: CampaignDraft = {
  name: "", purpose: "retention", channel: "email", delivery_mode: "targeted",
  source_kind: "manual", source_ref: null, source_tool_slug: null,
  template_ref: "Aviso institucional",
  template_body: "Olá {nome}, entre em contato conosco para atendimento.",
  per_minute_limit: 10,
};

const statusLabels: Record<string, string> = {
  draft: "Rascunho", approved: "Aprovada", scheduled: "Agendada",
  running: "Em execução", paused: "Pausada", completed: "Concluída", cancelled: "Cancelada",
};

function Stat({ label, value, icon: Icon }: {
  label: string; value: number | string; icon: typeof Activity;
}) {
  return <div className="rounded-xl border border-[var(--color-legacy-e7e7ea)] bg-white px-4 py-4">
    <div className="mb-2 flex items-center gap-2 text-xs text-[var(--color-legacy-777780)]"><Icon className="h-4 w-4" />{label}</div>
    <p className="text-2xl font-semibold tracking-tight text-[var(--color-legacy-202124)]">{value}</p>
  </div>;
}

export default function DispatchConsolePage() {
  const [campaigns, setCampaigns] = useState<DispatchCampaign[]>([]);
  const [metrics, setMetrics] = useState<DispatchMetrics | null>(null);
  const [financial, setFinancial] = useState<DispatchPaymentResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState<CampaignDraft>(initialDraft);
  const [templates, setTemplates] = useState<DispatchTemplate[]>([]);
  const [sources, setSources] = useState<DispatchSource[]>([]);
  const [composioExecutionAvailable, setComposioExecutionAvailable] = useState(false);
  const [showProposal, setShowProposal] = useState(false);
  const [proposalTemplateId, setProposalTemplateId] = useState("");
  const [showIndividual, setShowIndividual] = useState(false);
  const [individualTemplateId, setIndividualTemplateId] = useState("");
  const [individualSubjectType, setIndividualSubjectType] = useState<"student" | "external">("student");
  const [individualSubjectRef, setIndividualSubjectRef] = useState("");
  const [individualEvidence, setIndividualEvidence] = useState("");
  const [individualSchedule, setIndividualSchedule] = useState("");
  const requestIdRef = useRef<string>("");
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<DispatchCampaign | null>(null);
  const [approvalRef, setApprovalRef] = useState("");
  const [audience, setAudience] = useState("");
  const [consentRef, setConsentRef] = useState("");
  const [proposalId, setProposalId] = useState("");
  const [scheduleAt, setScheduleAt] = useState("");
  const [replies, setReplies] = useState<Array<{
    event_kind: string; reply_intent: string | null; recommended_action: string | null;
    occurred_at: string;
  }>>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [all, summary, payment] = await Promise.allSettled([
      dispatchApi.campaigns(), dispatchApi.metrics(), dispatchApi.financial(),
    ]);
    if (all.status === "fulfilled") setCampaigns(all.value.items);
    else setError(all.reason instanceof Error ? all.reason.message : "Falha ao carregar campanhas.");
    if (summary.status === "fulfilled") setMetrics(summary.value);
    if (payment.status === "fulfilled") setFinancial(payment.value);
    try { setTemplates((await dispatchApi.templates()).items); }
    catch { setTemplates([]); }
    try {
      const catalog = await dispatchApi.sources();
      setSources(catalog.items);
      setComposioExecutionAvailable(catalog.composio_tool_execution_enabled);
    } catch {
      setSources([]);
      setComposioExecutionAvailable(false);
    }
    setLoading(false);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const studentId = params.get("student");
    const originProposal = params.get("proposal");
    if (originProposal) {
      setProposalId(originProposal);
      setShowProposal(true);
      setShowCreate(false);
      setShowIndividual(false);
    }
    if (params.get("mode") === "individual") {
      // Never trigger an action automatically based on a query string.
      if (studentId) { setIndividualSubjectType("student"); setIndividualSubjectRef(studentId); }
      setShowIndividual(true);
      setShowCreate(false);
    }
  }, []);
  useEffect(() => {
    if (!selected) { setSelectedDetail(null); return; }
    dispatchApi.detail(selected).then(value => setSelectedDetail(value.campaign))
      .catch(() => setSelectedDetail(null));
  }, [selected, campaigns]);
  useEffect(() => {
    if (!selected) { setReplies([]); return; }
    dispatchApi.replies(selected).then((value) => setReplies(value.items))
      .catch(() => setReplies([]));
  }, [selected]);

  const current = campaigns.find((item) => item.id === selected) || null;

  async function execute(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      toast.success(success);
      await refresh();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Operação não concluída.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }

  async function individual() {
    if (!individualTemplateId || !individualSubjectRef.trim() || individualEvidence.trim().length < 8) {
      setError("Selecione modelo aprovado, destinatário e autorização válida.");
      return;
    }
    if (!requestIdRef.current) requestIdRef.current = crypto.randomUUID();
    await execute(async () => {
      const result = await dispatchApi.intervene({
        template_id: individualTemplateId,
        subject_type: individualSubjectType,
        subject_ref: individualSubjectRef.trim(),
        evidence_ref: individualEvidence.trim(),
        scheduled_for: individualSchedule
          ? new Date(individualSchedule).toISOString() : undefined,
      }, requestIdRef.current);
      setSelected(result.id);
      requestIdRef.current = "";
      setShowIndividual(false);
      setIndividualSubjectRef("");
      setIndividualEvidence("");
      setIndividualSchedule("");
    }, "Intervenção individual preparada e encaminhada para a fila.");
  }

  async function materializeApprovedProposal() {
    if (!proposalId.trim() || !proposalTemplateId) {
      setError("Selecione uma proposta aprovada e um modelo de permanência aprovado.");
      return;
    }
    await execute(async () => {
      const result = await dispatchApi.materializeRetentionProposal(proposalId.trim(), proposalTemplateId);
      setSelected(result.id);
      setShowProposal(false);
      setProposalTemplateId("");
    }, "Execução vinculada à proposta aprovada, sem nova aprovação de campanha.");
  }

  async function create() {
    await execute(async () => {
      const result = await dispatchApi.create(draft);
      setSelected(result.id);
      setShowCreate(false);
      setDraft(initialDraft);
    }, "Campanha criada como rascunho.");
  }

  async function addTargets() {
    if (!current) return;
    try {
      const rows = audience.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
      if (rows.length > 1000) throw new Error("Limite de 1.000 destinatários por lote.");
      const targets = rows.map((row) => {
        const [kind, ref, evidence, obligation] = row.split("|").map((value) => value.trim());
        const contactEvidence = evidence || consentRef;
        if (!["student", "external"].includes(kind) || !ref) {
          throw new Error("Formato: student|UUID ou external|referência|obrigação");
        }
        if (current.purpose === "collections" && !obligation) {
          throw new Error("Cobrança exige obrigação: tipo|destinatário|obrigação.");
        }
        if (!contactEvidence || contactEvidence.length < 8) {
          throw new Error("Informe autorização vigente por destinatário.");
        }
        return {
          subject_type: kind as "student" | "external", subject_ref: ref,
          consent_ref: contactEvidence, obligation_ref: obligation || undefined,
        };
      });
      await execute(() => dispatchApi.stage(current.id, targets), "Audiência adicionada ao outbox.");
      setAudience("");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Formato de audiência inválido.");
    }
  }

  return <>
    <Header title="Disparos" subtitle="Operação multicanal com controles de autorização, filas e auditoria" />
    <main className="mx-auto max-w-[1400px] space-y-6 px-4 pb-14 pt-6 md:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-legacy-202124)]">Comunicações e intervenções</h1>
          <p className="mt-1 text-sm text-[var(--color-legacy-85858b)]">Um contato individual, um grupo de alunos ou campanhas em escala — com os mesmos controles.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/disparos/importacoes" className="rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-sm font-medium text-[var(--color-legacy-45454c)]">Importações Composio</Link>
          <Link href="/disparos/modelos" className="rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-sm font-medium text-[var(--color-legacy-45454c)]">Modelos e aprovações</Link>
          <Link href="/disparos/provedores" className="rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-sm font-medium text-[var(--color-legacy-45454c)]">Provedores</Link>
          <button onClick={() => { setShowProposal(v => !v); setShowCreate(false); setShowIndividual(false); }} type="button"
            className="rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-sm font-medium text-[var(--color-legacy-45454c)]">
            Usar proposta aprovada
          </button>
          <button onClick={() => { setShowIndividual(v => !v); setShowCreate(false); setShowProposal(false); }} type="button"
            className="rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-sm font-medium text-[var(--color-legacy-202124)]">
            Intervenção individual
          </button>
          <button onClick={() => { setShowCreate(v => !v); setShowIndividual(false); setShowProposal(false); }} type="button"
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-legacy-202124)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-legacy-35363a)]">
            <Plus className="h-4 w-4" /> Nova campanha
          </button>
        </div>
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-[var(--color-legacy-e8e3d6)] bg-[var(--color-legacy-fffcf6)] p-4 text-sm text-[var(--color-legacy-655735)]">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <p className="font-semibold">Envio real permanece desabilitado por padrão</p>
          <p className="mt-1">Publicar ou iniciar uma campanha aqui não autoriza automaticamente um provedor.
            Aprovação humana, autorização documentada e configuração operacional separada são obrigatórias.
            Cobrança por WhatsApp permanece bloqueada.</p>
        </div>
      </div>

      {metrics && <p className="text-xs text-[var(--color-legacy-85858b)]">
        Worker: {metrics.worker_online ? "conectado recentemente" : "sem heartbeat recente"} ·
        Custo estimado dos envios aceitos: {Number(metrics.estimated_cost_brl ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
      </p>}
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat icon={Activity} label="Campanhas" value={metrics?.campaigns ?? "—"} />
        <Stat icon={Clock3} label="Na fila" value={metrics?.queued ?? "—"} />
        <Stat icon={CheckCircle2} label="Aceitas pelo canal" value={metrics?.accepted ?? "—"} />
        <Stat icon={Pause} label="Simuladas" value={metrics?.simulated ?? "—"} />
        <Stat icon={AlertTriangle} label="Problemas" value={metrics?.problems ?? "—"} />
      </div>

      {showProposal && <section className="space-y-4 rounded-2xl border border-[var(--color-legacy-e7e7ea)] bg-white p-5">
        <div>
          <h2 className="text-base font-semibold text-[var(--color-legacy-202124)]">Executar proposta de permanência aprovada</h2>
          <p className="mt-1 text-sm text-[var(--color-legacy-85858b)]">
            Reutiliza a audiência, o histórico de aprovação e as autorizações existentes.
            Não cria um novo processo de aprovação.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-xs text-[var(--color-legacy-55555c)]">Proposta aprovada da MIRA
            <input value={proposalId} onChange={e => setProposalId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm"
              placeholder="ID da proposta aprovada" />
          </label>
          <label className="text-xs text-[var(--color-legacy-55555c)]">Modelo de permanência aprovado
            <select value={proposalTemplateId} onChange={e => setProposalTemplateId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm">
              <option value="">Selecione um modelo</option>
              {templates.filter(t => t.status === "approved" && t.purpose === "retention").map(t =>
                <option key={t.id} value={t.id}>{t.subject} · {t.channel}</option>)}
            </select>
          </label>
        </div>
        <button type="button" disabled={busy || !proposalId.trim() || !proposalTemplateId}
          onClick={() => void materializeApprovedProposal()}
          className="rounded-lg bg-[var(--color-legacy-202124)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          Preparar execução vinculada
        </button>
      </section>}

      {showIndividual && <section className="space-y-4 rounded-2xl border border-[var(--color-legacy-e7e7ea)] bg-white p-5">
        <div>
          <h2 className="text-base font-semibold text-[var(--color-legacy-202124)]">Contato individual</h2>
          <p className="mt-1 text-sm text-[var(--color-legacy-85858b)]">Indicado para retenção, acompanhamento acadêmico ou atendimento. Exige modelo revisado e autorização específica.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-xs text-[var(--color-legacy-55555c)]">Modelo aprovado
            <select value={individualTemplateId} onChange={e => { setIndividualTemplateId(e.target.value); requestIdRef.current = ""; }}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm">
              <option value="">Selecione um modelo</option>
              {templates.filter(t => t.status === "approved" && t.purpose !== "collections").map(t =>
                <option key={t.id} value={t.id}>{t.subject} · {t.channel} · {t.purpose}</option>)}
            </select>
          </label>
          <label className="text-xs text-[var(--color-legacy-55555c)]">Destinatário
            <select value={individualSubjectType} onChange={e => setIndividualSubjectType(e.target.value as "student" | "external")}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm">
              <option value="student">Aluno da MIRA</option><option value="external">Contato externo</option>
            </select>
          </label>
          <label className="text-xs text-[var(--color-legacy-55555c)]">ID do destinatário
            <input value={individualSubjectRef} onChange={e => { setIndividualSubjectRef(e.target.value); requestIdRef.current = ""; }}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm"
              placeholder="UUID do aluno ou referência externa" />
          </label>
          <label className="text-xs text-[var(--color-legacy-55555c)]">Referência de autorização individual
            <input value={individualEvidence} onChange={e => { setIndividualEvidence(e.target.value); requestIdRef.current = ""; }}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" placeholder="Evidência da integração autorizada" />
          </label>
          <label className="text-xs text-[var(--color-legacy-55555c)]">Agendar (opcional)
            <input type="datetime-local" value={individualSchedule} onChange={e => { setIndividualSchedule(e.target.value); requestIdRef.current = ""; }}
              className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5 text-sm" />
          </label>
        </div>
        <button type="button" disabled={busy || !individualTemplateId || !individualSubjectRef || individualEvidence.length < 8}
          onClick={() => void individual()} className="rounded-lg bg-[var(--color-legacy-2563eb)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          Preparar intervenção
        </button>
      </section>}

      {showCreate && <section className="space-y-4 rounded-2xl border border-[var(--color-legacy-e7e7ea)] bg-white p-5">
        <h2 className="text-base font-semibold text-[var(--color-legacy-202124)]">Nova campanha</h2>
        <div className="grid gap-4 md:grid-cols-4">
          <label className="text-sm text-[var(--color-legacy-55555c)]">Nome
            <input className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5" value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Ex.: Lembrete de mensalidade" />
          </label>
          <label className="text-sm text-[var(--color-legacy-55555c)]">Finalidade
            <select className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5" value={draft.purpose}
              onChange={(e) => setDraft({ ...draft, purpose: e.target.value as CampaignDraft["purpose"],
                channel: e.target.value === "collections" ? "email" : draft.channel })}>
              <option value="retention">Permanência</option>
              <option value="academic">Comunicação acadêmica</option>
              <option value="service">Atendimento</option>
              <option value="collections">Cobrança</option>
            </select>
          </label>
          <label className="text-sm text-[var(--color-legacy-55555c)]">Modo
            <select className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5"
              value={draft.delivery_mode} onChange={e => setDraft({ ...draft, delivery_mode: e.target.value as "targeted" | "bulk" })}>
              <option value="targeted">Segmentada (seleção de destinatários)</option>
              <option value="bulk">Em escala (lotes sucessivos)</option>
            </select>
          </label>
          <label className="text-sm text-[var(--color-legacy-55555c)]">Canal
            <select className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5" value={draft.channel}
              onChange={(e) => setDraft({ ...draft, channel: e.target.value as CampaignDraft["channel"] })}>
              <option value="email">E-mail</option>
              <option value="sms">SMS</option>
              {draft.purpose === "retention" && <option value="whatsapp">WhatsApp (simulação)</option>}
            </select>
          </label>
        </div>
        <label className="block text-sm text-[var(--color-legacy-55555c)]">Origem dos dados da organização
          <select className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5"
            value={`${draft.source_kind || "manual"}::${draft.source_ref || ""}`}
            onChange={e => {
              const selectedSource = sources.find(item =>
                `${item.kind}::${item.reference || ""}` === e.target.value);
              if (!selectedSource) return;
              setDraft({
                ...draft, source_kind: selectedSource.kind,
                source_ref: selectedSource.reference,
                source_tool_slug: selectedSource.kind === "composio"
                  ? selectedSource.tools[0] || null : null,
              });
            }}>
            {sources.length === 0 && <option value="manual::">Dados do workspace MIRA</option>}
            {sources.map(source => <option
              key={`${source.kind}::${source.reference || ""}`}
              value={`${source.kind}::${source.reference || ""}`}
              disabled={!source.can_bind}>
              {source.name} · {source.category === "composio" ? "Composio" : source.category === "native" ? "Nativo" : "MIRA"}
              {!source.can_bind ? " (não homologado)" : ""}
            </option>)}
          </select>
        </label>
        {draft.source_kind === "composio" && <label className="block text-sm text-[var(--color-legacy-55555c)]">
          Ferramenta autorizada no workspace
          <select value={draft.source_tool_slug || ""}
            className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5"
            onChange={e => setDraft({ ...draft, source_tool_slug: e.target.value })}>
            {(sources.find(source => source.kind === "composio"
              && source.reference === draft.source_ref)?.tools || []).map(slug =>
                <option key={slug} value={slug}>{slug}</option>)}
          </select>
        </label>}
        <p className="text-xs text-[var(--color-legacy-85858b)]">
          Selecionar uma conexão registra a origem, mas não importa dados automaticamente nem
          autoriza contato. Composio: {composioExecutionAvailable ? "ferramentas sujeitas ao executor autorizado" : "execução de ferramentas desativada"}.
        </p>
        <label className="block text-sm text-[var(--color-legacy-55555c)]">Identificador do modelo
          <input className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5" value={draft.template_ref}
            onChange={(e) => setDraft({ ...draft, template_ref: e.target.value })} />
        </label>
        <label className="block text-sm text-[var(--color-legacy-55555c)]">Texto do modelo (somente {"{nome}"} será substituído)
          <textarea className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2.5" rows={3}
            value={draft.template_body} onChange={(e) => setDraft({ ...draft, template_body: e.target.value })} />
        </label>
        <button type="button" disabled={busy || draft.name.trim().length < 3}
          onClick={() => void create()} className="rounded-lg bg-[var(--color-legacy-2563eb)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "Salvando…" : "Criar rascunho"}
        </button>
      </section>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="overflow-hidden rounded-2xl border border-[var(--color-legacy-e7e7ea)] bg-white">
          <div className="border-b border-[var(--color-legacy-eeeef0)] px-5 py-4">
            <h2 className="font-semibold text-[var(--color-legacy-202124)]">Campanhas</h2>
            <p className="mt-1 text-xs text-[var(--color-legacy-85858b)]">Selecione uma campanha para preparar audiência, aprovar ou controlar execução.</p>
          </div>
          {loading ? <p className="p-6 text-sm text-[var(--color-legacy-777780)]">Carregando…</p>
            : campaigns.length === 0 ? <p className="p-6 text-sm text-[var(--color-legacy-777780)]">Nenhuma campanha criada.</p>
              : <div className="divide-y divide-[var(--color-legacy-f0f0f2)]">
                {campaigns.map((campaign) => <button type="button" key={campaign.id}
                  onClick={() => setSelected(campaign.id)} className={`flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-[var(--color-legacy-fafafa)] ${selected === campaign.id ? "bg-[var(--color-legacy-f5f8ff)]" : ""}`}>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-[var(--color-legacy-202124)]">{campaign.name}</div>
                    <div className="mt-1 text-xs text-[var(--color-legacy-85858b)]">
                    {campaign.purpose === "collections" ? "Cobrança" : campaign.purpose === "retention" ? "Permanência" : "Atendimento"}
                    {" · "}{campaign.delivery_mode === "individual" ? "Contato individual" : campaign.delivery_mode === "bulk" ? "Em escala" : "Segmentada"}
                    {" · "}{campaign.channel}{" · "}{campaign.total} destinatário(s)
                     {" · "}{campaign.source_kind === "retention_proposal" ? "Proposta aprovada da MIRA"
                       : campaign.source_kind === "composio" ? "Composio"
                       : campaign.source_kind === "native" ? "Conector nativo" : "Dados da MIRA"}
                  </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <span className="rounded-md bg-[var(--color-legacy-f1f1f2)] px-2 py-1 text-[length:var(--type-caption)] font-medium">{statusLabels[campaign.status]}</span>
                    <p className="mt-1 text-xs text-[var(--color-legacy-85858b)]">{campaign.accepted} aceitas · {campaign.problems} alertas</p>
                  </div>
                </button>)}
              </div>}
        </section>

        <aside className="space-y-4 rounded-2xl border border-[var(--color-legacy-e7e7ea)] bg-white p-5">
          {!current ? <p className="text-sm text-[var(--color-legacy-85858b)]">Selecione uma campanha para gerenciar.</p> : <>
            <h2 className="text-base font-semibold text-[var(--color-legacy-202124)]">{current.name}</h2>
            <p className="text-xs text-[var(--color-legacy-85858b)]">Estado: {statusLabels[current.status]} · {current.total} contatos planejados</p>
            {selectedDetail && <div className="rounded-lg border border-[var(--color-legacy-e7e7e9)] bg-[var(--color-legacy-fafafa)] p-3">
              <p className="text-xs font-semibold">Prévia do conteúdo em revisão</p>
              <p className="mt-1 text-xs text-[var(--color-legacy-85858b)]">{selectedDetail.template_ref}</p>
              <p className="mt-2 whitespace-pre-wrap text-sm">{selectedDetail.template_body}</p>
              <p className="mt-2 text-xs text-[var(--color-legacy-85858b)]">Variáveis renderizadas somente no momento do contato.</p>
            </div>}
            {current.status === "draft" && <>
              <label className="block text-xs font-medium text-[var(--color-legacy-66666b)]">Importar destinatários
                <textarea className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2 text-xs" rows={3}
                  value={audience} onChange={(e) => setAudience(e.target.value)}
                  placeholder={"student|UUID|autorização\nexternal|referência|autorização|obrigação"} />
              </label>
              <label className="block text-xs text-[var(--color-legacy-66666b)]">Autorização compartilhada (opcional para lote com evidências individuais)
                <input value={consentRef} onChange={(e) => setConsentRef(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2" placeholder="Registro institucional ou contratual" />
              </label>
              <button disabled={busy || !audience.trim()}
                onClick={() => void addTargets()}
                className="w-full rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-xs font-medium disabled:opacity-50">
                Adicionar ao outbox
              </button>
              {current.source_kind === "composio" && <>
                <div className="rounded-lg border border-[var(--color-source-dbeafe)] bg-[var(--color-legacy-f7faff)] p-3 text-xs">
                  <p className="font-semibold text-[var(--color-legacy-1d4ed8)]">Audiência da conexão Composio</p>
                  <p className="mt-1 text-[var(--color-legacy-536276)]">
                    Importe dados na tela de conexões. Somente registros com autorização individual,
                    contato verificado e obrigação financeira elegível entram na fila.
                  </p>
                  <Link href="/disparos/importacoes" className="mt-2 inline-block font-medium text-[var(--color-legacy-2563eb)]">
                    Consultar dados da conexão
                  </Link>
                </div>
                <button type="button" disabled={busy}
                  onClick={() => void execute(async () => {
                    const result = await dispatchApi.stageFromComposio(current.id);
                    toast.message(`${result.filtered} registro(s) não elegível(is) ignorado(s).`);
                  }, "Registros autorizados vinculados à campanha.")}
                  className="w-full rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-xs font-medium disabled:opacity-50">
                  Vincular registros elegíveis importados
                </button>
              </>}
              <label className="block text-xs text-[var(--color-legacy-66666b)]">Evidência institucional para aprovação
                <input value={approvalRef} onChange={(e) => setApprovalRef(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2" placeholder="Número do documento ou autorização" />
              </label>
              <button disabled={busy || current.total < 1 || approvalRef.length < 8}
                onClick={() => void execute(() => dispatchApi.approve(current.id, approvalRef), "Campanha aprovada.")}
                className="w-full rounded-lg bg-[var(--color-legacy-202124)] px-3 py-2 text-xs font-medium text-white disabled:opacity-50">
                <ShieldCheck className="mr-2 inline h-4 w-4" /> Aprovar com segundo usuário
              </button>
            </>}
            {current.status === "approved" && <>
              <label className="block text-xs text-[var(--color-legacy-66666b)]">Agendar para
                <input type="datetime-local" value={scheduleAt}
                  onChange={(e) => setScheduleAt(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[var(--color-legacy-dadadd)] p-2" />
              </label>
              <button disabled={!scheduleAt || busy} onClick={() => void execute(
                () => dispatchApi.schedule(current.id, new Date(scheduleAt).toISOString()), "Campanha agendada.",
              )} className="w-full rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-xs font-medium disabled:opacity-50">Agendar</button>
              <button disabled={busy} onClick={() => void execute(
                () => dispatchApi.action(current.id, "start"), "Campanha iniciada em modo controlado.",
              )} className="flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--color-legacy-2563eb)] px-3 py-2 text-xs font-medium text-white">
                <Play className="h-3 w-3" /> Iniciar execução
              </button>
            </>}
            {current.status === "scheduled" && <button disabled={busy}
              onClick={() => void execute(() => dispatchApi.action(current.id, "start"), "Campanha iniciada.")}
              className="w-full rounded-lg bg-[var(--color-legacy-2563eb)] px-3 py-2 text-xs font-medium text-white">Iniciar agora</button>}
            {current.status === "running" && <button disabled={busy}
              onClick={() => void execute(() => dispatchApi.action(current.id, "pause"), "Campanha pausada.")}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-[var(--color-legacy-dadadd)] px-3 py-2 text-xs font-medium">
                <Pause className="h-3 w-3" /> Pausar novas entregas
              </button>}
            {current.status === "paused" && <button disabled={busy}
              onClick={() => void execute(() => dispatchApi.action(current.id, "resume"), "Campanha retomada.")}
              className="w-full rounded-lg bg-[var(--color-legacy-202124)] px-3 py-2 text-xs font-medium text-white">Retomar</button>}
            {!["completed", "cancelled"].includes(current.status) && <button disabled={busy}
              onClick={() => void execute(() => dispatchApi.action(current.id, "cancel"), "Campanha cancelada.")}
              className="w-full rounded-lg px-3 py-2 text-xs font-medium text-red-600 hover:bg-red-50">
              Cancelar pendências
            </button>}
            <div className="border-t border-[var(--color-legacy-eeeef0)] pt-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-[var(--color-legacy-55555c)]"><MessageCircle className="h-4 w-4" /> Respostas e ações</div>
              {replies.length === 0
                ? <p className="mt-2 text-xs text-[var(--color-legacy-85858b)]">Nenhuma resposta conciliada.</p>
                : replies.slice(0, 6).map((reply, index) =>
                  <p className="mt-2 rounded bg-[var(--color-legacy-f7f7f8)] px-2 py-1.5 text-xs" key={index}>
                    {reply.reply_intent || reply.event_kind} · {reply.recommended_action || "Recebido"}
                  </p>)}
            </div>
          </>}
        </aside>
      </div>

      <section className="rounded-xl border border-[var(--color-legacy-e7e7ea)] bg-white p-5">
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-legacy-202124)]">Resultados financeiros verificados</h2>
        <div className="flex flex-wrap items-baseline gap-6">
          <p className="text-2xl font-semibold text-[var(--color-legacy-202124)]">{financial
            ? Number(financial.payments.received_brl).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
            : "—"}</p>
          <p className="text-sm text-[var(--color-legacy-85858b)]">{financial?.payments.transactions ?? "—"} pagamentos conciliados</p>
        </div>
        <p className="mt-2 text-xs text-[var(--color-legacy-85858b)]">Valores são provenientes de fatos financeiros verificados, não de entregas ou respostas a campanhas.</p>
      </section>
    </main>
  </>;
}
