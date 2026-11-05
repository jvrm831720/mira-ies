"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Activity, AlertTriangle, CheckCircle2, Clock3, MessageCircle, Pause, Play, Plus, ShieldCheck } from "lucide-react";
import { Header } from "@/components/layout/header";
import {
  dispatchApi, type DispatchCampaign, type DispatchMetrics,
  type DispatchPaymentResults, type CampaignDraft,
} from "@/lib/dispatch-api";

const initialDraft: CampaignDraft = {
  name: "", purpose: "retention", channel: "email",
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
  return <div className="rounded-xl border border-[#E7E7EA] bg-white px-4 py-4">
    <div className="mb-2 flex items-center gap-2 text-xs text-[#777780]"><Icon className="h-4 w-4" />{label}</div>
    <p className="text-2xl font-semibold tracking-tight text-[#202124]">{value}</p>
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
  const [selected, setSelected] = useState<string | null>(null);
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
    setLoading(false);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
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
        const [kind, ref, obligation] = row.split("|").map((value) => value.trim());
        if (!["student", "external"].includes(kind) || !ref) {
          throw new Error("Formato: student|UUID ou external|referência|obrigação");
        }
        if (current.purpose === "collections" && !obligation) {
          throw new Error("Cobrança exige obrigação: tipo|destinatário|obrigação.");
        }
        return {
          subject_type: kind as "student" | "external", subject_ref: ref,
          consent_ref: consentRef, obligation_ref: obligation || undefined,
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
          <h1 className="text-xl font-semibold text-[#202124]">Central de disparos</h1>
          <p className="mt-1 text-sm text-[#85858B]">Cobranças e permanência, com execução controlada por organização.</p>
        </div>
        <button onClick={() => setShowCreate((value) => !value)} type="button"
          className="inline-flex items-center gap-2 rounded-lg bg-[#202124] px-4 py-2 text-sm font-medium text-white hover:bg-[#35363A]">
          <Plus className="h-4 w-4" /> Nova campanha
        </button>
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-[#E8E3D6] bg-[#FFFCF6] p-4 text-sm text-[#655735]">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <p className="font-semibold">Envio real permanece desabilitado por padrão</p>
          <p className="mt-1">Publicar ou iniciar uma campanha aqui não autoriza automaticamente um provedor.
            Aprovação humana, autorização documentada e configuração operacional separada são obrigatórias.
            Cobrança por WhatsApp permanece bloqueada.</p>
        </div>
      </div>

      {metrics && <p className="text-xs text-[#85858B]">
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

      {showCreate && <section className="space-y-4 rounded-2xl border border-[#E7E7EA] bg-white p-5">
        <h2 className="text-base font-semibold text-[#202124]">Nova campanha</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <label className="text-sm text-[#55555C]">Nome
            <input className="mt-1 w-full rounded-lg border border-[#DADADD] p-2.5" value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Ex.: Lembrete de mensalidade" />
          </label>
          <label className="text-sm text-[#55555C]">Finalidade
            <select className="mt-1 w-full rounded-lg border border-[#DADADD] p-2.5" value={draft.purpose}
              onChange={(e) => setDraft({ ...draft, purpose: e.target.value as CampaignDraft["purpose"],
                channel: e.target.value === "collections" ? "email" : draft.channel })}>
              <option value="retention">Permanência</option>
              <option value="collections">Cobrança</option>
            </select>
          </label>
          <label className="text-sm text-[#55555C]">Canal
            <select className="mt-1 w-full rounded-lg border border-[#DADADD] p-2.5" value={draft.channel}
              onChange={(e) => setDraft({ ...draft, channel: e.target.value as CampaignDraft["channel"] })}>
              <option value="email">E-mail</option>
              <option value="sms">SMS</option>
              {draft.purpose === "retention" && <option value="whatsapp">WhatsApp (simulação)</option>}
            </select>
          </label>
        </div>
        <label className="block text-sm text-[#55555C]">Identificador do modelo
          <input className="mt-1 w-full rounded-lg border border-[#DADADD] p-2.5" value={draft.template_ref}
            onChange={(e) => setDraft({ ...draft, template_ref: e.target.value })} />
        </label>
        <label className="block text-sm text-[#55555C]">Texto do modelo (somente {"{nome}"} será substituído)
          <textarea className="mt-1 w-full rounded-lg border border-[#DADADD] p-2.5" rows={3}
            value={draft.template_body} onChange={(e) => setDraft({ ...draft, template_body: e.target.value })} />
        </label>
        <button type="button" disabled={busy || draft.name.trim().length < 3}
          onClick={() => void create()} className="rounded-lg bg-[#2563EB] px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "Salvando…" : "Criar rascunho"}
        </button>
      </section>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="overflow-hidden rounded-2xl border border-[#E7E7EA] bg-white">
          <div className="border-b border-[#EEEEF0] px-5 py-4">
            <h2 className="font-semibold text-[#202124]">Campanhas</h2>
            <p className="mt-1 text-xs text-[#85858B]">Selecione uma campanha para preparar audiência, aprovar ou controlar execução.</p>
          </div>
          {loading ? <p className="p-6 text-sm text-[#777780]">Carregando…</p>
            : campaigns.length === 0 ? <p className="p-6 text-sm text-[#777780]">Nenhuma campanha criada.</p>
              : <div className="divide-y divide-[#F0F0F2]">
                {campaigns.map((campaign) => <button type="button" key={campaign.id}
                  onClick={() => setSelected(campaign.id)} className={`flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-[#FAFAFA] ${selected === campaign.id ? "bg-[#F5F8FF]" : ""}`}>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-[#202124]">{campaign.name}</div>
                    <div className="mt-1 text-xs text-[#85858B]">{campaign.purpose === "collections" ? "Cobrança" : "Permanência"} · {campaign.channel} · {campaign.total} destinatários</div>
                  </div>
                  <div className="shrink-0 text-right">
                    <span className="rounded-md bg-[#F1F1F2] px-2 py-1 text-[11px] font-medium">{statusLabels[campaign.status]}</span>
                    <p className="mt-1 text-xs text-[#85858B]">{campaign.accepted} aceitas · {campaign.problems} alertas</p>
                  </div>
                </button>)}
              </div>}
        </section>

        <aside className="space-y-4 rounded-2xl border border-[#E7E7EA] bg-white p-5">
          {!current ? <p className="text-sm text-[#85858B]">Selecione uma campanha para gerenciar.</p> : <>
            <h2 className="text-base font-semibold text-[#202124]">{current.name}</h2>
            <p className="text-xs text-[#85858B]">Estado: {statusLabels[current.status]} · {current.total} contatos planejados</p>
            {current.status === "draft" && <>
              <label className="block text-xs font-medium text-[#66666B]">Importar destinatários
                <textarea className="mt-1 w-full rounded-lg border border-[#DADADD] p-2 text-xs" rows={3}
                  value={audience} onChange={(e) => setAudience(e.target.value)}
                  placeholder={"student|UUID\nexternal|referência|obrigação"} />
              </label>
              <label className="block text-xs text-[#66666B]">Referência da autorização de contato
                <input value={consentRef} onChange={(e) => setConsentRef(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#DADADD] p-2" placeholder="Registro institucional ou contratual" />
              </label>
              <button disabled={busy || !audience.trim() || consentRef.length < 8}
                onClick={() => void addTargets()}
                className="w-full rounded-lg border border-[#DADADD] px-3 py-2 text-xs font-medium disabled:opacity-50">
                Adicionar ao outbox
              </button>
              {current.purpose === "retention" && <>
                <label className="block text-xs text-[#66666B]">Ou usar proposta aprovada da MIRA
                  <input value={proposalId} onChange={(e) => setProposalId(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-[#DADADD] p-2" placeholder="ID da proposta" />
                </label>
                <button disabled={busy || !proposalId.trim()} onClick={() => void execute(
                  () => dispatchApi.stageProposal(current.id, proposalId), "Audiência aprovada incorporada.",
                )} className="w-full rounded-lg border border-[#DADADD] px-3 py-2 text-xs font-medium disabled:opacity-50">
                  Importar proposta aprovada
                </button>
              </>}
              <label className="block text-xs text-[#66666B]">Evidência institucional para aprovação
                <input value={approvalRef} onChange={(e) => setApprovalRef(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#DADADD] p-2" placeholder="Número do documento ou autorização" />
              </label>
              <button disabled={busy || current.total < 1 || approvalRef.length < 8}
                onClick={() => void execute(() => dispatchApi.approve(current.id, approvalRef), "Campanha aprovada.")}
                className="w-full rounded-lg bg-[#202124] px-3 py-2 text-xs font-medium text-white disabled:opacity-50">
                <ShieldCheck className="mr-2 inline h-4 w-4" /> Aprovar com segundo usuário
              </button>
            </>}
            {current.status === "approved" && <>
              <label className="block text-xs text-[#66666B]">Agendar para
                <input type="datetime-local" value={scheduleAt}
                  onChange={(e) => setScheduleAt(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#DADADD] p-2" />
              </label>
              <button disabled={!scheduleAt || busy} onClick={() => void execute(
                () => dispatchApi.schedule(current.id, new Date(scheduleAt).toISOString()), "Campanha agendada.",
              )} className="w-full rounded-lg border border-[#DADADD] px-3 py-2 text-xs font-medium disabled:opacity-50">Agendar</button>
              <button disabled={busy} onClick={() => void execute(
                () => dispatchApi.action(current.id, "start"), "Campanha iniciada em modo controlado.",
              )} className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#2563EB] px-3 py-2 text-xs font-medium text-white">
                <Play className="h-3 w-3" /> Iniciar execução
              </button>
            </>}
            {current.status === "scheduled" && <button disabled={busy}
              onClick={() => void execute(() => dispatchApi.action(current.id, "start"), "Campanha iniciada.")}
              className="w-full rounded-lg bg-[#2563EB] px-3 py-2 text-xs font-medium text-white">Iniciar agora</button>}
            {current.status === "running" && <button disabled={busy}
              onClick={() => void execute(() => dispatchApi.action(current.id, "pause"), "Campanha pausada.")}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#DADADD] px-3 py-2 text-xs font-medium">
                <Pause className="h-3 w-3" /> Pausar novas entregas
              </button>}
            {current.status === "paused" && <button disabled={busy}
              onClick={() => void execute(() => dispatchApi.action(current.id, "resume"), "Campanha retomada.")}
              className="w-full rounded-lg bg-[#202124] px-3 py-2 text-xs font-medium text-white">Retomar</button>}
            {!["completed", "cancelled"].includes(current.status) && <button disabled={busy}
              onClick={() => void execute(() => dispatchApi.action(current.id, "cancel"), "Campanha cancelada.")}
              className="w-full rounded-lg px-3 py-2 text-xs font-medium text-red-600 hover:bg-red-50">
              Cancelar pendências
            </button>}
            <div className="border-t border-[#EEEEF0] pt-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#55555C]"><MessageCircle className="h-4 w-4" /> Respostas e ações</div>
              {replies.length === 0
                ? <p className="mt-2 text-xs text-[#85858B]">Nenhuma resposta conciliada.</p>
                : replies.slice(0, 6).map((reply, index) =>
                  <p className="mt-2 rounded bg-[#F7F7F8] px-2 py-1.5 text-xs" key={index}>
                    {reply.reply_intent || reply.event_kind} · {reply.recommended_action || "Recebido"}
                  </p>)}
            </div>
          </>}
        </aside>
      </div>

      <section className="rounded-xl border border-[#E7E7EA] bg-white p-5">
        <h2 className="mb-3 text-sm font-semibold text-[#202124]">Resultados financeiros verificados</h2>
        <div className="flex flex-wrap items-baseline gap-6">
          <p className="text-2xl font-semibold text-[#202124]">{financial
            ? Number(financial.payments.received_brl).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
            : "—"}</p>
          <p className="text-sm text-[#85858B]">{financial?.payments.transactions ?? "—"} pagamentos conciliados</p>
        </div>
        <p className="mt-2 text-xs text-[#85858B]">Valores são provenientes de fatos financeiros verificados, não de entregas ou respostas a campanhas.</p>
      </section>
    </main>
  </>;
}
