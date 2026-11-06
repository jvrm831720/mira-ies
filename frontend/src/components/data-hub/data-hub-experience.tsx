"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { hasNavigationPermission } from "@/components/layout/navigation";
import {
  AlertTriangle, ArrowRight, CheckCircle2, Clock3, Database, FileSpreadsheet,
  FileUp, History, Info, Plug, RefreshCw, Search, Settings2, ShieldCheck,
} from "@/components/ui/icons";
import { api } from "@/lib/api";
import { dispatchApi } from "@/lib/dispatch-api";
import { categoryLabel, connectionState, importIssues, runState, type DisplayState } from "./data-hub-model";

type Section = "overview" | "connections" | "catalog" | "runs" | "quality" | "settings";
type SyncRow = {
  id: string; source: string; kind: "upload" | "composio";
  status: string; started: string | null; finished: string | null;
  processed: number; total: number; error: boolean;
};

const sections: Array<{ id: Section; label: string }> = [
  { id: "overview", label: "Visão geral" },
  { id: "connections", label: "Conexões" },
  { id: "catalog", label: "Explorar integrações" },
  { id: "runs", label: "Importações e histórico" },
  { id: "quality", label: "Qualidade de dados" },
  { id: "settings", label: "Configurações" },
];

const toneClasses: Record<DisplayState["tone"], string> = {
  neutral: "border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-slate-600)]",
  blue: "border-[var(--color-blue-tint)] bg-[var(--color-blue-tint)] text-[var(--color-blue)]",
  green: "border-[var(--color-green-tint)] bg-[var(--color-green-tint)] text-[var(--color-green)]",
  red: "border-[var(--color-red-tint)] bg-[var(--color-red-tint)] text-[var(--color-red)]",
  amber: "border-[var(--color-peach-tint)] bg-[var(--color-peach-tint)] text-[var(--color-red)]",
};

function Status({ state }: { state: DisplayState }) {
  return <span className={"inline-flex items-center rounded-md border px-2 py-0.5 text-[length:var(--type-caption)] font-medium " + toneClasses[state.tone]}>{state.label}</span>;
}

function Time({ value }: { value?: string | null }) {
  if (!value || Number.isNaN(Date.parse(value))) return <span className="text-[var(--color-muted)]">Não registrado</span>;
  return <time dateTime={value}>{new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))}</time>;
}

