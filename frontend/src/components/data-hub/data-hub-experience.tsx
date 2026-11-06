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
  neutral: "border-[#E6E7EA] bg-[#F8F9FA] text-[#667085]",
  blue: "border-[#D5E3FF] bg-[#F1F6FF] text-[#266DF0]",
  green: "border-[#D3E9DD] bg-[#F0F8F4] text-[#24714D]",
  red: "border-[#F6D5D2] bg-[#FFF5F4] text-[#B42318]",
  amber: "border-[#F6E0BA] bg-[#FFF9EE] text-[#946200]",
};

function Status({ state }: { state: DisplayState }) {
  return <span className={"inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium " + toneClasses[state.tone]}>{state.label}</span>;
}

function Time({ value }: { value?: string | null }) {
  if (!value || Number.isNaN(Date.parse(value))) return <span className="text-[#98A0AA]">Não registrado</span>;
  return <time dateTime={value}>{new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))}</time>;
}

function Panel({ title, description, children, action }: { title: string; description?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return <section className="overflow-hidden rounded-xl border border-[#E6E7EA] bg-white">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#EDF0F2] px-5 py-4">
      <div><h2 className="text-[13px] font-semibold text-[#101112]">{title}</h2>{description && <p className="mt-1 text-xs text-[#7D8591]">{description}</p>}</div>{action}
    </div>
    {children}
  </section>;
}

function SmallLink({ href, children }: { href: string; children: React.ReactNode }) {
  return <Link className="inline-flex items-center gap-1 text-xs font-medium text-[#266DF0] hover:underline" href={href}>{children}<ArrowRight size={14} aria-hidden /></Link>;
}

function Empty({ message }: { message: string }) {
  return <div className="flex min-h-36 items-center justify-center px-5 py-9 text-center text-xs text-[#77808C]">{message}</div>;
}

function Stat({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return <div className="rounded-xl border border-[#E6E7EA] bg-white px-5 py-4">
    <p className="text-xs text-[#78818D]">{label}</p>
    <p className="mt-3 text-[28px] font-semibold tracking-[-0.04em] text-[#101112]">{value}</p>
    <p className="mt-1 text-[11px] text-[#9AA1AA]">{detail}</p>
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

  const catalog = useQuery({
    queryKey: ["data-hub", tenantKey, "native-catalog"],
    queryFn: () => api.listConnectors(), enabled: authorized, staleTime: 60_000, retry: 1,
  });
  const jacad = useQuery({
    queryKey: ["data-hub", tenantKey, "jacad"],
    queryFn: () => api.jacadConnection(), enabled: authorized, staleTime: 60_000, retry: 1,
  });
  const sponte = useQuery({
    queryKey: ["data-hub", tenantKey, "sponte"],
    queryFn: () => api.sponteConnection(), enabled: authorized, staleTime: 60_000, retry: 1,
  });
  const uploads = useQuery({
    queryKey: ["data-hub", tenantKey, "upload-history"],
    queryFn: () => api.uploadHistory(30, 0), enabled: authorized, staleTime: 45_000, retry: 1,
  });
  const composioHistory = useQuery({
    queryKey: ["data-hub", tenantKey, "composio-import-history"],
    queryFn: () => dispatchApi.composioImportHistory(),
    enabled: authorized && canSeeDispatch, staleTime: 45_000, retry: 1,
  });

  const composioCatalog = useQuery({
    queryKey: ["data-hub", tenantKey, "composio-catalog"],
    queryFn: () => api.composioCatalog(),
    enabled: authorized && canManageIntegrations, staleTime: 300_000, retry: false,
  });
  const composioConnections = useQuery({
    queryKey: ["data-hub", tenantKey, "composio-connections"],
    queryFn: () => api.composioConnections(),
    enabled: authorized && canManageIntegrations, staleTime: 60_000, retry: false,
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

  if (me.isLoading) return <><Header title="Dados e integrações" subtitle="Preparando o seu espaço de trabalho." /><main className="p-8 text-sm text-[#79818B]">Verificando acesso...</main></>;
  if (me.isError || !authorized) return <><Header title="Dados e integrações" subtitle="Acesso ao Data Hub" /><main className="m-6 rounded-xl border border-[#E6E7EA] bg-white p-8 text-sm text-[#555E69]" role="alert">Você não tem permissão para consultar este Data Hub. Solicite o acesso <strong>data.view</strong> ao administrador do workspace.</main></>;

  return <>
    <Header title="Data Hub" subtitle="Fontes, conexões e operações de dados em um só lugar." />
    <main className="mx-auto w-full max-w-[1520px] space-y-5 px-4 pb-12 pt-5 md:px-8 md:pt-7 xl:px-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-xs leading-5 text-[#737C88]">As informações abaixo vêm de contratos atuais da MIRA. Catálogo não significa conexão autenticada; agendamento não significa sincronização concluída.</p>
        <button type="button" onClick={refresh} className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-[#E6E7EA] bg-white px-3 text-xs font-medium text-[#454D59] hover:bg-[#F8F9FA] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#266DF0]">
          <RefreshCw size={14} aria-hidden /> Atualizar dados
        </button>
      </div>
      <nav aria-label="Seções do Data Hub" className="flex gap-5 overflow-x-auto border-b border-[#E6E7EA]">
        {sections.map(item => <button key={item.id} type="button" onClick={() => setSection(item.id)}
          aria-current={section === item.id ? "page" : undefined}
          className={"shrink-0 border-b-2 px-0.5 pb-3 pt-1 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#266DF0] " + (section === item.id ? "border-[#266DF0] text-[#101112]" : "border-transparent text-[#7A828D] hover:text-[#101112]")}>{item.label}</button>)}
      </nav>

      {section === "overview" && <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Stat label="Conexões nativas configuradas" value={jacad.isLoading || sponte.isLoading ? "—" : nativeConfigured} detail="JACAD e Sponte; não representa todo o workspace" />
          <Stat label="Conexões com erro conhecido" value={jacad.isLoading || sponte.isLoading ? "—" : nativeFailures} detail="Entre os dois provedores consultados" />
          <Stat label="Conectores no catálogo" value={catalog.isLoading ? "—" : (catalog.data?.count ?? "—")} detail="Disponibilidade não equivale à homologação" />
          <Stat label="Lotes recentes consultados" value={uploads.isLoading ? "—" : (uploads.data?.items.length ?? "—")} detail="Amostra dos 30 últimos uploads, não total histórico" />
          <Stat label="Contas Composio registradas" value={!canManageIntegrations ? "Restrito" : composioConnections.isLoading ? "—" : (composioConnections.data?.total ?? "Indisponível")} detail="Registros locais; não comprova autenticação remota" />
        </div>
        <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
          <Panel title="Fontes acadêmicas" description="Estado real das conexões nativas consultáveis"
            action={<SmallLink href="/conectores">Gerenciar conexões</SmallLink>}>
            <div className="divide-y divide-[#EDF0F2]">
              {connections.map(item => <div key={item.id} className="flex items-center justify-between gap-3 px-5 py-4">
                <div className="flex items-center gap-3"><span className="rounded-lg bg-[#F5F6F8] p-2 text-[#666E78]"><Database size={17} aria-hidden /></span>
                  <div><p className="text-xs font-medium text-[#252A32]">{item.name}</p><p className="mt-1 text-[11px] text-[#9299A3]">{item.category}</p></div></div>
                {item.error ? <Status state={{key:"unknown",label:"Consulta indisponível",tone:"amber"}} /> :
                 item.loading ? <span className="text-xs text-[#9AA1AA]">Consultando...</span> : <Status state={connectionState(item.value)} />}
              </div>)}
            </div>
          </Panel>
          <Panel title="Atividade verificável" description="Últimos eventos consultados, sem totais inferidos"
            action={<button type="button" className="text-xs font-medium text-[#266DF0]" onClick={() => setSection("runs")}>Ver histórico</button>}>
            <div className="space-y-4 px-5 py-5 text-xs">
              <div className="flex items-center justify-between gap-3"><span className="text-[#79818C]">Última sincronização nativa registrada</span><Time value={latestSync} /></div>
              <div className="flex items-center justify-between gap-3"><span className="text-[#79818C]">Falhas de upload na amostra</span><strong className="font-semibold text-[#353C47]">{uploads.isLoading ? "—" : issues.filter(x => x.kind === "failed").length}</strong></div>
              <div className="flex items-center justify-between gap-3"><span className="text-[#79818C]">Execuções Composio consultadas</span><strong className="font-semibold text-[#353C47]">{!canSeeDispatch ? "Sem permissão" : composioHistory.isLoading ? "—" : (composioHistory.data?.items.length ?? "Indisponível")}</strong></div>
              <p className="border-t border-[#EDF0F2] pt-4 text-[11px] leading-5 text-[#8B929C]">Execuções Composio são histórico de ingestão do Dispatch, não prova de execução remota de ferramentas no Data Hub.</p>
            </div>
          </Panel>
        </div>
        <Panel title="Próximas ações" description="Operações existentes — nenhuma é executada automaticamente">
          <div className="grid gap-3 p-5 sm:grid-cols-3">
            <Link href="/conectores" className="group rounded-lg border border-[#E6E7EA] p-4 hover:border-[#C6D5F8] hover:bg-[#FAFCFF]"><Plug size={20} className="text-[#6C7581]" aria-hidden /><p className="mt-3 text-xs font-semibold text-[#1F242B]">Configurar fontes</p><p className="mt-1 text-[11px] text-[#8E96A1]">Credenciais e sincronização nas telas homologadas.</p></Link>
            {canImport ? <Link href="/importar" className="group rounded-lg border border-[#E6E7EA] p-4 hover:border-[#C6D5F8] hover:bg-[#FAFCFF]"><FileUp size={20} className="text-[#6C7581]" aria-hidden /><p className="mt-3 text-xs font-semibold text-[#1F242B]">Importar arquivo</p><p className="mt-1 text-[11px] text-[#8E96A1]">Preview, mapeamento e confirmação humana.</p></Link> :
              <div className="rounded-lg border border-[#E6E7EA] p-4"><ShieldCheck size={20} className="text-[#6C7581]" aria-hidden /><p className="mt-3 text-xs font-semibold text-[#1F242B]">Importação restrita</p><p className="mt-1 text-[11px] text-[#8E96A1]">Requer a permissão data.import.</p></div>}
            <Link href="/importacoes" className="group rounded-lg border border-[#E6E7EA] p-4 hover:border-[#C6D5F8] hover:bg-[#FAFCFF]"><History size={20} className="text-[#6C7581]" aria-hidden /><p className="mt-3 text-xs font-semibold text-[#1F242B]">Revisar lotes</p><p className="mt-1 text-[11px] text-[#8E96A1]">Detalhes do processamento no histórico de uploads.</p></Link>
          </div>
        </Panel>
      </div>}

      {section === "connections" && <Panel title="Conexões" description="Cada integração mantém sua autenticação, origem e histórico próprio."
        action={<SmallLink href="/conectores">Abrir configurações</SmallLink>}>
        <div className="divide-y divide-[#EDF0F2]">
          {connections.map(item => <article key={item.id} className="grid gap-4 px-5 py-5 md:grid-cols-[1fr_1fr_auto] md:items-center">
            <div className="flex items-center gap-3"><span className="rounded-lg bg-[#F4F6F9] p-2.5"><Plug size={19} aria-hidden /></span>
              <div><h3 className="text-[13px] font-semibold text-[#1F252C]">{item.name}</h3><p className="mt-1 text-[11px] text-[#89919B]">{item.category} · Nativo</p></div></div>
            <div className="flex flex-wrap items-center gap-3 text-xs">
              {item.error ? <Status state={{key:"unknown",label:"Falha ao consultar",tone:"amber"}} /> : item.loading ? "Carregando..." : <Status state={connectionState(item.value)} />}
              <p className="text-[#8A939E]">Última sincronização: <Time value={item.value?.last_sync_at} /></p>
            </div>
            <SmallLink href={"/dados/conexoes/" + item.id}>Inspecionar</SmallLink>
          </article>)}
        </div>
        {canManageIntegrations && <div className="border-t border-[#EDF0F2]">
          <div className="px-5 pb-2 pt-4"><h3 className="text-xs font-semibold text-[#343B45]">Contas Composio</h3><p className="mt-1 text-[11px] text-[#8B929D]">Registros locais deste workspace, sem atualização remota automática.</p></div>
          {composioConnections.isLoading ? <Empty message="Carregando contas locais..." /> :
           composioConnections.isError ? <div role="alert" className="p-5 text-xs text-[#AC3327]">Conexões Composio indisponíveis. Verifique a configuração do serviço.</div> :
           connectedComposioAccounts.length === 0 ? <Empty message="Nenhuma conta Composio registrada no workspace." /> :
           <div className="divide-y divide-[#EDF0F2]">{connectedComposioAccounts.map(account => <div key={account.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
             <div><p className="text-xs font-medium text-[#282F39]">{account.display_name || account.toolkit_slug}</p><p className="mt-1 text-[11px] text-[#818A96]">{account.toolkit_slug} · Registrada em <Time value={account.connected_at} /></p></div>
             <Status state={account.status === "active" ? { key: "configured", label: "Ativa (local)", tone: "blue" } :
               account.status === "revoked" ? { key: "disabled", label: "Revogada", tone: "neutral" } :
               account.status === "expired" ? { key: "disconnected", label: "Expirada", tone: "amber" } :
               account.status === "error" ? { key: "error", label: "Erro", tone: "red" } :
               { key: "unknown", label: "Estado: " + account.status, tone: "neutral" }} />
           </div>)}</div>}
        </div>}
        <p className="border-t border-[#EDF0F2] px-5 py-4 text-[11px] text-[#858D98]">JACAD e Sponte têm contratos nativos; as contas Composio têm identidade por conexão. Um registro local ativo não comprova sessão remota vigente. Não há restrição de uma conexão por workspace.</p>
      </Panel>}

      {section === "catalog" && <Panel title="Explorar integrações" description="Catálogo retornado pela API; não confundir presença no catálogo com conexão ativa."
        action={<SmallLink href="/conectores">Conectores nativos</SmallLink>}>
        <div className="border-b border-[#EDF0F2] px-5 py-4">
          <label htmlFor="data-hub-search" className="mb-1.5 block text-[11px] font-medium text-[#717A85]">Pesquisar sistemas</label>
          <div className="relative max-w-md"><Search size={15} aria-hidden className="absolute left-3 top-3 text-[#929AA5]" /><input id="data-hub-search" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Nome, categoria ou descrição" className="w-full rounded-lg border border-[#E6E7EA] bg-white py-2.5 pl-9 pr-3 text-xs text-[#292F37] outline-none focus:border-[#266DF0]" /></div>
        </div>
        {catalog.isLoading ? <Empty message="Consultando o catálogo..." /> : catalog.isError ? <div role="alert" className="px-5 py-8 text-xs text-[#B42318]">Não foi possível consultar o catálogo. Tente atualizar os dados.</div> :
          catalogItems.length === 0 ? <Empty message="Nenhum conector encontrado para esta pesquisa." /> :
          <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">{catalogItems.map(item => <article key={item.id} className="flex flex-col rounded-lg border border-[#E6E7EA] p-4">
            <div className="flex items-start justify-between gap-2"><span className="rounded-lg bg-[#F5F6F8] p-2 text-[#707988]"><Plug size={18} aria-hidden /></span><span className="rounded-md bg-[#F5F6F8] px-2 py-1 text-[10px] text-[#777F89]">Catálogo nativo</span></div>
            <h3 className="mt-4 text-[13px] font-semibold text-[#252A32]">{item.name}</h3><p className="mt-1 text-[11px] text-[#727B86]">{categoryLabel(item.category)}</p>
            <p className="mt-3 min-h-10 text-xs leading-5 text-[#848C96]">{item.description || "Recursos e homologação dependem da configuração do provedor."}</p>
            <div className="mt-auto border-t border-[#EDF0F2] pt-3"><SmallLink href="/conectores">Ver integrações existentes</SmallLink></div>
          </article>)}</div>}
        {canManageIntegrations && <div className="border-t border-[#EDF0F2]">
          <div className="px-5 pb-2 pt-5"><h3 className="text-xs font-semibold text-[#303843]">Composio · catálogo remoto</h3><p className="mt-1 text-[11px] text-[#8B929E]">Visível somente com settings.manage. Toolkit habilitado não significa conta conectada ou ferramenta pronta para execução.</p></div>
          {composioCatalog.isLoading ? <Empty message="Consultando o catálogo Composio..." /> :
           composioCatalog.isError ? <div role="alert" className="px-5 py-6 text-xs text-[#A53E2E]">Catálogo Composio indisponível ou não configurado.</div> :
           remoteCatalogItems.length === 0 ? <Empty message="Nenhuma ferramenta remota encontrada." /> :
           <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">{remoteCatalogItems.slice(0, 60).map(item => <article key={item.slug} className="rounded-lg border border-[#E6E7EA] p-4">
             <div className="flex items-start justify-between gap-2"><span className="rounded-lg bg-[#F5F6F8] p-2"><Plug size={17} aria-hidden /></span><Status state={item.enabled ? {key:"configured",label:"Política habilitada",tone:"blue"} : {key:"disabled",label:"Política desabilitada",tone:"neutral"}} /></div>
             <h4 className="mt-3 text-xs font-semibold text-[#2B323B]">{item.name}</h4><p className="mt-1 text-[11px] text-[#8A939E]">{categoryLabel(item.category || item.categories?.[0])}</p>
             <p className="mt-2 text-[11px] leading-5 text-[#7F8893]">{item.description || "Nenhuma descrição fornecida pelo provedor."}</p>
             <p className="mt-3 border-t border-[#EDF0F2] pt-2 text-[10px] text-[#89919B]">{item.selected_tool_slugs?.length || 0} ferramenta(s) selecionada(s) nesta política</p>
           </article>)}</div>}
        </div>}
        {canManageIntegrations && remoteCatalogItems.length > 60 && <p className="border-t border-[#EDF0F2] px-5 py-3 text-[11px] text-[#7D8591]">Exibindo os primeiros 60 de {remoteCatalogItems.length} toolkits. Refine a pesquisa para localizar outros itens.</p>}
        <div className="border-t border-[#EDF0F2] bg-[#FAFAFB] px-5 py-3 text-[11px] text-[#818A96]">Ferramentas Composio são regidas por catálogo, allowlist, OAuth e políticas específicas; não há execução genérica neste catálogo.</div>
      </Panel>}

      {section === "runs" && <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_330px]">
        <Panel title="Histórico de importações" description="Uploads do workspace e importações Composio, sem misturar execuções não relacionadas."
          action={<SmallLink href="/importacoes">Histórico completo de arquivos</SmallLink>}>
          {uploads.isError && <div role="alert" className="border-b px-5 py-3 text-xs text-[#B42318]">Não foi possível carregar os uploads.</div>}
          {canSeeDispatch && composioHistory.isError && <div role="alert" className="border-b px-5 py-3 text-xs text-[#B42318]">Histórico Composio indisponível.</div>}
          {uploads.isLoading ? <Empty message="Carregando histórico..." /> : runs.length === 0 ? <Empty message="Nenhuma execução retornada pelos serviços consultados." /> :
          <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left text-xs"><thead className="border-b border-[#EDF0F2] bg-[#FAFAFB] text-[11px] text-[#8B939E]"><tr><th className="px-5 py-3 font-medium">Origem</th><th className="px-4 py-3 font-medium">Início</th><th className="px-4 py-3 font-medium">Estado</th><th className="px-4 py-3 font-medium">Registros</th><th className="px-4 py-3 font-medium">Detalhes</th></tr></thead>
            <tbody className="divide-y divide-[#EDF0F2]">{runs.map(row => <tr key={row.id} className={selectedRun === row.id ? "bg-[#F8FBFF]" : "hover:bg-[#FAFBFC]"}>
              <td className="max-w-56 truncate px-5 py-4 text-[#313843]">{row.source}<p className="mt-1 text-[10px] text-[#9AA2AC]">{row.kind === "upload" ? "Arquivo" : "Composio / Dispatch"}</p></td>
              <td className="px-4 py-4 text-[#7B8390]"><Time value={row.started} /></td><td className="px-4 py-4"><Status state={runState(row.status)} /></td>
              <td className="px-4 py-4 text-[#535B67]">{row.processed} / {row.total}</td>
              <td className="px-4 py-4"><button type="button" onClick={() => setSelectedRun(row.id)} className="font-medium text-[#266DF0] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#266DF0]">Ver</button></td>
            </tr>)}</tbody></table></div>}
        </Panel>
        <Panel title="Detalhes da execução" description="Evidência disponível no contrato atual">
          {!selected ? <Empty message="Selecione uma execução para inspecionar." /> :
          <dl className="space-y-4 px-5 py-5 text-xs">
            <div><dt className="text-[#8F97A1]">Identificador</dt><dd className="mt-1 break-all font-mono text-[11px] text-[#29303A]">{selected.id}</dd></div>
            <div><dt className="text-[#8F97A1]">Origem</dt><dd className="mt-1 text-[#29303A]">{selected.source}</dd></div>
            <div><dt className="text-[#8F97A1]">Estado</dt><dd className="mt-1"><Status state={runState(selected.status)} /></dd></div>
            <div><dt className="text-[#8F97A1]">Início / término</dt><dd className="mt-1 text-[#29303A]"><Time value={selected.started} /> · <Time value={selected.finished} /></dd></div>
            <div><dt className="text-[#8F97A1]">Processados / total conhecido</dt><dd className="mt-1 text-[#29303A]">{selected.processed} / {selected.total}</dd></div>
            {selected.error && <p className="rounded-lg bg-[#FFF6F5] p-3 text-[11px] text-[#B42318]">Falha registrada. Detalhes técnicos e dados sensíveis devem ser consultados no serviço de origem.</p>}
            <p className="border-t border-[#EDF0F2] pt-4 text-[11px] leading-5 text-[#929AA5]">Etapas internas, ator responsável e retries não são fornecidos por estes contratos. Nenhum reprocessamento é iniciado aqui.</p>
          </dl>}
        </Panel>
      </div>}

      {section === "quality" && <Panel title="Qualidade de dados" description="Somente problemas que podem ser demonstrados com evidências persistidas."
        action={<SmallLink href="/importacoes">Investigar lotes</SmallLink>}>
        {uploads.isLoading ? <Empty message="Inspecionando importações recentes..." /> : uploads.isError ? <div role="alert" className="p-6 text-xs text-[#B42318]">Sem evidências suficientes: histórico indisponível.</div> :
          issues.length === 0 && nativeFailures === 0 ? <div className="px-6 py-10 text-center">
            <CheckCircle2 size={24} className="mx-auto text-[#6C9480]" aria-hidden />
            <p className="mt-3 text-xs font-medium text-[#3F4954]">Nenhum problema identificável nos dados consultados.</p>
            <p className="mt-1 text-[11px] text-[#8B939C]">Isto não comprova qualidade integral, ausência de duplicidades ou dados completos.</p>
          </div> :
          <div className="divide-y divide-[#EDF0F2]">
            {issues.map(issue => <div key={issue.id} className="flex gap-3 px-5 py-4"><AlertTriangle className="mt-0.5 shrink-0 text-[#B46E18]" size={17} aria-hidden /><div>
              <p className="text-xs font-medium text-[#303742]">{issue.title} · {issue.source}</p>
              <p className="mt-1 text-[11px] leading-5 text-[#8A919C]">{issue.kind === "partial" ? issue.detail : "O lote retornou um estado de falha. Verifique o histórico sem expor dados pessoais."}</p></div></div>)}
            {connections.filter(item => item.value && connectionState(item.value).key === "error").map(item => <div key={item.id} className="flex gap-3 px-5 py-4"><AlertTriangle className="mt-0.5 shrink-0 text-[#B46E18]" size={17} aria-hidden /><div><p className="text-xs font-medium text-[#303742]">Falha de sincronização · {item.name}</p><p className="mt-1 text-[11px] text-[#8A919C]">Consulte o provedor na configuração da conexão. Nenhuma ação será repetida automaticamente.</p></div></div>)}
          </div>}
        <div className="flex items-start gap-2 border-t border-[#EDF0F2] bg-[#FAFAFB] px-5 py-4"><Info size={15} className="shrink-0 text-[#9099A6]" aria-hidden /><p className="text-[11px] leading-5 text-[#7A8490]">Cobertura de campos, duplicidades, conciliação e scores de qualidade requerem contratos dedicados; o Data Hub não inventa esses resultados. Dados ausentes não representam situação favorável.</p></div>
      </Panel>}

      {section === "settings" && <div className="grid gap-5 md:grid-cols-2">
        <Panel title="Mapeamentos e objetos" description="Operações existentes com revisão explícita">
          <div className="space-y-4 p-5"><FileSpreadsheet size={21} className="text-[#7C8590]" aria-hidden /><p className="text-xs leading-5 text-[#747D89]">O mapeamento de colunas é realizado no Smart Import. Configurações de objetos personalizados e linhagem completa não são editáveis por este painel.</p>
            {canImport ? <SmallLink href="/importar">Abrir importação inteligente</SmallLink> : <span className="text-xs text-[#9BA3AD]">Permissão data.import necessária</span>}</div>
        </Panel>
        <Panel title="Políticas e integrações" description="As credenciais nunca são expostas neste painel">
          <div className="space-y-4 p-5"><Settings2 size={21} className="text-[#7C8590]" aria-hidden /><p className="text-xs leading-5 text-[#747D89]">Autenticação, revogação, sincronizações e permissões continuam sob os fluxos nativos e controles de workspace. Composio só executa ferramentas autorizadas por política.</p><SmallLink href="/conectores">Gerenciar integrações</SmallLink></div>
        </Panel>
      </div>}
    </main>
  </>;
}
