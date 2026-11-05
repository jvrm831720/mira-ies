"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Clock3,
  FileCheck2,
  Layers,
  Mail,
  MessageCircle,
  Pause,
  Play,
  Plus,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Users,
  Workflow,
  XCircle,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { loadGroupMemberIds } from "@/lib/retention-audience";
import type { RiskLevel, RetentionCampaignOpportunity, RetentionRunResult } from "@/types/api";

const steps = [
  { id: "planejar", label: "Planejar", detail: "Público, estratégia e régua" },
  { id: "aprovar", label: "Aprovar", detail: "Revisão e permissões" },
  { id: "executar", label: "Executar", detail: "Acompanhamento operacional" },
] as const;
type Step = (typeof steps)[number]["id"];

const levelOptions: { value: RiskLevel; title: string; detail: string; color: string }[] = [
  { value: "critico", title: "Crítico", detail: "Prioridade imediata", color: "var(--brand-coral)" },
  { value: "medio", title: "Médio", detail: "Acompanhamento próximo", color: "var(--brand-indigo)" },
  { value: "baixo", title: "Baixo", detail: "Baixa prioridade", color: "var(--brand-blue)" },
];
const channelItems = [
  { key: "whatsapp", label: "WhatsApp", icon: MessageCircle },
  { key: "email", label: "E-mail", icon: Mail },
  { key: "sms", label: "SMS", icon: Smartphone },
] as const;
const statusLabels: Record<string, string> = {
  draft: "Rascunho",
  in_review: "Em revisão",
  changes_requested: "Ajustes solicitados",
  approved: "Aprovada",
};

function formatNumber(value: number) {
  return value.toLocaleString("pt-BR");
}

