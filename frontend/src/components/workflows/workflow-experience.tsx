"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity, AlertCircle, ArrowRight, Clock3, FileClock, History,
  LockKeyhole, RefreshCw, Search, Settings2, ShieldCheck, Workflow,
} from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { getVisibleNavigation, hasNavigationPermission } from "@/components/layout/navigation";
import { api } from "@/lib/api";
import { dispatchApi, type ComposioImportHistory, type DispatchCampaign } from "@/lib/dispatch-api";
import type { RetentionCampaignProposal } from "@/types/api";
import { WorkflowCanvas } from "./workflow-canvas";
import { WorkflowInspector } from "./workflow-inspector";
import { blocksForWorkflow, statusLabel, workflowRecords, type WorkflowRecord } from "./workflow-model";

type Tab = "editor" | "history" | "permissions";
type Filter = "all" | "proposal" | "dispatch";
type DispatchItem = {
  id: string; status: string; subject_type: string; subject_ref: string;
  attempt?: number; updated_at?: string; last_error?: string;
};

function dateTime(value: string | null | undefined): string {
  if (!value) return "Não registrado";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Não registrado" : parsed.toLocaleString("pt-BR");
}

function Status({ value, kind }: { value: string; kind?: WorkflowRecord["kind"] }) {
  const state = kind ? statusLabel(value, kind) : value;
  return <span className="inline-flex max-w-full items-center rounded-md border border-[var(--color-legacy-e9eaed)] bg-[var(--color-legacy-f7f8fa)] px-2 py-1 text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-59616f)]">{state}</span>;
}

const grants = [
  { permission: "campaigns.view", label: "Visualizar" },
  { permission: "campaigns.edit", label: "Editar" },
  { permission: "campaigns.approve", label: "Aprovar" },
  { permission: "campaigns.execute", label: "Executar (fora deste editor)" },
] as const;

function AccessMatrix({ can }: { can: (permission: string) => boolean }) {
  return (
    <section aria-label="Permissões de workflows" className="overflow-hidden rounded-xl border border-[var(--color-legacy-e6e9ed)] bg-white">
      <div className="border-b border-[var(--color-legacy-edf0f2)] px-5 py-4">
        <h2 className="text-sm font-semibold text-[var(--color-legacy-1d2229)]">Quem pode fazer o quê</h2>
        <p className="mt-1 text-xs leading-5 text-[var(--color-legacy-737b87)]">Permissões efetivas deste workspace. Os serviços aplicam controle próprio, MFA e segregação de funções.</p>
      </div>
      <div className="divide-y divide-[var(--color-legacy-f0f1f3)]">
        {grants.map(item => <div key={item.permission} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
          <div><p className="text-xs font-medium text-[var(--color-legacy-343942)]">{item.label}</p>
            <p className="mt-0.5 font-mono text-[length:var(--type-overline)] text-[var(--color-legacy-868f99)]">{item.permission}</p></div>
          <span className={"rounded-md px-2 py-1 text-[length:var(--type-caption)] font-semibold " +
            (can(item.permission) ? "bg-[var(--color-legacy-ecf8f0)] text-[var(--color-legacy-24744a)]" : "bg-[var(--color-legacy-f5f6f8)] text-[var(--color-legacy-767c86)]")}>
            {can(item.permission) ? "Concedida" : "Sem permissão"}
          </span>
        </div>)}
      </div>
      <p className="border-t border-[var(--color-legacy-edf0f2)] bg-[var(--color-legacy-fafbfc)] px-5 py-4 text-[length:var(--type-caption)] leading-5 text-[var(--color-legacy-6c7480)]">
        Uma permissão exibida não contorna validação de tenant, estado, aprovação, usuário humano ou MFA/AAL2. Ações de execução não estão disponíveis no canvas.
      </p>
    </section>
  );
}

