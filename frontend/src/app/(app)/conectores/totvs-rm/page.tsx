"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle, ArrowLeft, Ban, CheckCircle2, Clock3, Database,
  History, LoaderCircle, Play, RefreshCw, RotateCcw, XCircle,
} from "@/components/ui/icons";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import type { RMTotvsJob, RMTotvsJobStatus } from "@/lib/api";

const ACTIVE = ["queued", "running", "retry_wait", "cancel_requested", "publishing"];
const STATUS: Record<string, { label: string; className: string }> = {
  queued: { label: "Na fila", className: "bg-slate-100 text-slate-700" },
  running: { label: "Em execução", className: "bg-blue-50 text-blue-700" },
  retry_wait: { label: "Aguardando retry", className: "bg-amber-50 text-amber-700" },
  cancel_requested: { label: "Cancelamento solicitado", className: "bg-amber-50 text-amber-700" },
  publishing: { label: "Publicando snapshot", className: "bg-blue-50 text-blue-700" },
  cancelled: { label: "Cancelada", className: "bg-slate-100 text-slate-600" },
  succeeded: { label: "Concluída", className: "bg-emerald-50 text-emerald-700" },
  failed: { label: "Falhou", className: "bg-red-50 text-red-700" },
};
const EVENT_LABELS: Record<string, string> = {
  queued: "Adicionada à fila", started: "Worker iniciou a execução",
  lease_recovered: "Execução retomada após perda de lease",
  snapshot_attached: "Snapshot associado", retry_scheduled: "Nova tentativa agendada",
  manual_retry: "Nova tentativa solicitada manualmente",
  cancel_requested: "Cancelamento solicitado", publishing: "Início da publicação atômica", cancelled: "Execução cancelada",
  succeeded: "Execução concluída", failed: "Execução encerrada com falha",
};