function PlanningPanel({
  onNavigate,
  onRun,
  running,
}: {
  onNavigate: (step: Step) => void;
  onRun: (payload: { levels: RiskLevel[]; studentIds: string[]; campaign: string; dryRun: boolean; channels: string[] }) => Promise<void>;
  running: boolean;
}) {
  const searchParams = useSearchParams();
  const groupFromUrl = searchParams.get("group")?.trim() || "";
  const campaignFromUrl = searchParams.get("campaign")?.trim() || "";
  const [source, setSource] = useState<"manual" | "intelligent">("manual");
  const [campaign, setCampaign] = useState(campaignFromUrl);
  const [levels, setLevels] = useState<RiskLevel[]>(["critico"]);
  const [channels, setChannels] = useState<string[]>(["whatsapp", "email"]);
  const [dryRun, setDryRun] = useState(true);
  const [selectedGroups, setSelectedGroups] = useState<string[]>(groupFromUrl ? [groupFromUrl] : []);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [audienceLoading, setAudienceLoading] = useState(false);
  const [intelligentSelection, setIntelligentSelection] = useState<RetentionCampaignOpportunity | null>(null);

  const summaryQuery = useQuery({ queryKey: ["student-groups", "summary"], queryFn: () => api.studentGroupsSummary() });
  const opportunitiesQuery = useQuery({
    queryKey: ["retention-campaign-opportunities"],
    queryFn: () => api.retentionCampaignOpportunities(),
    enabled: source === "intelligent",
  });
  useEffect(() => {
    if (!groupFromUrl) return;
    setSelectedGroups([groupFromUrl]);
    setSource("manual");
  }, [groupFromUrl]);

  async function loadAudience(groupIds: string[]) {
    setSelectedGroups(groupIds);
    if (!groupIds.length) {
      setSelectedIds([]);
      return;
    }
    setAudienceLoading(true);
    try {
      const results = await Promise.all(groupIds.map((groupId) => loadGroupMemberIds(groupId)));
      const ids = [...new Set(results.flatMap((result) => result.ids))];
      setSelectedIds(ids);
      if (results.some((result) => result.truncated)) toast.message("O público foi carregado parcialmente; revise a cobertura antes de executar.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível carregar o público do grupo.");
    } finally {
      setAudienceLoading(false);
    }
  }

  function applyOpportunity(opportunity: RetentionCampaignOpportunity) {
    setIntelligentSelection(opportunity);
    setCampaign(`Campanha · ${opportunity.group_name}`);
    setChannels(opportunity.recommended_channels.filter((channel) => channel !== "operacao_interna"));
    setSelectedGroups([opportunity.group_id]);
    void loadAudience([opportunity.group_id]);
  }

  function toggleLevel(level: RiskLevel) {
    setLevels((current) => current.includes(level) ? current.filter((item) => item !== level) : [...current, level]);
  }

  function toggleChannel(channel: string) {
    setChannels((current) => current.includes(channel) ? current.filter((item) => item !== channel) : [...current, channel]);
  }

  return (
    <div className="space-y-5">
      <Card className="overflow-hidden">
        <CardHeader className="border-b bg-[#FCFCFD]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Monte a intervenção</CardTitle>
              <CardDescription>Escolha uma recomendação da inteligência ou crie uma campanha manual com critérios operacionais.</CardDescription>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800"><ShieldCheck className="h-3.5 w-3.5" /> Opt-out e intervalos sempre ativos</span>
          </div>
        </CardHeader>
        <CardContent className="space-y-6 p-5">
          <div className="grid gap-3 md:grid-cols-2">
            <button type="button" onClick={() => setSource("manual")} className={`rounded-xl border p-4 text-left transition ${source === "manual" ? "border-primary bg-primary/5 shadow-[0_0_0_2px_rgba(64,80,205,0.08)]" : "border-border hover:bg-muted/40"}`}>
              <div className="flex items-center gap-2"><Plus className="h-4 w-4 text-primary" /><span className="font-semibold">Campanha manual</span></div>
              <p className="mt-1 text-xs text-muted-foreground">Defina nome, risco, grupo, canais e público da execução.</p>
            </button>
            <button type="button" onClick={() => setSource("intelligent")} className={`rounded-xl border p-4 text-left transition ${source === "intelligent" ? "border-primary bg-primary/5 shadow-[0_0_0_2px_rgba(64,80,205,0.08)]" : "border-border hover:bg-muted/40"}`}>
              <div className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /><span className="font-semibold">Campanha inteligente</span></div>
              <p className="mt-1 text-xs text-muted-foreground">Use oportunidades explicáveis e envie a proposta para aprovação.</p>
            </button>
          </div>

          {source === "intelligent" ? (
            <div className="space-y-3 rounded-xl border border-[#D9D6FE] bg-[#F9F8FF] p-4">
              <div className="flex items-center justify-between gap-3"><div><p className="text-sm font-semibold">Oportunidades recomendadas</p><p className="text-xs text-muted-foreground">A recomendação é determinística e explicável; a mensagem ainda precisa de revisão humana.</p></div><Link href="/campanhas" className="text-xs font-semibold text-primary underline underline-offset-2">Abrir aprovações</Link></div>
              {opportunitiesQuery.isLoading ? <div className="space-y-2"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div> : opportunitiesQuery.isError ? <p className="text-sm text-red-600">Não foi possível carregar as oportunidades para seu perfil.</p> : (opportunitiesQuery.data?.opportunities ?? []).length === 0 ? <p className="text-sm text-muted-foreground">Nenhuma oportunidade disponível no momento.</p> : <div className="grid gap-2 lg:grid-cols-2">{(opportunitiesQuery.data?.opportunities ?? []).map((opportunity) => { const selected = intelligentSelection?.group_id === opportunity.group_id; return <button key={opportunity.group_id} type="button" onClick={() => applyOpportunity(opportunity)} className={`rounded-lg border p-3 text-left ${selected ? "border-primary bg-white" : "border-border bg-white hover:border-primary/40"}`}><div className="flex items-start justify-between gap-2"><span className="text-sm font-semibold">{opportunity.group_name}</span><span className="rounded-full bg-muted px-2 py-1 text-[10px] font-semibold">{formatNumber(opportunity.matched_count)} alunos</span></div><p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{opportunity.objective}</p><div className="mt-2 flex items-center gap-1 text-[11px] font-medium text-primary">Usar recomendação <ChevronRight className="h-3 w-3" /></div></button>; })}</div>}
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_260px]">
            <div className="space-y-4">
              <label className="block space-y-1.5 text-sm font-medium">Nome da campanha<Input value={campaign} onChange={(event) => setCampaign(event.target.value)} placeholder="Ex.: Acolhimento — críticos financeiros" /></label>
              <div><p className="mb-2 text-sm font-medium">Segmentação por risco</p><div className="grid gap-2 sm:grid-cols-3">{levelOptions.map((option) => { const checked = levels.includes(option.value); return <button type="button" key={option.value} aria-pressed={checked} onClick={() => toggleLevel(option.value)} disabled={selectedIds.length > 0} className={`flex items-center gap-2 rounded-lg border p-3 text-left ${checked ? "border-primary bg-primary/5" : "border-border hover:bg-muted/30"} ${selectedIds.length > 0 ? "opacity-60" : ""}`}><span className="grid h-4 w-4 place-items-center rounded-full border" style={checked ? { borderColor: option.color, backgroundColor: option.color, color: "white" } : undefined}>{checked ? <Check className="h-3 w-3" /> : null}</span><span><span className="block text-xs font-semibold">{option.title}</span><span className="block text-[10px] text-muted-foreground">{option.detail}</span></span></button>; })}</div></div>
              <div><p className="mb-2 text-sm font-medium">Canais permitidos</p><div className="flex flex-wrap gap-2">{channelItems.map(({ key, label, icon: Icon }) => { const checked = channels.includes(key); return <button key={key} type="button" aria-pressed={checked} onClick={() => toggleChannel(key)} className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold ${checked ? "border-primary bg-primary/5 text-primary" : "border-border text-muted-foreground hover:bg-muted/30"}`}><Icon className="h-3.5 w-3.5" />{label}</button>; })}</div></div>
            </div>
            <div className="space-y-3 rounded-xl bg-muted/35 p-4">
              <div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Público</p><p className="mt-1 text-2xl font-semibold tabular-nums">{audienceLoading ? "…" : formatNumber(selectedIds.length)}</p><p className="text-xs text-muted-foreground">alunos selecionados</p></div>
              <div className="border-t pt-3"><p className="text-xs font-semibold">Grupos de alunos</p><div className="mt-2 max-h-32 space-y-1 overflow-y-auto">{(summaryQuery.data?.groups ?? []).map((group) => { const checked = selectedGroups.includes(group.id); return <label key={group.id} className="flex cursor-pointer items-center gap-2 text-xs"><input type="checkbox" checked={checked} onChange={() => void loadAudience(checked ? selectedGroups.filter((id) => id !== group.id) : [...selectedGroups, group.id])} /><span className="truncate">{group.name}</span><span className="ml-auto text-muted-foreground">{formatNumber(group.matched_count)}</span></label>; })}</div></div>
              {selectedGroups.length === 0 ? <p className="text-[11px] leading-relaxed text-muted-foreground">Sem grupo: a régua usa os níveis de risco selecionados e o limite operacional.</p> : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
            <label className="flex items-start gap-2 text-xs text-muted-foreground"><input type="checkbox" className="mt-0.5" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} /><span><span className="font-semibold text-foreground">Dry-run recomendado</span><br />Simula a execução sem enviar mensagens reais.</span></label>
            <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => onNavigate("aprovar")}><FileCheck2 className="mr-2 h-4 w-4" />Ver aprovações</Button><Button disabled={running || (!campaign.trim() && source === "manual")} onClick={() => void onRun({ levels, studentIds: selectedIds, campaign, dryRun, channels })}>{running ? "Preparando…" : dryRun ? "Simular intervenção" : "Executar intervenção"}<ChevronRight className="ml-2 h-4 w-4" /></Button></div>
          </div>
        </CardContent>
      </Card>
      {selectedGroups.length > 0 ? <div className="flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-xs text-blue-900"><Layers className="h-4 w-4 shrink-0" /><span><strong>{selectedGroups.length} grupo(s) selecionado(s).</strong> O público será deduplicado e as regras de opt-out, preferências e intervalo serão aplicadas no processamento.</span></div> : null}
      {intelligentSelection ? <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900"><AlertTriangle className="mr-2 inline h-4 w-4" />{intelligentSelection.safeguards[0]} A proposta completa pode ser revisada em Campanhas inteligentes.</div> : null}
    </div>
  );
}

function ApprovalPanel({ onPlan }: { onPlan: () => void }) {
  const queryClient = useQueryClient();
  const proposalsQuery = useQuery({ queryKey: ["retention-campaign-proposals"], queryFn: () => api.retentionCampaignProposals() });
  const proposals = proposalsQuery.data?.proposals ?? [];
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const selected = proposals.find((proposal) => proposal.id === selectedId) ?? proposals[0] ?? null;
  useEffect(() => { if (selected && !selectedId) setSelectedId(selected.id); }, [selected, selectedId]);
  async function createProposal() { if (!selected) return; setBusy(true); try { await api.createRetentionCampaignProposal(selected.source_group_ids); toast.success("Nova proposta gerada a partir dos grupos selecionados."); await queryClient.invalidateQueries({ queryKey: ["retention-campaign-proposals"] }); } catch (error) { toast.error(error instanceof Error ? error.message : "Não foi possível gerar a proposta."); } finally { setBusy(false); } }
  return <div className="space-y-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm text-muted-foreground">{formatNumber(proposals.length)} propostas no tenant</p><p className="mt-1 text-xs text-muted-foreground">Aprovação, atestado institucional e execução ficam separados por permissão.</p></div><Button variant="outline" onClick={onPlan}><Plus className="mr-2 h-4 w-4" />Criar outra no planejamento</Button></div>{proposalsQuery.isLoading ? <Card><CardContent className="p-6"><Skeleton className="h-20 w-full" /></CardContent></Card> : proposals.length === 0 ? <Card><CardContent className="flex flex-col items-center gap-3 p-10 text-center"><Sparkles className="h-8 w-8 text-muted-foreground" /><h2 className="font-semibold">Nenhuma proposta pronta</h2><p className="max-w-md text-sm text-muted-foreground">Use o planejamento para escolher uma oportunidade inteligente e gerar uma proposta editável.</p><Button onClick={onPlan}>Abrir planejamento</Button></CardContent></Card> : <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]"><div className="space-y-2">{proposals.map((proposal) => <button key={proposal.id} type="button" onClick={() => setSelectedId(proposal.id)} className={`w-full rounded-xl border p-4 text-left ${selected?.id === proposal.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted/30"}`}><div className="flex items-center justify-between gap-2"><span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Rev. {proposal.revision}</span><span className="rounded-full bg-muted px-2 py-1 text-[10px] font-semibold">{statusLabels[proposal.status]}</span></div><p className="mt-2 text-sm font-semibold">{proposal.title}</p><p className="mt-1 text-xs text-muted-foreground">{formatNumber(proposal.audience_total)} alunos · {formatNumber(proposal.outreach_eligible_count)} elegíveis</p></button>)}</div>{selected ? <Card><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle>{selected.title}</CardTitle><CardDescription className="mt-1">Revisão {selected.revision} · criada em {new Date(selected.created_at).toLocaleDateString("pt-BR")}</CardDescription></div><span className="rounded-full bg-muted px-3 py-1.5 text-xs font-semibold">{statusLabels[selected.status]}</span></div></CardHeader><CardContent className="space-y-5"><div className="grid gap-2 sm:grid-cols-4">{[{ label: "Público", value: selected.audience_total }, { label: "Elegíveis", value: selected.outreach_eligible_count }, { label: "Bloqueados", value: selected.blocked_count }, { label: "Ação interna", value: selected.internal_action_count }].map((item) => <div key={item.label} className="rounded-lg border bg-muted/20 p-3"><p className="text-xs text-muted-foreground">{item.label}</p><p className="mt-1 text-xl font-semibold tabular-nums">{formatNumber(item.value)}</p></div>)}</div><div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4"><p className="text-sm font-semibold text-blue-950">Snapshot protegido</p><p className="mt-1 break-all text-xs text-blue-900">Hash: {selected.audience_hash}</p><p className="mt-2 text-xs text-blue-900">O público, opt-out, preferências e intervalos foram calculados no momento da proposta.</p></div><div className="grid gap-4 md:grid-cols-2"><div><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">Objetivo</p><p className="mt-1 text-sm leading-relaxed">{selected.objective}</p></div><div><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted-foreground">Régua</p><p className="mt-1 text-sm">{selected.cadence_days.length ? `Dias ${selected.cadence_days.join(", ")}` : "Ação interna"} · {selected.recommended_channels.join(", ") || "sem canal"}</p></div></div><div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => void createProposal()} disabled={busy}><RefreshCw className="mr-2 h-4 w-4" />Recalcular snapshot</Button><Link href={`/campanhas?proposal=${encodeURIComponent(selected.id)}`} className="inline-flex h-10 items-center rounded-md border border-input bg-background px-4 text-sm font-medium hover:bg-accent">Abrir revisão completa <ChevronRight className="ml-2 h-4 w-4" /></Link></div><div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />A execução só deve acontecer após revisão, atestado e aprovação conforme a permissão da instituição.</div></CardContent></Card> : null}</div>}</div>;
}

function ExecutionPanel({ result, onPlan, onRefresh }: { result: RetentionRunResult | null; onPlan: () => void; onRefresh: () => void }) {
  const logsQuery = useQuery({ queryKey: ["retention-logs", "interventions"], queryFn: () => api.retentionLogs({ limit: 20 }) });
  const logs = logsQuery.data?.logs ?? [];
  const totals = result?.totals;
  return <div className="space-y-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm text-muted-foreground">Acompanhe dry-runs, envios e bloqueios sem misturar planejamento com operação.</p></div><div className="flex gap-2"><Button variant="outline" onClick={onRefresh}><RefreshCw className="mr-2 h-4 w-4" />Atualizar</Button><Button onClick={onPlan}><Play className="mr-2 h-4 w-4" />Nova intervenção</Button></div></div>{result ? <Card><CardHeader><CardTitle className="text-base">Última execução</CardTitle><CardDescription>{result.campaign_id ? `Campanha ${result.campaign_id}` : "Execução sem identificador"}</CardDescription></CardHeader><CardContent className="grid gap-3 sm:grid-cols-4">{[{ label: "Avaliados", value: result.students_evaluated ?? 0 }, { label: "Enviados / simulados", value: (totals?.sent ?? 0) + (totals?.dry_run ?? 0) }, { label: "Ignorados", value: totals?.skipped ?? 0 }, { label: "Falhas", value: (totals?.failed ?? 0) + (totals?.unknown ?? 0) }].map((item) => <div key={item.label} className="rounded-lg border bg-muted/20 p-4"><p className="text-xs text-muted-foreground">{item.label}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{formatNumber(item.value)}</p></div>)}</CardContent></Card> : null}<Card><CardHeader><div className="flex items-center justify-between gap-2"><div><CardTitle className="text-base">Atividade operacional recente</CardTitle><CardDescription>Os resultados também aparecem no histórico individual de cada aluno.</CardDescription></div><Link href="/retencao/logs" className="text-xs font-semibold text-primary underline underline-offset-2">Ver histórico completo</Link></div></CardHeader><CardContent>{logsQuery.isLoading ? <Skeleton className="h-32 w-full" /> : logs.length === 0 ? <div className="flex flex-col items-center gap-2 py-8 text-center"><Clock3 className="h-7 w-7 text-muted-foreground" /><p className="text-sm font-semibold">Nenhuma execução registrada</p><p className="text-xs text-muted-foreground">Depois de simular ou executar uma intervenção, os registros aparecem aqui.</p></div> : <div className="divide-y">{logs.slice(0, 8).map((log) => <div key={log.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div className="min-w-0"><p className="truncate text-sm font-medium">{log.campaign_id || "Intervenção avulsa"}</p><p className="text-xs text-muted-foreground">{log.channel || "canal não definido"} · {log.student_id ? `aluno ${log.student_id.slice(0, 8)}…` : "sem aluno"}</p></div><span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${log.status === "sent" ? "bg-emerald-50 text-emerald-800" : log.status === "failed" ? "bg-red-50 text-red-700" : "bg-muted text-muted-foreground"}`}>{log.status}</span></div>)}</div>}</CardContent></Card><div className="grid gap-3 md:grid-cols-3"><div className="rounded-xl border border-amber-200 bg-amber-50 p-4"><Pause className="h-4 w-4 text-amber-800" /><p className="mt-3 text-sm font-semibold text-amber-950">Pausar régua</p><p className="mt-1 text-xs text-amber-900">Disponível para execuções enfileiradas; intervenções já enviadas não são revertidas.</p></div><div className="rounded-xl border border-red-200 bg-red-50 p-4"><XCircle className="h-4 w-4 text-red-700" /><p className="mt-3 text-sm font-semibold text-red-950">Cancelar execução</p><p className="mt-1 text-xs text-red-900">Use o histórico para identificar a execução e registrar a decisão operacional.</p></div><div className="rounded-xl border border-blue-200 bg-blue-50 p-4"><Workflow className="h-4 w-4 text-blue-800" /><p className="mt-3 text-sm font-semibold text-blue-950">Histórico do aluno</p><p className="mt-1 text-xs text-blue-900">Cada decisão preserva campanha, canal, motivo, opt-out e outcome.</p></div></div></div>;
}

function RetencaoContent() {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("planejar");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RetentionRunResult | null>(null);

  async function run(payload: { levels: RiskLevel[]; studentIds: string[]; campaign: string; dryRun: boolean; channels: string[] }) {
    if (!payload.studentIds.length && !payload.levels.length) { toast.error("Selecione grupos, alunos ou níveis de risco."); return; }
    setRunning(true);
    try {
      const campaignId = payload.campaign.trim() || `intervencao-${new Date().toISOString().slice(0, 10)}`;
      const response = await api.retentionRun({ risk_levels: payload.studentIds.length ? undefined : payload.levels, limit: 500, campaign_id: campaignId, campaign_name: payload.campaign.trim() || undefined, dry_run: payload.dryRun, student_ids: payload.studentIds.length ? payload.studentIds : undefined, channels: payload.channels as Array<"whatsapp" | "email" | "sms"> }, crypto.randomUUID());
      setResult(response);
      setStep("executar");
      toast.success(response.message || (payload.dryRun ? "Simulação concluída." : "Intervenção executada."));
      void queryClient.invalidateQueries({ queryKey: ["retention-logs"] });
    } catch (error) { toast.error(error instanceof Error ? error.message : "Não foi possível executar a intervenção."); }
    finally { setRunning(false); }
  }

  return <><Header title="Intervenções" subtitle="Planeje, aprove e acompanhe estratégias de retenção em um só lugar." /><main className="mira-page mx-auto w-full max-w-[1440px] space-y-6 px-4 pb-12 pt-5 md:px-9 md:pt-7"><div className="rounded-xl border border-[#e4e7ec] bg-white p-4 shadow-none"><div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Centro de intervenção</p><p className="mt-1 text-sm text-muted-foreground">Do sinal operacional ao histórico do aluno, cada etapa tem seu próprio contexto e permissão.</p></div><div className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground"><Users className="h-4 w-4" /> {result ? "Última execução pronta para acompanhamento" : "Nenhuma execução nesta sessão"}</div></div><div className="mt-5 grid gap-2 md:grid-cols-3">{steps.map((item, index) => { const active = step === item.id; const complete = steps.findIndex((entry) => entry.id === step) > index; return <button key={item.id} type="button" onClick={() => setStep(item.id)} className={`relative flex items-center gap-3 rounded-xl border p-3 text-left ${active ? "border-primary bg-primary/5" : complete ? "border-emerald-200 bg-emerald-50/50" : "border-border hover:bg-muted/30"}`}><span className={`grid h-8 w-8 place-items-center rounded-full text-xs font-bold ${active ? "bg-primary text-white" : complete ? "bg-emerald-600 text-white" : "bg-muted text-muted-foreground"}`}>{complete ? <Check className="h-4 w-4" /> : index + 1}</span><span><span className="block text-sm font-semibold">{item.label}</span><span className="block text-[11px] text-muted-foreground">{item.detail}</span></span>{index < steps.length - 1 ? <ChevronRight className="absolute -right-3 hidden h-4 w-4 bg-white text-muted-foreground md:block" /> : null}</button>; })}</div></div>{step === "planejar" ? <PlanningPanel onNavigate={setStep} onRun={run} running={running} /> : null}{step === "aprovar" ? <ApprovalPanel onPlan={() => setStep("planejar")} /> : null}{step === "executar" ? <ExecutionPanel result={result} onPlan={() => setStep("planejar")} onRefresh={() => void queryClient.invalidateQueries({ queryKey: ["retention-logs", "interventions"] })} /> : null}<div className="flex items-start gap-2 rounded-xl border bg-muted/20 p-4 text-xs leading-relaxed text-muted-foreground"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />Toda execução respeita opt-out global, preferências por canal, deduplicação e intervalos anti-spam. A aprovação institucional não substitui a análise da base legal nem libera envio fora das permissões do tenant.</div></main></>;
}

export default function RetencaoPage() {
  return <Suspense fallback={<main className="p-8"><Skeleton className="h-8 w-64" /></main>}><RetencaoContent /></Suspense>;
}