function ImportHistory({
  items, loading, error, retry,
}: {
  items: ComposioImportHistory[]; loading: boolean; error: string | null; retry: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = items.find(item => item.id === selectedId);
  return (
    <section className="overflow-hidden rounded-xl border border-[var(--color-legacy-e6e9ed)] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-legacy-eef0f2)] px-5 py-4">
        <div><h3 className="text-xs font-semibold text-[var(--color-legacy-282e38)]">Execuções reais · Importações Composio</h3>
          <p className="mt-1 text-[length:var(--type-caption)] leading-5 text-[var(--color-legacy-7d8590)]">Histórico do workspace, separado deste workflow. Não representa envio ou execução da proposta selecionada.</p></div>
        <button type="button" onClick={retry} className="inline-flex items-center gap-1 text-xs text-[var(--color-legacy-2563eb)] hover:underline"><RefreshCw className="h-3.5 w-3.5" /> Atualizar</button>
      </div>
      {loading && <p role="status" className="p-5 text-xs text-[var(--color-legacy-767e88)]">Carregando execuções registradas...</p>}
      {error && <div role="alert" className="p-5 text-xs text-[var(--color-legacy-af2e2e)]">Falha ao consultar execuções: {error}</div>}
      {!loading && !error && items.length === 0 && <p className="p-5 text-xs text-[var(--color-legacy-767e88)]">Nenhuma execução de importação registrada para este workspace.</p>}
      {items.length > 0 && <div className="divide-y divide-[var(--color-legacy-f0f2f3)]">
        {items.map(run => (
          <button key={run.id} type="button" aria-pressed={selectedId === run.id} onClick={() => setSelectedId(run.id)}
            className={"flex w-full flex-wrap items-center justify-between gap-3 px-5 py-3 text-left hover:bg-[var(--color-legacy-f8f9fb)] " + (selectedId === run.id ? "bg-[var(--color-legacy-f3f6fc)]" : "")}>
            <div className="min-w-0">
              <p className="truncate font-mono text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-303844)]">{run.id}</p>
              <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-838b97)]">{run.toolkit_slug} · {run.tool_slug} · {dateTime(run.started_at)}</p>
            </div><Status value={run.status} />
          </button>
        ))}
      </div>}
      {selected && <div className="space-y-2 border-t border-[var(--color-legacy-e4eaf4)] bg-[var(--color-legacy-fbfcfe)] p-5 text-xs text-[var(--color-legacy-3d4651)]">
        <h4 className="font-semibold">Detalhe da execução {selected.id}</h4>
        <p>Origem: {selected.toolkit_slug} / {selected.tool_slug}</p>
        <p>Estado registrado: {selected.status}</p>
        <p>Início: {dateTime(selected.started_at)} · Término: {dateTime(selected.finished_at)}</p>
        <p>Linhas observadas: {selected.rows_total} · Criadas: {selected.rows_created} · Atualizadas: {selected.rows_updated}</p>
        <p>Erro registrado: {selected.error_code || "Nenhum código de erro registrado"}</p>
        <p className="text-[length:var(--type-caption)] text-[var(--color-legacy-838b97)]">Etapas internas não são expostas por este contrato. Não há retry de execução nesta tela.</p>
      </div>}
    </section>
  );
}