function dateLabel(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function durationLabel(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}
function StatusPill({ status }: { status: string }) {
  const item = STATUS[status] || { label: status, className: "bg-slate-100 text-slate-700" };
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold ${item.className}`}>{item.label}</span>;
}
function Metric({ label, value, hint }: { label: string; value: string | number; hint: string }) {
  return <Card><CardContent className="p-4">
    <p className="text-xs font-medium text-muted-foreground">{label}</p>
    <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
    <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p>
  </CardContent></Card>;
}

export default function TotvsRmOperationsPage() {
  const client = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [coligadaFilter, setColigadaFilter] = useState("");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [coligada, setColigada] = useState("");
  const [sourceName, setSourceName] = useState("TOTVS_RM");
  const [entityName, setEntityName] = useState("EduAlunoData");
  const [pageSize, setPageSize] = useState("500");
  const [showEnqueue, setShowEnqueue] = useState(false);

  const metrics = useQuery({
    queryKey: ["totvs-rm-metrics"], queryFn: api.totvsRmMetrics, retry: false,
    refetchInterval: 10000,
  });
  const scopes = useQuery({
    queryKey: ["totvs-rm-scopes"], queryFn: api.totvsRmScopes, retry: false,
    refetchInterval: 15000,
  });
  const jobs = useQuery({
    queryKey: ["totvs-rm-jobs", statusFilter, coligadaFilter],
    queryFn: () => api.totvsRmJobs({
      status: statusFilter || undefined,
      coligada_id: coligadaFilter.trim() || undefined,
      limit: 50, offset: 0,
    }),
    retry: false,
    refetchInterval: (query) => query.state.data?.jobs?.some((job) => ACTIVE.includes(job.status)) ? 3000 : 15000,
  });
  const detail = useQuery({
    queryKey: ["totvs-rm-job", selectedJobId],
    queryFn: () => api.totvsRmJob(selectedJobId!),
    enabled: Boolean(selectedJobId), retry: false, refetchInterval: (query) =>
      query.state.data && ACTIVE.includes(query.state.data.status) ? 2500 : false,
  });

  const enqueue = useMutation({
    mutationFn: () => api.enqueueTotvsRmSync({
      coligada_id: coligada.trim(), source_name: sourceName.trim(),
      entity_name: entityName.trim(), schema_version: "v1",
      page_size: Number(pageSize), max_attempts: 5,
    }),
    onSuccess: (result) => {
      toast.success("Snapshot adicionado à fila");
      setShowEnqueue(false);
      setColigada("");
      setSelectedJobId(result.job_id);
      client.invalidateQueries({ queryKey: ["totvs-rm-jobs"] });
      client.invalidateQueries({ queryKey: ["totvs-rm-scopes"] });
      client.invalidateQueries({ queryKey: ["totvs-rm-metrics"] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Não foi possível enfileirar a sincronização"),
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelTotvsRmJob(id),
    onSuccess: (result) => {
      toast.success(result.status === "cancelled" ? "Execução cancelada" : "Solicitação de cancelamento registrada");
      client.invalidateQueries({ queryKey: ["totvs-rm-job", selectedJobId] });
      client.invalidateQueries({ queryKey: ["totvs-rm-jobs"] });
      client.invalidateQueries({ queryKey: ["totvs-rm-metrics"] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Não foi possível cancelar"),
  });
  const retry = useMutation({
    mutationFn: (id: string) => api.retryTotvsRmJob(id),
    onSuccess: () => {
      toast.success("Nova tentativa adicionada à fila");
      client.invalidateQueries({ queryKey: ["totvs-rm-job", selectedJobId] });
      client.invalidateQueries({ queryKey: ["totvs-rm-jobs"] });
      client.invalidateQueries({ queryKey: ["totvs-rm-metrics"] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Não foi possível solicitar nova tentativa"),
  });

  const counts = metrics.data?.jobs_by_status || {};
  const activeCount = metrics.data?.active_jobs ?? 0;
  const queueDepth = metrics.data?.queue_depth ?? 0;
  const jobList = jobs.data?.jobs || [];
  const selectedJob = detail.data;
  const canCancel = Boolean(selectedJob && ["queued", "retry_wait", "running"].includes(selectedJob.status));
  const canRetry = selectedJob?.status === "failed";
  const hasErrors = metrics.isError || jobs.isError || scopes.isError;

  const scopeSummary = useMemo(() => scopes.data?.scopes ?? [], [scopes.data?.scopes]);

  return <>
    <Header title="Operações TOTVS RM" subtitle="Acompanhe filas, execuções, eventos e snapshots por coligada." />
    <main className="mira-page mx-auto w-full max-w-6xl space-y-6 px-4 pb-12 pt-5 md:px-9 md:pt-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/conectores" className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-3.5 w-3.5" /> Dados e integrações
          </Link>
          <h1 className="mt-2 text-xl font-semibold tracking-tight">Central de operações</h1>
          <p className="mt-1 text-sm text-muted-foreground">Visibilidade operacional da fila de sincronização TOTVS RM.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => {
            client.invalidateQueries({ queryKey: ["totvs-rm-metrics"] });
            client.invalidateQueries({ queryKey: ["totvs-rm-jobs"] });
            client.invalidateQueries({ queryKey: ["totvs-rm-scopes"] });
          }}><RefreshCw className="mr-2 h-4 w-4" /> Atualizar</Button>
          <Button size="sm" onClick={() => setShowEnqueue((value) => !value)}>
            <Play className="mr-2 h-4 w-4" /> Enfileirar snapshot
          </Button>
        </div>
      </div>

      <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
          <div className="space-y-1">
            <p className="text-sm font-semibold text-amber-950">A fila está disponível; o worker de produção ainda não foi configurado.</p>
            <p className="text-xs leading-relaxed text-amber-900">
              Enfileirar cria uma execução persistida. Ela só será processada quando um worker autorizado e um executor RM estiverem configurados. Esta tela não testa conexão, não consulta o RM e não indica que os dados foram sincronizados.
            </p>
          </div>
        </div>
      </div>

      {showEnqueue && <Card>
        <CardHeader>
          <CardTitle className="text-base">Nova sincronização</CardTitle>
          <CardDescription>Cria um job de snapshot completo. Não envia credenciais nem dados de alunos.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="space-y-1.5 text-xs font-medium">Código da coligada
              <input value={coligada} onChange={(e) => setColigada(e.target.value)} maxLength={80} placeholder="Ex.: 1" className="mt-1.5 h-10 w-full rounded-lg border border-input bg-background px-3 text-sm font-normal outline-none focus:ring-2 focus:ring-primary/20" />
            </label>
            <label className="space-y-1.5 text-xs font-medium">Origem
              <input value={sourceName} onChange={(e) => setSourceName(e.target.value)} maxLength={120} className="mt-1.5 h-10 w-full rounded-lg border border-input bg-background px-3 text-sm font-normal outline-none focus:ring-2 focus:ring-primary/20" />
            </label>
            <label className="space-y-1.5 text-xs font-medium">DataServer / entidade
              <input value={entityName} onChange={(e) => setEntityName(e.target.value)} maxLength={120} className="mt-1.5 h-10 w-full rounded-lg border border-input bg-background px-3 text-sm font-normal outline-none focus:ring-2 focus:ring-primary/20" />
            </label>
            <label className="space-y-1.5 text-xs font-medium">Registros por página
              <input type="number" min="1" max="1000" value={pageSize} onChange={(e) => setPageSize(e.target.value)} className="mt-1.5 h-10 w-full rounded-lg border border-input bg-background px-3 text-sm font-normal outline-none focus:ring-2 focus:ring-primary/20" />
            </label>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setShowEnqueue(false)}>Fechar</Button>
            <Button size="sm" disabled={enqueue.isPending || !coligada.trim() || !sourceName.trim() || !entityName.trim() || !Number.isInteger(Number(pageSize)) || Number(pageSize) < 1 || Number(pageSize) > 1000}
              onClick={() => enqueue.mutate()}>
              {enqueue.isPending ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              Confirmar e enfileirar
            </Button>
          </div>
        </CardContent>
      </Card>}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Jobs na fila" value={metrics.isLoading ? "—" : queueDepth} hint={`${counts.queued ?? 0} aguardando · ${counts.retry_wait ?? 0} em retry`} />
        <Metric label="Jobs ativos" value={metrics.isLoading ? "—" : activeCount} hint={`${counts.running ?? 0} em execução · ${counts.cancel_requested ?? 0} cancelando`} />
        <Metric label="Concluídos" value={metrics.isLoading ? "—" : counts.succeeded ?? 0} hint="Snapshots finalizados com sucesso" />
        <Metric label="Falhas" value={metrics.isLoading ? "—" : counts.failed ?? 0} hint={`Duração média: ${durationLabel(metrics.data?.average_duration_seconds)}`} />
      </section>

      {hasErrors && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">
        Não foi possível carregar parte dos dados operacionais. Verifique sua permissão de coordenador e tente atualizar.
      </div>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="min-w-0">
          <CardHeader className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div><CardTitle className="text-base">Execuções recentes</CardTitle><CardDescription>{jobs.data?.total ?? 0} jobs encontrados · exibindo até 50</CardDescription></div>
              <History className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="grid gap-2 sm:grid-cols-[1fr_180px]">
              <input value={coligadaFilter} onChange={(e) => setColigadaFilter(e.target.value)} placeholder="Filtrar por coligada" className="h-9 rounded-lg border border-input bg-background px-3 text-xs outline-none focus:ring-2 focus:ring-primary/20" />
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-9 rounded-lg border border-input bg-background px-3 text-xs outline-none focus:ring-2 focus:ring-primary/20">
                <option value="">Todos os status</option>
                {Object.entries(STATUS).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}
              </select>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {jobs.isLoading && <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground"><LoaderCircle className="h-4 w-4 animate-spin" /> Carregando execuções…</div>}
            {!jobs.isLoading && jobList.length === 0 && <EmptyState icon={<Database className="h-5 w-5" />} title="Nenhuma execução encontrada" description="Quando um snapshot for enfileirado, ele aparecerá aqui com seu histórico de eventos." />}
            {jobList.map((job) => <JobRow key={job.id} job={job} selected={selectedJobId === job.id} onSelect={() => setSelectedJobId(job.id)} />)}
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="text-base">Detalhes da execução</CardTitle>
            <CardDescription>{selectedJob ? `Coligada ${selectedJob.coligada_id}` : "Selecione um job para consultar os eventos."}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedJobId && <EmptyState icon={<Clock3 className="h-5 w-5" />} title="Nenhum job selecionado" description="Os detalhes e a linha do tempo aparecem nesta área." />}
            {selectedJobId && detail.isLoading && <div className="flex items-center gap-2 py-6 text-xs text-muted-foreground"><LoaderCircle className="h-4 w-4 animate-spin" /> Carregando detalhes…</div>}
            {selectedJob && <>
              <div className="flex items-center justify-between gap-2"><span className="text-xs text-muted-foreground">Status atual</span><StatusPill status={selectedJob.status} /></div>
              <div className="space-y-1 text-xs">
                <p className="font-semibold">{selectedJob.source_name} · {selectedJob.entity_name}</p>
                <p className="text-muted-foreground">Coligada {selectedJob.coligada_id} · Schema {selectedJob.schema_version}</p>
                <p className="break-all font-mono text-[10px] text-muted-foreground">{selectedJob.id}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/40 p-3 text-xs">
                <div><p className="text-muted-foreground">Tentativas</p><p className="mt-1 font-semibold tabular-nums">{selectedJob.attempts} / {selectedJob.max_attempts}</p></div>
                <div><p className="text-muted-foreground">Página</p><p className="mt-1 font-semibold tabular-nums">{selectedJob.request?.page_size ?? "—"} registros</p></div>
                <div><p className="text-muted-foreground">Criada</p><p className="mt-1 font-medium">{dateLabel(selectedJob.created_at)}</p></div>
                <div><p className="text-muted-foreground">Finalizada</p><p className="mt-1 font-medium">{dateLabel(selectedJob.finished_at)}</p></div>
              </div>
              {selectedJob.snapshot_run_id && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800"><CheckCircle2 className="mr-1.5 inline h-4 w-4" /> Snapshot publicado: <span className="break-all font-mono">{selectedJob.snapshot_run_id}</span></div>}
              {selectedJob.error_code && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800"><p className="font-semibold">{selectedJob.error_code}</p><p className="mt-1">{selectedJob.error_message || "A execução terminou com falha."}</p></div>}
              <div className="flex flex-wrap gap-2">
                {canCancel && <Button size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate(selectedJob.id)}><Ban className="mr-1.5 h-3.5 w-3.5" /> Cancelar</Button>}
                {canRetry && <Button size="sm" disabled={retry.isPending} onClick={() => retry.mutate(selectedJob.id)}><RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Tentar novamente</Button>}
              </div>
              <div className="border-t border-border pt-3">
                <p className="mb-3 text-xs font-semibold">Linha do tempo</p>
                {detail.data?.events?.length ? <ol className="space-y-3">
                  {detail.data.events.map((event, index) => <li key={event.created_at + event.event_type + index} className="relative pl-4">
                    <span className={`absolute left-0 top-1.5 h-2 w-2 rounded-full ${event.severity === "error" ? "bg-red-500" : event.severity === "warning" ? "bg-amber-500" : "bg-blue-500"}`} />
                    <p className="text-[11px] font-medium">{EVENT_LABELS[event.event_type] || event.event_type}</p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">{dateLabel(event.created_at)}</p>
                    {event.details?.code != null && <p className="mt-1 text-[10px] text-muted-foreground">Código: {String(event.details.code)}</p>}
                  </li>)}
                </ol> : <p className="text-[11px] text-muted-foreground">Nenhum evento disponível.</p>}
              </div>
            </>}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Escopos cadastrados</CardTitle><CardDescription>Combinação de tenant, coligada, origem, entidade e versão de schema.</CardDescription></CardHeader>
        <CardContent>
          {scopes.isLoading ? <p className="text-xs text-muted-foreground">Carregando escopos…</p> : scopeSummary.length === 0 ? <p className="text-xs text-muted-foreground">Nenhum escopo criado ainda.</p> : <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-left text-xs">
              <thead><tr className="border-b border-border text-muted-foreground"><th className="pb-2 pr-3 font-medium">Coligada</th><th className="pb-2 pr-3 font-medium">Origem</th><th className="pb-2 pr-3 font-medium">Entidade</th><th className="pb-2 pr-3 font-medium">Schema</th><th className="pb-2 pr-3 font-medium">Snapshot atual</th><th className="pb-2 font-medium">Atualizado</th></tr></thead>
              <tbody>{scopeSummary.map((scope) => <tr key={scope.id} className="border-b border-border/70 last:border-0"><td className="py-2.5 pr-3 font-medium">{scope.coligada_id}</td><td className="py-2.5 pr-3">{scope.source_name}</td><td className="py-2.5 pr-3">{scope.entity_name}</td><td className="py-2.5 pr-3">{scope.schema_version}</td><td className="py-2.5 pr-3 font-mono text-[10px]">{scope.current_snapshot_run_id ? scope.current_snapshot_run_id.slice(0, 12) + "…" : "—"}</td><td className="py-2.5">{dateLabel(scope.updated_at)}</td></tr>)}</tbody>
            </table>
          </div>}
        </CardContent>
      </Card>
    </main>
  </>;
}

function JobRow({ job, selected, onSelect }: { job: RMTotvsJob; selected: boolean; onSelect: () => void }) {
  return <button type="button" onClick={onSelect} className={`w-full rounded-xl border p-3 text-left transition hover:border-primary/40 hover:bg-muted/20 ${selected ? "border-primary/50 bg-primary/[0.04]" : "border-border"}`}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-xs font-semibold">{job.entity_name} <span className="font-normal text-muted-foreground">· Coligada {job.coligada_id}</span></span>
      <StatusPill status={job.status as RMTotvsJobStatus} />
    </div>
    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted-foreground">
      <span>{dateLabel(job.created_at)}</span>
      <span>{job.attempts}/{job.max_attempts} tentativas</span>
    </div>
    {job.error_code && <p className="mt-2 flex items-center gap-1 text-[10px] text-red-600"><XCircle className="h-3 w-3" /> {job.error_code}</p>}
  </button>;
}