function Panel({ title, description, children, action }: { title: string; description?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return <section className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-white">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-blue-tint)] px-5 py-4">
      <div><h2 className="text-[length:var(--type-body-compact)] font-semibold text-[var(--color-ink)]">{title}</h2>{description && <p className="mt-1 text-xs text-[var(--color-slate-600)]">{description}</p>}</div>{action}
    </div>
    {children}
  </section>;
}

function SmallLink({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link className="inline-flex items-center gap-1 text-xs font-medium text-[var(--color-blue)] hover:underline" href={href}>{children}<ArrowRight size={14} aria-hidden /></Link>;
}

function Empty({ message }: { message: string }) {
  return <div className="flex min-h-36 items-center justify-center px-5 py-9 text-center text-xs text-[var(--color-slate-600)]">{message}</div>;
}

function Stat({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return <div className="rounded-xl border border-[var(--color-border)] bg-white px-5 py-4">
    <p className="text-xs text-[var(--color-slate-600)]">{label}</p>
    <p className="mt-3 text-[length:var(--type-display-medium)] font-semibold tracking-[-0.04em] text-[var(--color-ink)]">{value}</p>
    <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">{detail}</p>
  </div>;
}

export function DataHubExperience() {
  const [section, setSection] = useState<Section>("overview");
  const [search, setSearch] = useState("");
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const me = useQuery({ queryKey: ["org-me"], queryFn: () => api.me(), retry: false, staleTime: 60_000 });
  const authorized = hasNavigationPermission(me.data, "data.view");
  const canImport = hasNavigationPermission(me.data, "data.import");
  const canSeeDispatch = hasNavigationPermission(me.data, "campaigns.view");
  const canManageIntegrations = hasNavigationPermission(me.data, "settings.manage");
  const tenantKey = me.data?.tenant_id;
  const onOverview = section === "overview";
  const onConnections = section === "connections";
  const onCatalog = section === "catalog";
  const onRuns = section === "runs";
  const onQuality = section === "quality";

  const catalog = useQuery({
    queryKey: ["data-hub", tenantKey, "native-catalog"],
    queryFn: () => api.listConnectors(), enabled: authorized && (onOverview || onCatalog), staleTime: 60_000, retry: 1,
  });
  const jacad = useQuery({
    queryKey: ["data-hub", tenantKey, "jacad"],
    queryFn: () => api.jacadConnection(), enabled: authorized && (onOverview || onConnections || onQuality), staleTime: 60_000, retry: 1,
  });
  const sponte = useQuery({
    queryKey: ["data-hub", tenantKey, "sponte"],
    queryFn: () => api.sponteConnection(), enabled: authorized && (onOverview || onConnections || onQuality), staleTime: 60_000, retry: 1,
  });
  const uploads = useQuery({
    queryKey: ["data-hub", tenantKey, "upload-history"],
    queryFn: () => api.uploadHistory(30, 0), enabled: authorized && (onOverview || onRuns || onQuality), staleTime: 45_000, retry: 1,
  });
  const composioHistory = useQuery({
    queryKey: ["data-hub", tenantKey, "composio-import-history"],
    queryFn: () => dispatchApi.composioImportHistory(),
    enabled: authorized && canSeeDispatch && (onOverview || onRuns), staleTime: 45_000, retry: 1,
  });

  const composioCatalog = useQuery({
    queryKey: ["data-hub", tenantKey, "composio-catalog"],
    queryFn: () => api.composioCatalog(),
    enabled: authorized && canManageIntegrations && onCatalog, staleTime: 300_000, retry: false,
  });
  const composioConnections = useQuery({
    queryKey: ["data-hub", tenantKey, "composio-connections"],
    queryFn: () => api.composioConnections(),
    enabled: authorized && canManageIntegrations && (onOverview || onConnections), staleTime: 60_000, retry: false,
  });

  const connections = useMemo(() => [
    { id: "jacad", name: "JACAD", category: "Sistema acadêmico", value: jacad.data, loading: jacad.isLoading, error: jacad.isError },
    { id: "sponte", name: "Sponte", category: "Sistema acadêmico", value: sponte.data, loading: sponte.isLoading, error: sponte.isError },
  ], [jacad.data, jacad.isLoading, jacad.isError, sponte.data, sponte.isLoading, sponte.isError]);

  const runs = useMemo<SyncRow[]>(() => {
    const imports = (uploads.data?.items || []).map(item => ({
      id: "upload:" + item.id, source: item.filename, kind: "upload" as const,
      status: item.status, started: item.uploaded_at || null, finished: item.processed_at || null,
      processed: item.processed_rows, total: item.total_rows, error: Boolean(item.error_message),
    }));
    const remote = (composioHistory.data?.items || []).map(item => ({
      id: "composio:" + item.id, source: item.toolkit_slug + " · " + item.tool_slug, kind: "composio" as const,
      status: item.status, started: item.started_at || null, finished: item.finished_at || null,
      processed: item.rows_created + item.rows_updated, total: item.rows_total,
      error: Boolean(item.error_code),
    }));
    return [...imports, ...remote].sort((a, b) => (b.started || "").localeCompare(a.started || ""));
  }, [uploads.data?.items, composioHistory.data?.items]);
  const selected = runs.find(row => row.id === selectedRun);
  const issues = useMemo(() => importIssues(uploads.data?.items || []), [uploads.data?.items]);
  const nativeConfigured = connections.filter(item => item.value?.configured).length;
  const nativeFailures = connections.filter(item => item.value && connectionState(item.value).key === "error").length;
  const connectedComposioAccounts = composioConnections.data?.items || [];
  const remoteCatalogItems = (composioCatalog.data?.items || []).filter(item =>
    (item.name + " " + item.slug + " " + (item.description || "") + " " + (item.categories || []).join(" ")).toLocaleLowerCase("pt-BR").includes(search.toLocaleLowerCase("pt-BR"))
  );
  const catalogItems = useMemo(() => (catalog.data?.connectors || []).filter(item =>
    (item.name + " " + (item.category || "") + " " + (item.description || "")).toLocaleLowerCase("pt-BR").includes(search.toLocaleLowerCase("pt-BR"))
  ), [catalog.data?.connectors, search]);
  const latestSync = connections.map(item => item.value?.last_sync_at).filter((x): x is string => Boolean(x))
    .sort().reverse()[0] || null;

  function refresh() {
    void catalog.refetch();
    void jacad.refetch();
    void sponte.refetch();
    void uploads.refetch();
    if (canSeeDispatch) void composioHistory.refetch();
    if (canManageIntegrations) { void composioCatalog.refetch(); void composioConnections.refetch(); }
  }

  if (me.isLoading) return <><Header title="Dados e integrações" subtitle="Preparando o seu espaço de trabalho." /><main className="p-8 text-sm text-[var(--color-slate-600)]">Verificando acesso...</main></>;
  if (me.isError || !authorized) return <><Header title="Dados e integrações" subtitle="Acesso ao Data Hub" /><main className="m-6 rounded-xl border border-[var(--color-border)] bg-white p-8 text-sm text-[var(--color-slate-600)]" role="alert">Você não tem permissão para consultar este Data Hub. Solicite o acesso <strong>data.view</strong> ao administrador do workspace.</main></>;

  return <>
    <Header title="Data Hub" subtitle="Fontes, conexões e operações de dados em um só lugar." />
    <main className="mx-auto w-full max-w-[1520px] space-y-5 px-4 pb-12 pt-5 md:px-8 md:pt-7 xl:px-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-xs leading-5 text-[var(--color-slate-600)]">As informações abaixo vêm de contratos atuais da MIRA. Catálogo não significa conexão autenticada; agendamento não significa sincronização concluída.</p>
        <button type="button" onClick={refresh} className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-[var(--color-border)] bg-white px-3 text-xs font-medium text-[var(--color-slate-600)] hover:bg-[var(--color-panel)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-blue)]">
          <RefreshCw size={14} aria-hidden /> Atualizar dados
        </button>
      </div>
      <nav aria-label="Seções do Data Hub" className="flex gap-5 overflow-x-auto border-b border-[var(--color-border)]">
        {sections.map(item => <button key={item.id} type="button" onClick={() => setSection(item.id)}
          aria-current={section === item.id ? "page" : undefined}
          className={"shrink-0 border-b-2 px-0.5 pb-3 pt-1 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-blue)] " + (section === item.id ? "border-[var(--color-blue)] text-[var(--color-ink)]" : "border-transparent text-[var(--color-slate-600)] hover:text-[var(--color-ink)]")}>{item.label}</button>)}
      </nav>

      {section === "overview" && <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Stat label="Conexões nativas configuradas" value={jacad.isLoading || sponte.isLoading ? "—" : nativeConfigured} detail="JACAD e Sponte; não representa todo o workspace" />
          <Stat label="Conexões com erro conhecido" value={jacad.isLoading || sponte.isLoading ? "—" : nativeFailures} detail="Entre os dois provedores consultados" />
          <Stat label="Conectores no catálogo" value={catalog.isLoading ? "—" : (catalog.data?.count ?? "—")} detail="Disponibilidade não equivale à homologação" />
          <Stat label="Lotes recentes consultados" value={uploads.isLoading ? "—" : (uploads.data?.items.length ?? "—")} detail="Amostra dos 30 últimos uploads, não total histórico" />
          <Stat label="Contas de apps registradas" value={!canManageIntegrations ? "Restrito" : composioConnections.isLoading ? "—" : (composioConnections.data?.total ?? "Indisponível")} detail="Registros locais; não comprova autenticação remota" />
        </div>
        <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
          <Panel title="Fontes acadêmicas" description="Estado real das conexões nativas consultáveis"
            action={<SmallLink href="/conectores">Gerenciar conexões</SmallLink>}>
            <div className="divide-y divide-[var(--color-blue-tint)]">
              {connections.map(item => <div key={item.id} className="flex items-center justify-between gap-3 px-5 py-4">
                <div className="flex items-center gap-3"><span className="rounded-lg bg-[var(--color-blue-tint)] p-2 text-[var(--color-slate-600)]"><Database size={17} aria-hidden /></span>
                  <div><p className="text-xs font-medium text-[var(--color-ink)]">{item.name}</p><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">{item.category}</p></div></div>
                {item.error ? <Status state={{key:"unknown",label:"Consulta indisponível",tone:"amber"}} /> :
                 item.loading ? <span className="text-xs text-[var(--color-muted)]">Consultando...</span> : <Status state={connectionState(item.value)} />}
              </div>)}
            </div>
          </Panel>
          <Panel title="Atividade verificável" description="Últimos eventos consultados, sem totais inferidos"
            action={<button type="button" className="text-xs font-medium text-[var(--color-blue)]" onClick={() => setSection("runs")}>Ver histórico</button>}>
            <div className="space-y-4 px-5 py-5 text-xs">
              <div className="flex items-center justify-between gap-3"><span className="text-[var(--color-slate-600)]">Última sincronização nativa registrada</span><Time value={latestSync} /></div>
              <div className="flex items-center justify-between gap-3"><span className="text-[var(--color-slate-600)]">Falhas de upload na amostra</span><strong className="font-semibold text-[var(--color-ink)]">{uploads.isLoading ? "—" : issues.filter(x => x.kind === "failed").length}</strong></div>
              <div className="flex items-center justify-between gap-3"><span className="text-[var(--color-slate-600)]">Importações de apps consultadas</span><strong className="font-semibold text-[var(--color-ink)]">{!canSeeDispatch ? "Sem permissão" : composioHistory.isLoading ? "—" : (composioHistory.data?.items.length ?? "Indisponível")}</strong></div>
              <p className="border-t border-[var(--color-blue-tint)] pt-4 text-[length:var(--type-caption)] leading-5 text-[var(--color-muted)]">O histórico de importações não comprova que todas as ações de um aplicativo foram executadas.</p>
            </div>
          </Panel>
        </div>
        <Panel title="Próximas ações" description="Operações existentes — nenhuma é executada automaticamente">
          <div className="grid gap-3 p-5 sm:grid-cols-3">
            <Link href="/conectores" className="group rounded-lg border border-[var(--color-border)] p-4 hover:border-[var(--color-blue-tint)] hover:bg-[var(--color-blue-tint)]"><Plug size={20} className="text-[var(--color-slate-600)]" aria-hidden /><p className="mt-3 text-xs font-semibold text-[var(--color-blue)]">Configurar fontes</p><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">Credenciais e sincronização nas telas homologadas.</p></Link>
            {canImport ? <Link href="/importar" className="group rounded-lg border border-[var(--color-border)] p-4 hover:border-[var(--color-blue-tint)] hover:bg-[var(--color-blue-tint)]"><FileUp size={20} className="text-[var(--color-slate-600)]" aria-hidden /><p className="mt-3 text-xs font-semibold text-[var(--color-blue)]">Importar arquivo</p><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">Preview, mapeamento e confirmação humana.</p></Link> :
              <div className="rounded-lg border border-[var(--color-border)] p-4"><ShieldCheck size={20} className="text-[var(--color-slate-600)]" aria-hidden /><p className="mt-3 text-xs font-semibold text-[var(--color-blue)]">Importação restrita</p><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">Requer a permissão data.import.</p></div>}
            <Link href="/importacoes" className="group rounded-lg border border-[var(--color-border)] p-4 hover:border-[var(--color-blue-tint)] hover:bg-[var(--color-blue-tint)]"><History size={20} className="text-[var(--color-slate-600)]" aria-hidden /><p className="mt-3 text-xs font-semibold text-[var(--color-blue)]">Revisar lotes</p><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">Detalhes do processamento no histórico de uploads.</p></Link>
          </div>
        </Panel>
      </div>}

      {section === "connections" && <Panel title="Conexões" description="Cada integração mantém sua autenticação, origem e histórico próprio."
        action={<SmallLink href="/conectores">Abrir configurações</SmallLink>}>
        <div className="divide-y divide-[var(--color-blue-tint)]">
          {connections.map(item => <article key={item.id} className="grid gap-4 px-5 py-5 md:grid-cols-[1fr_1fr_auto] md:items-center">
            <div className="flex items-center gap-3"><span className="rounded-lg bg-[var(--color-blue-tint)] p-2.5"><Plug size={19} aria-hidden /></span>
              <div><h3 className="text-[length:var(--type-body-compact)] font-semibold text-[var(--color-blue)]">{item.name}</h3><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">{item.category} · Nativo</p></div></div>
            <div className="flex flex-wrap items-center gap-3 text-xs">
              {item.error ? <Status state={{key:"unknown",label:"Falha ao consultar",tone:"amber"}} /> : item.loading ? "Carregando..." : <Status state={connectionState(item.value)} />}
              <p className="text-[var(--color-muted)]">Última sincronização: <Time value={item.value?.last_sync_at} /></p>
            </div>
            <SmallLink href={"/dados/conexoes/" + item.id}>Inspecionar</SmallLink>
          </article>)}
        </div>
        {canManageIntegrations && <div className="border-t border-[var(--color-blue-tint)]">
          <div className="px-5 pb-2 pt-4"><h3 className="text-xs font-semibold text-[var(--color-ink)]">Contas de aplicativos</h3><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">Registros locais deste workspace, sem atualização remota automática.</p></div>
          {composioConnections.isLoading ? <Empty message="Carregando contas locais..." /> :
           composioConnections.isError ? <div role="alert" className="p-5 text-xs text-[var(--color-red)]">Contas de aplicativos indisponíveis. Verifique a configuração das conexões.</div> :
           connectedComposioAccounts.length === 0 ? <Empty message="Nenhuma conta de aplicativo registrada no workspace." /> :
           <div className="divide-y divide-[var(--color-blue-tint)]">{connectedComposioAccounts.map(account => <div key={account.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
             <div><p className="text-xs font-medium text-[var(--color-blue)]">{account.display_name || account.toolkit_slug}</p><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">{account.toolkit_slug} · Registrada em <Time value={account.connected_at} /></p></div>
             <Status state={account.status === "active" ? { key: "configured", label: "Ativa (local)", tone: "blue" } :
               account.status === "revoked" ? { key: "disabled", label: "Revogada", tone: "neutral" } :
               account.status === "expired" ? { key: "disconnected", label: "Expirada", tone: "amber" } :
               account.status === "error" ? { key: "error", label: "Erro", tone: "red" } :
               { key: "unknown", label: "Estado: " + account.status, tone: "neutral" }} />
           </div>)}</div>}
        </div>}
        <p className="border-t border-[var(--color-blue-tint)] px-5 py-4 text-[length:var(--type-caption)] text-[var(--color-muted)]">JACAD e Sponte têm contratos nativos; as contas de apps têm identidade por conexão. Um registro local ativo não comprova sessão remota vigente. Não há restrição de uma conexão por workspace.</p>
      </Panel>}

      {section === "catalog" && <Panel title="Explorar integrações" description="Catálogo retornado pela API; não confundir presença no catálogo com conexão ativa."
        action={<SmallLink href="/conectores">Conectores nativos</SmallLink>}>
        <div className="border-b border-[var(--color-blue-tint)] px-5 py-4">
          <label htmlFor="data-hub-search" className="mb-1.5 block text-[length:var(--type-caption)] font-medium text-[var(--color-slate-600)]">Pesquisar sistemas</label>
          <div className="relative max-w-md"><Search size={15} aria-hidden className="absolute left-3 top-3 text-[var(--color-muted)]" /><input id="data-hub-search" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Nome, categoria ou descrição" className="w-full rounded-lg border border-[var(--color-border)] bg-white py-2.5 pl-9 pr-3 text-xs text-[var(--color-ink)] outline-none focus:border-[var(--color-blue)]" /></div>
        </div>
        {catalog.isLoading ? <Empty message="Consultando o catálogo..." /> : catalog.isError ? <div role="alert" className="px-5 py-8 text-xs text-[var(--color-red)]">Não foi possível consultar o catálogo. Tente atualizar os dados.</div> :
          catalogItems.length === 0 ? <Empty message="Nenhum conector encontrado para esta pesquisa." /> :
          <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">{catalogItems.map(item => <article key={item.id} className="flex flex-col rounded-lg border border-[var(--color-border)] p-4">
            <div className="flex items-start justify-between gap-2"><span className="rounded-lg bg-[var(--color-blue-tint)] p-2 text-[var(--color-slate-600)]"><Plug size={18} aria-hidden /></span><span className="rounded-md bg-[var(--color-blue-tint)] px-2 py-1 text-[length:var(--type-overline)] text-[var(--color-slate-600)]">Catálogo nativo</span></div>
            <h3 className="mt-4 text-[length:var(--type-body-compact)] font-semibold text-[var(--color-ink)]">{item.name}</h3><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-slate-600)]">{categoryLabel(item.category)}</p>
            <p className="mt-3 min-h-10 text-xs leading-5 text-[var(--color-muted)]">{item.description || "Recursos e homologação dependem da configuração do provedor."}</p>
            <div className="mt-auto border-t border-[var(--color-blue-tint)] pt-3"><SmallLink href="/conectores">Ver integrações existentes</SmallLink></div>
          </article>)}</div>}
        {canManageIntegrations && <div className="border-t border-[var(--color-blue-tint)]">
          <div className="px-5 pb-2 pt-5"><h3 className="text-xs font-semibold text-[var(--color-blue)]">Apps disponíveis para conectar</h3><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">Visível somente com settings.manage. Um app habilitado não significa conta conectada ou ações prontas para execução.</p></div>
          {composioCatalog.isLoading ? <Empty message="Consultando aplicativos disponíveis..." /> :
           composioCatalog.isError ? <div role="alert" className="px-5 py-6 text-xs text-[var(--color-red)]">Catálogo adicional indisponível ou não configurado.</div> :
           remoteCatalogItems.length === 0 ? <Empty message="Nenhuma ferramenta remota encontrada." /> :
           <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">{remoteCatalogItems.slice(0, 60).map(item => <article key={item.slug} className="rounded-lg border border-[var(--color-border)] p-4">
             <div className="flex items-start justify-between gap-2"><span className="rounded-lg bg-[var(--color-blue-tint)] p-2"><Plug size={17} aria-hidden /></span><Status state={item.enabled ? {key:"configured",label:"Política habilitada",tone:"blue"} : {key:"disabled",label:"Política desabilitada",tone:"neutral"}} /></div>
             <h4 className="mt-3 text-xs font-semibold text-[var(--color-ink)]">{item.name}</h4><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">{categoryLabel(item.category || item.categories?.[0])}</p>
             <p className="mt-2 text-[length:var(--type-caption)] leading-5 text-[var(--color-muted)]">{item.description || "Nenhuma descrição fornecida pelo provedor."}</p>
             <p className="mt-3 border-t border-[var(--color-blue-tint)] pt-2 text-[length:var(--type-overline)] text-[var(--color-muted)]">{item.selected_tool_slugs?.length || 0} ferramenta(s) selecionada(s) nesta política</p>
           </article>)}</div>}
        </div>}
        {canManageIntegrations && remoteCatalogItems.length > 60 && <p className="border-t border-[var(--color-blue-tint)] px-5 py-3 text-[length:var(--type-caption)] text-[var(--color-slate-600)]">Exibindo os primeiros 60 de {remoteCatalogItems.length} toolkits. Refine a pesquisa para localizar outros itens.</p>}
        <div className="border-t border-[var(--color-blue-tint)] bg-[var(--color-canvas)] px-5 py-3 text-[length:var(--type-caption)] text-[var(--color-muted)]">Cada aplicativo segue permissões, autenticação e políticas próprias. Estar no catálogo não autoriza a execução de ações.</div>
      </Panel>}

      {section === "runs" && <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_330px]">
        <Panel title="Histórico de importações" description="Arquivos enviados e importações por aplicativos, sem misturar execuções não relacionadas."
          action={<SmallLink href="/importacoes">Histórico completo de arquivos</SmallLink>}>
          {uploads.isError && <div role="alert" className="border-b px-5 py-3 text-xs text-[var(--color-red)]">Não foi possível carregar os uploads.</div>}
          {canSeeDispatch && composioHistory.isError && <div role="alert" className="border-b px-5 py-3 text-xs text-[var(--color-red)]">Histórico das importações por apps indisponível.</div>}
          {uploads.isLoading ? <Empty message="Carregando histórico..." /> : runs.length === 0 ? <Empty message="Nenhuma execução retornada pelos serviços consultados." /> :
          <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left text-xs"><thead className="border-b border-[var(--color-blue-tint)] bg-[var(--color-canvas)] text-[length:var(--type-caption)] text-[var(--color-muted)]"><tr><th className="px-5 py-3 font-medium">Origem</th><th className="px-4 py-3 font-medium">Início</th><th className="px-4 py-3 font-medium">Estado</th><th className="px-4 py-3 font-medium">Registros</th><th className="px-4 py-3 font-medium">Detalhes</th></tr></thead>
            <tbody className="divide-y divide-[var(--color-blue-tint)]">{runs.map(row => <tr key={row.id} className={selectedRun === row.id ? "bg-[var(--color-blue-tint)]" : "hover:bg-[var(--color-blue-tint)]"}>
              <td className="max-w-56 truncate px-5 py-4 text-[var(--color-ink)]">{row.source}<p className="mt-1 text-[length:var(--type-overline)] text-[var(--color-muted)]">{row.kind === "upload" ? "Arquivo" : "App conectado / Operação"}</p></td>
              <td className="px-4 py-4 text-[var(--color-slate-600)]"><Time value={row.started} /></td><td className="px-4 py-4"><Status state={runState(row.status)} /></td>
              <td className="px-4 py-4 text-[var(--color-slate-600)]">{row.processed} / {row.total}</td>
              <td className="px-4 py-4"><button type="button" onClick={() => setSelectedRun(row.id)} className="font-medium text-[var(--color-blue)] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-blue)]">Ver</button></td>
            </tr>)}</tbody></table></div>}
        </Panel>
        <Panel title="Detalhes da execução" description="Evidência disponível no contrato atual">
          {!selected ? <Empty message="Selecione uma execução para inspecionar." /> :
          <dl className="space-y-4 px-5 py-5 text-xs">
            <div><dt className="text-[var(--color-muted)]">Identificador</dt><dd className="mt-1 break-all font-mono text-[length:var(--type-caption)] text-[var(--color-blue)]">{selected.id}</dd></div>
            <div><dt className="text-[var(--color-muted)]">Origem</dt><dd className="mt-1 text-[var(--color-blue)]">{selected.source}</dd></div>
            <div><dt className="text-[var(--color-muted)]">Estado</dt><dd className="mt-1"><Status state={runState(selected.status)} /></dd></div>
            <div><dt className="text-[var(--color-muted)]">Início / término</dt><dd className="mt-1 text-[var(--color-blue)]"><Time value={selected.started} /> · <Time value={selected.finished} /></dd></div>
            <div><dt className="text-[var(--color-muted)]">Processados / total conhecido</dt><dd className="mt-1 text-[var(--color-blue)]">{selected.processed} / {selected.total}</dd></div>
            {selected.error && <p className="rounded-lg bg-[var(--color-red-tint)] p-3 text-[length:var(--type-caption)] text-[var(--color-red)]">Falha registrada. Detalhes técnicos e dados sensíveis devem ser consultados no serviço de origem.</p>}
            <p className="border-t border-[var(--color-blue-tint)] pt-4 text-[length:var(--type-caption)] leading-5 text-[var(--color-muted)]">Etapas internas, ator responsável e retries não são fornecidos por estes contratos. Nenhum reprocessamento é iniciado aqui.</p>
          </dl>}
        </Panel>
      </div>}

      {section === "quality" && <Panel title="Qualidade de dados" description="Somente problemas que podem ser demonstrados com evidências persistidas."
        action={<SmallLink href="/importacoes">Investigar lotes</SmallLink>}>
        {uploads.isLoading ? <Empty message="Inspecionando importações recentes..." /> : uploads.isError ? <div role="alert" className="p-6 text-xs text-[var(--color-red)]">Sem evidências suficientes: histórico indisponível.</div> :
          issues.length === 0 && nativeFailures === 0 ? <div className="px-6 py-10 text-center">
            <CheckCircle2 size={24} className="mx-auto text-[var(--color-slate-600)]" aria-hidden />
            <p className="mt-3 text-xs font-medium text-[var(--color-slate-600)]">Nenhum problema identificável nos dados consultados.</p>
            <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">Isto não comprova qualidade integral, ausência de duplicidades ou dados completos.</p>
          </div> :
          <div className="divide-y divide-[var(--color-blue-tint)]">
            {issues.map(issue => <div key={issue.id} className="flex gap-3 px-5 py-4"><AlertTriangle className="mt-0.5 shrink-0 text-[var(--color-red)]" size={17} aria-hidden /><div>
              <p className="text-xs font-medium text-[var(--color-ink)]">{issue.title} · {issue.source}</p>
              <p className="mt-1 text-[length:var(--type-caption)] leading-5 text-[var(--color-muted)]">{issue.kind === "partial" ? issue.detail : "O lote retornou um estado de falha. Verifique o histórico sem expor dados pessoais."}</p></div></div>)}
            {connections.filter(item => item.value && connectionState(item.value).key === "error").map(item => <div key={item.id} className="flex gap-3 px-5 py-4"><AlertTriangle className="mt-0.5 shrink-0 text-[var(--color-red)]" size={17} aria-hidden /><div><p className="text-xs font-medium text-[var(--color-ink)]">Falha de sincronização · {item.name}</p><p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-muted)]">Consulte o provedor na configuração da conexão. Nenhuma ação será repetida automaticamente.</p></div></div>)}
          </div>}
        <div className="flex items-start gap-2 border-t border-[var(--color-blue-tint)] bg-[var(--color-canvas)] px-5 py-4"><Info size={15} className="shrink-0 text-[var(--color-muted)]" aria-hidden /><p className="text-[length:var(--type-caption)] leading-5 text-[var(--color-slate-600)]">Cobertura de campos, duplicidades, conciliação e scores de qualidade requerem contratos dedicados; o Data Hub não inventa esses resultados. Dados ausentes não representam situação favorável.</p></div>
      </Panel>}

      {section === "settings" && <div className="grid gap-5 md:grid-cols-2">
        <Panel title="Mapeamentos e objetos" description="Operações existentes com revisão explícita">
          <div className="space-y-4 p-5"><FileSpreadsheet size={21} className="text-[var(--color-slate-600)]" aria-hidden /><p className="text-xs leading-5 text-[var(--color-slate-600)]">O mapeamento de colunas é realizado no Smart Import. Configurações de objetos personalizados e linhagem completa não são editáveis por este painel.</p>
            {canImport ? <SmallLink href="/importar">Abrir importação inteligente</SmallLink> : <span className="text-xs text-[var(--color-muted)]">Permissão data.import necessária</span>}</div>
        </Panel>
        <Panel title="Políticas e integrações" description="As credenciais nunca são expostas neste painel">
          <div className="space-y-4 p-5"><Settings2 size={21} className="text-[var(--color-slate-600)]" aria-hidden /><p className="text-xs leading-5 text-[var(--color-slate-600)]">Autenticação, revogação, sincronizações e permissões continuam sob os fluxos nativos e controles de workspace. A MIRA só executa ações autorizadas pelas políticas da organização.</p><SmallLink href="/conectores">Gerenciar integrações</SmallLink></div>
        </Panel>
      </div>}
    </main>
  </>;
}