function RecordHistory({
  record, linked, events, auditLoading, auditError, items, detailsLoading, detailsError, retry,
}: {
  record: WorkflowRecord;
  linked: DispatchCampaign[];
  events: Array<{ id: string; event_type: string; actor_user_id?: string | null; revision: number; created_at: string }>;
  auditLoading: boolean;
  auditError: string | null;
  items: DispatchItem[];
  detailsLoading: boolean;
  detailsError: string | null;
  retry: () => void;
}) {
  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-[var(--color-legacy-e6e9ed)] bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-legacy-eef0f2)] px-5 py-4">
          <div><h2 className="text-sm font-semibold text-[var(--color-legacy-272d35)]">{record.kind === "proposal" ? "Auditoria da proposta" : "Itens operacionais do disparador"}</h2>
            <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-7d8590)]">{record.kind === "proposal" ? "Eventos versionados registrados no serviço de permanência" : "Até 100 itens retornados pelo serviço; não é um registro de run de workflow gráfico"}</p></div>
          <button type="button" onClick={retry} className="flex items-center gap-1 text-xs text-[var(--color-legacy-2563eb)] hover:underline"><RefreshCw className="h-3.5 w-3.5" /> Reconsultar</button>
        </div>
        {(auditLoading || detailsLoading) && <p role="status" className="p-5 text-xs text-[var(--color-legacy-757e89)]">Consultando evidências...</p>}
        {(auditError || detailsError) && <p role="alert" className="p-5 text-xs text-[var(--color-legacy-b3261e)]">{auditError || detailsError}</p>}
        {record.kind === "proposal" ? (
          <div className="divide-y divide-[var(--color-legacy-eef0f2)]">
            {linked.length > 0 && <div className="bg-[var(--color-legacy-f8fafd)] p-5">
              <h3 className="mb-2 text-xs font-semibold text-[var(--color-legacy-38465c)]">Encaminhamentos registrados para este ID</h3>
              {linked.map(c => <Link key={c.id} href={"/workflows/dispatch/" + encodeURIComponent(c.id)}
                className="flex items-center justify-between gap-2 py-1.5 text-xs text-[var(--color-legacy-2563eb)] hover:underline">
                {c.name} <Status value={c.status} kind="dispatch" /></Link>)}
            </div>}
            {events.length === 0 && !auditLoading && !auditError && <p className="p-5 text-xs text-[var(--color-legacy-7e8690)]">Nenhum evento auditável disponível. Aprovação não equivale a execução.</p>}
            {events.map(event => <div key={event.id} className="flex gap-3 px-5 py-3.5">
              <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[var(--color-legacy-2563eb)]" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-[var(--color-legacy-323841)]">{event.event_type}</p>
                <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-7a838f)]">Revisão {event.revision} · {dateTime(event.created_at)} · Responsável {event.actor_user_id ?? "Não informado"}</p>
                <p className="mt-1 font-mono text-[length:var(--type-overline)] text-[var(--color-legacy-969da6)]">Evento {event.id}</p>
              </div>
            </div>)}
          </div>
        ) : (
          <div className="divide-y divide-[var(--color-legacy-eef0f2)]">
            {items.length === 0 && !detailsLoading && !detailsError && <p className="p-5 text-xs text-[var(--color-legacy-7e8690)]">Nenhum item operacional retornado pelo dispatch.</p>}
            {items.map(item => <div key={item.id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-3.5">
              <div className="min-w-0"><p className="break-all font-mono text-[length:var(--type-caption)] text-[var(--color-legacy-303640)]">Item {item.id}</p>
                <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-818994)]">{item.subject_type} · atualização {dateTime(item.updated_at)} · tentativas {item.attempt ?? "não informado"}</p>
                {item.last_error && <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-a22c2c)]">Erro: {item.last_error}</p>}
              </div><Status value={item.status} />
            </div>)}
          </div>
        )}
      </section>
      <div className="rounded-lg border border-[var(--color-legacy-e8e9ed)] bg-[var(--color-legacy-fafbfc)] p-4 text-[length:var(--type-caption)] leading-5 text-[var(--color-legacy-737b86)]">
        Não existem registros de execução da definição gráfica nesta Wave. Somente auditoria real e registros dos serviços são exibidos. Reconsultar dados é seguro; repetir envios não é uma ação disponível.
      </div>
    </div>
  );
}

export function WorkflowExperience({ selectedKind, selectedId }: {
  selectedKind?: string; selectedId?: string;
}) {
  const [tab, setTab] = useState<Tab>("editor");
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [selectedNode, setSelectedNode] = useState(selectedKind === "dispatch" ? "created" : "proposal");

  const me = useQuery({ queryKey: ["org-me"], queryFn: () => api.me(), retry: false, staleTime: 60_000 });
  const allowed = Boolean(me.data && getVisibleNavigation(me.data).some(g => g.items.some(item => item.href === "/workflows")));
  const coordinator = ["coordinator", "admin"].includes(me.data?.role ?? "");
  const can = (permission: string) => hasNavigationPermission(me.data, permission);
  const proposals = useQuery({
    queryKey: ["workflow-proposals", me.data?.tenant_id],
    queryFn: () => api.retentionCampaignProposals(),
    enabled: allowed && coordinator,
    retry: false,
  });
  const dispatch = useQuery({
    queryKey: ["workflow-dispatch", me.data?.tenant_id],
    queryFn: () => dispatchApi.campaigns(),
    enabled: allowed,
    retry: false,
  });
  const imports = useQuery({
    queryKey: ["workflow-composio-imports", me.data?.tenant_id],
    queryFn: () => dispatchApi.composioImportHistory(),
    enabled: allowed,
    retry: false,
  });

  const records = useMemo(
    () => workflowRecords(proposals.data?.proposals ?? [], dispatch.data?.items ?? []),
    [proposals.data?.proposals, dispatch.data?.items],
  );
  const selected = records.find(row => row.kind === selectedKind && row.id === selectedId);
  const linked = useMemo(() => selected?.kind === "proposal"
    ? (dispatch.data?.items ?? []).filter(row => row.origin_proposal_id === selected.id) : [],
    [dispatch.data?.items, selected],
  );
  const nodes = selected ? blocksForWorkflow(selected, linked) : [];
  const node = nodes.find(item => item.id === selectedNode) ?? nodes[0];

  const audit = useQuery({
    queryKey: ["workflow-proposal-audit", me.data?.tenant_id, selected?.id],
    queryFn: () => api.retentionCampaignProposalAudit(selected?.id ?? ""),
    enabled: allowed && coordinator && selected?.kind === "proposal",
    retry: false,
  });
  const detail = useQuery({
    queryKey: ["workflow-dispatch-detail", me.data?.tenant_id, selected?.id],
    queryFn: () => dispatchApi.detail(selected?.id ?? ""),
    enabled: allowed && selected?.kind === "dispatch",
    retry: false,
  });
  const retry = () => {
    if (selected?.kind === "proposal") void audit.refetch();
    if (selected?.kind === "dispatch") void detail.refetch();
  };
  const loading = me.isLoading || (allowed && (dispatch.isLoading || (coordinator && proposals.isLoading)));
  const dataError = proposals.error ?? dispatch.error;
  const filtered = records.filter(row =>
    (filter === "all" || row.kind === filter) &&
    (row.title + " " + row.id + " " + row.status).toLocaleLowerCase("pt-BR").includes(search.toLocaleLowerCase("pt-BR")),
  );

  return (
    <div className="min-h-dvh bg-[var(--color-canvas)]">
      <Header title={selected ? selected.title : "Workflows"} breadcrumbs={["Operação", "Workflows"]} subtitle="Processos existentes, com evidências e permissões" />
      <main className="mx-auto w-full max-w-[1680px] space-y-5 px-4 pb-14 pt-6 sm:px-6 xl:px-8">
        {me.isLoading && <p role="status" className="rounded-xl border bg-white p-6 text-sm text-[var(--color-legacy-707783)]">Verificando o acesso ao workspace...</p>}
        {me.isError && <p role="alert" className="rounded-xl border bg-white p-6 text-sm text-[var(--color-legacy-b3261e)]">Não foi possível verificar suas permissões.</p>}
        {!me.isLoading && !me.isError && !allowed && <section role="alert" className="rounded-xl border bg-white p-6">
          <div className="flex items-center gap-2"><LockKeyhole className="h-4 w-4 text-[var(--color-legacy-747b86)]" /><h2 className="text-sm font-semibold">Acesso indisponível</h2></div>
          <p className="mt-2 text-xs text-[var(--color-legacy-747b86)]">É necessário acesso a campanhas e ao módulo de operação do workspace.</p>
        </section>}
        {allowed && <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-[var(--color-legacy-7c8490)]">
              <Link href="/workflows" className="font-medium text-[var(--color-legacy-2563eb)] hover:underline">Todos os workflows</Link>
              {selected && <><ArrowRight className="h-3 w-3" /><span className="max-w-[250px] truncate text-[var(--color-legacy-343b45)]">{selected.title}</span></>}
            </div>
            <span className="inline-flex items-center gap-2 rounded-md border border-[var(--color-legacy-e7e9ed)] bg-white px-3 py-1.5 text-[length:var(--type-caption)] text-[var(--color-legacy-717b87)]">
              <ShieldCheck className="h-3.5 w-3.5" /> Nenhuma execução automática
            </span>
          </div>
          {loading && <p role="status" className="rounded-xl border bg-white p-6 text-xs text-[var(--color-legacy-717a86)]">Carregando operações reais...</p>}
          {dataError && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--color-legacy-f4d1cf)] bg-white p-5">
            <span className="text-xs text-[var(--color-legacy-ae3028)]">Erro ao consultar operações: {dataError instanceof Error ? dataError.message : "Falha não identificada"}</span>
            <button type="button" onClick={() => { void proposals.refetch(); void dispatch.refetch(); }} className="text-xs font-medium text-[var(--color-legacy-2563eb)]">Tentar novamente</button>
          </div>}
          {!selectedId ? <>
            <section className="rounded-xl border border-[var(--color-legacy-e7e9ed)] bg-white px-5 py-5 sm:px-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-[length:var(--type-overline)] font-semibold uppercase tracking-[0.12em] text-[var(--color-legacy-8a919e)]">Workspace · Operação</p>
                  <h2 className="mt-1 text-[length:var(--type-size-21)] font-semibold tracking-tight text-[var(--color-legacy-181b20)]">Processos e jornadas</h2>
                  <p className="mt-1 text-xs leading-5 text-[var(--color-legacy-777f8b)]">Propostas de permanência e operações de disparo persistidas na MIRA. Nenhum workflow gráfico novo é criado por esta interface.</p>
                </div>
                <span className="rounded-lg bg-[var(--color-legacy-f4f7fe)] px-3 py-2 text-xs font-medium text-[var(--color-legacy-245bbb)]">{records.length} registro(s)</span>
              </div>
              <div className="mt-5 flex flex-wrap items-center gap-2">
                {([{ id: "all", name: "Todos" }, { id: "proposal", name: "Permanência" }, { id: "dispatch", name: "Disparos" }] as const).map(option =>
                  <button key={option.id} type="button" aria-pressed={filter === option.id} onClick={() => setFilter(option.id)}
                    className={"rounded-md px-3 py-1.5 text-xs font-medium transition-colors " + (filter === option.id ? "bg-[var(--color-legacy-20242b)] text-white" : "border border-[var(--color-legacy-e3e6ea)] text-[var(--color-legacy-707782)] hover:bg-[var(--color-panel)]")}>
                    {option.name}
                  </button>)}
                <label className="ml-auto flex min-w-[160px] items-center gap-2 rounded-md border border-[var(--color-legacy-e4e7ea)] px-3 py-1.5 text-xs text-[var(--color-legacy-8a9199)]">
                  <Search className="h-3.5 w-3.5" aria-hidden="true" />
                  <span className="sr-only">Buscar processos</span>
                  <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Buscar workflow"
                    className="min-w-0 flex-1 bg-transparent text-[var(--color-legacy-303740)] outline-none" />
                </label>
              </div>
            </section>
            <section aria-label="Índice de workflows" className="overflow-hidden rounded-xl border border-[var(--color-legacy-e6e9ed)] bg-white">
              <div className="hidden grid-cols-[minmax(0,1fr)_140px_150px_165px] gap-3 border-b border-[var(--color-legacy-eff0f2)] bg-[var(--color-legacy-fafbfc)] px-5 py-3 text-[length:var(--type-caption)] font-semibold text-[var(--color-legacy-848b96)] md:grid">
                <span>Processo</span><span>Tipo</span><span>Estado</span><span>Última referência</span>
              </div>
              {filtered.map(row => <Link key={row.kind + row.id} href={"/workflows/" + row.kind + "/" + encodeURIComponent(row.id)}
                className="grid gap-2 border-b border-[var(--color-legacy-f0f1f3)] px-5 py-4 transition-colors last:border-0 hover:bg-[var(--color-legacy-fafbfc)] md:grid-cols-[minmax(0,1fr)_140px_150px_165px] md:items-center md:gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[var(--color-legacy-e7e9ed)] bg-[var(--color-legacy-f7f9fb)]"><Workflow className="h-4 w-4 text-[var(--color-legacy-5e6a7b)]" /></span>
                  <div className="min-w-0">
                    <p className="truncate text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-242933)]">{row.title}</p>
                    <p className="mt-1 truncate font-mono text-[length:var(--type-overline)] text-[var(--color-legacy-9a9faa)]">{row.id}</p>
                  </div>
                </div>
                <span className="text-xs text-[var(--color-legacy-747e89)]">{row.kind === "proposal" ? "Permanência" : "Disparador"}</span>
                <span><Status value={row.status} kind={row.kind} /></span>
                <span className="text-[length:var(--type-caption)] text-[var(--color-legacy-818993)]">{dateTime(row.updatedAt)}</span>
              </Link>)}
              {!loading && !dataError && filtered.length === 0 && <div className="p-8 text-center">
                <Workflow className="mx-auto mb-3 h-6 w-6 text-[var(--color-legacy-a0a8b2)]" />
                <p className="text-sm font-medium text-[var(--color-legacy-39404a)]">Nenhum processo encontrado</p>
                <p className="mt-1 text-xs text-[var(--color-legacy-828b96)]">A lista mostra somente registros que seu workspace permite consultar.</p>
              </div>}
            </section>
            <ImportHistory items={imports.data?.items ?? []} loading={imports.isLoading}
              error={imports.error instanceof Error ? imports.error.message : null} retry={() => { void imports.refetch(); }} />
          </> : !selected ? (!loading && !dataError && <section role="alert" className="rounded-xl border bg-white p-6 text-sm text-[var(--color-legacy-747b86)]">
            Processo não encontrado ou não acessível neste workspace. <Link href="/workflows" className="text-[var(--color-legacy-2563eb)] underline">Voltar à lista</Link>
          </section>) : <>
            <section className="rounded-xl border border-[var(--color-legacy-e7e9ed)] bg-white px-5 py-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-[length:var(--type-overline)] font-semibold uppercase tracking-[0.11em] text-[var(--color-legacy-87909d)]">{selected.kind === "proposal" ? "Proposta de permanência" : "Campanha de disparo"}</p>
                  <h2 className="mt-1 text-xl font-semibold tracking-tight text-[var(--color-legacy-161b22)]">{selected.title}</h2>
                  <p className="mt-1 break-all font-mono text-[length:var(--type-caption)] text-[var(--color-legacy-949ca8)]">{selected.id}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Status value={selected.status} kind={selected.kind} />
                  <span className="rounded-md border border-[var(--color-legacy-e8eaf0)] bg-[var(--color-source-f9fafb)] px-2 py-1 text-[length:var(--type-caption)] text-[var(--color-legacy-7e8691)]">
                    {selected.kind === "proposal" ? "Versão " + selected.source.revision : "Estado operacional"}
                  </span>
                </div>
              </div>
              <p className="mt-3 text-[length:var(--type-caption)] text-[var(--color-legacy-79828e)]">As etapas abaixo representam registros de origem. Este editor não cria uma definição executável.</p>
              <div role="tablist" aria-label="Visões do workflow" className="mt-4 flex gap-5 overflow-x-auto border-b border-[var(--color-legacy-edeff1)]">
                {([
                  { id: "editor", title: "Editor", icon: Workflow },
                  { id: "history", title: "Histórico e execuções", icon: History },
                  { id: "permissions", title: "Permissões", icon: ShieldCheck },
                ] as const).map(item => <button type="button" key={item.id} role="tab" aria-selected={tab === item.id} onClick={() => setTab(item.id)}
                  className={"flex shrink-0 items-center gap-2 border-b-2 pb-3 text-xs font-medium " + (tab === item.id ? "border-[var(--color-legacy-2563eb)] text-[var(--color-legacy-2563eb)]" : "border-transparent text-[var(--color-legacy-7c8591)] hover:text-[var(--color-legacy-343b45)]")}>
                  <item.icon className="h-4 w-4" />{item.title}
                </button>)}
              </div>
            </section>
            {tab === "editor" && <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_345px] xl:items-start">
              <WorkflowCanvas nodes={nodes} selectedId={node?.id ?? ""} onSelect={setSelectedNode} />
              <WorkflowInspector record={selected} node={node} canEdit={coordinator && can("campaigns.edit")}
                permissions={grants.filter(p => can(p.permission)).map(p => p.permission)}
                onSaved={async () => { await proposals.refetch(); if (selected.kind === "proposal") await audit.refetch(); }} />
            </div>}
            {tab === "history" && <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
              <RecordHistory record={selected} linked={linked} events={audit.data?.events ?? []}
                auditLoading={audit.isLoading} auditError={audit.error instanceof Error ? audit.error.message : null}
                items={(detail.data?.items ?? []) as DispatchItem[]}
                detailsLoading={detail.isLoading} detailsError={detail.error instanceof Error ? detail.error.message : null}
                retry={retry} />
              <ImportHistory items={imports.data?.items ?? []} loading={imports.isLoading}
                error={imports.error instanceof Error ? imports.error.message : null} retry={() => { void imports.refetch(); }} />
            </div>}
            {tab === "permissions" && <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_330px]">
              <AccessMatrix can={can} />
              <div className="rounded-xl border border-[var(--color-legacy-e6e9ed)] bg-white p-5">
                <LockKeyhole className="h-5 w-5 text-[var(--color-legacy-637188)]" />
                <h3 className="mt-3 text-sm font-semibold text-[var(--color-legacy-222831)]">Camada de execução separada</h3>
                <p className="mt-2 text-xs leading-6 text-[var(--color-legacy-78818e)]">Workflow Definition, Validation, Approval e Execution são conceitos distintos. Nenhum botão de publicação, run ou ferramenta Composio é ligado a um executor nesta Wave.</p>
                <div className="mt-4 flex items-center gap-2 text-[length:var(--type-caption)] text-[var(--color-legacy-747c88)]"><Settings2 className="h-4 w-4" /> Integrações: somente contratos já homologados</div>
              </div>
            </div>}
          </>}
        </>}
      </main>
    </div>
  );
}
