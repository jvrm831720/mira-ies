"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { ArrowRight, Check, Info, RefreshCw } from "@/components/ui/icons";
import { AppBrandIcon, safeHttpsUrl } from "./app-brand-icon";
import { profileFor } from "./apps-brand-profiles";
import { normalizeAppKey, unifyAppsCatalog, type CatalogApp } from "./apps-catalog-model";

function ConnectionState({ item }: { item: CatalogApp }) {
  const ready = item.status === "connected" || item.status === "configured";
  return <span className={"inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs " +
    (ready ? "border-[var(--mira-apps-ok-border)] bg-[var(--mira-apps-ok-bg)] text-[var(--mira-apps-ok)]" :
      "border-[var(--mira-apps-border)] bg-[var(--mira-apps-chip)] text-[var(--mira-apps-muted)]")}>
    {ready ? <Check size={13} aria-hidden="true"/> : <Info size={13} aria-hidden="true"/>}
    {item.statusText}
  </span>;
}

function detailsRoute(item: CatalogApp) {
  if (item.id === "jacad" || item.id === "sponte") return `/dados/conexoes/${item.id}`;
  if (item.id === "totvsrm") return "/conectores/totvs-rm";
  return item.route;
}

export function AppDetailExperience({ slug }: { slug: string }) {
  const id = normalizeAppKey(slug);
  const [connecting, setConnecting] = useState(false);
  const me = useQuery({queryKey:["org-me"],queryFn:api.me,staleTime:60_000,retry:false});
  const canRead = hasNavigationPermission(me.data,"data.view");
  const canManage = hasNavigationPermission(me.data,"settings.manage");
  const tenant = me.data?.tenant_id;
  const nativeCatalog = useQuery({
    queryKey:["apps-catalog",tenant,"native"],queryFn:api.listConnectors,enabled:canRead,staleTime:300_000,retry:1,
  });
  const curatedCatalog = useQuery({
    queryKey:["apps-catalog",tenant,"curated"],queryFn:api.composioCuratedCategories,enabled:canRead,staleTime:300_000,retry:1,
  });
  const externalCatalog = useQuery({
    queryKey:["apps-catalog",tenant,"external"],queryFn:api.composioCatalog,enabled:canRead&&canManage,staleTime:300_000,retry:false,
  });
  const accounts = useQuery({
    queryKey:["apps-catalog",tenant,"accounts"],queryFn:api.composioConnections,enabled:canRead&&canManage,staleTime:60_000,retry:false,
  });
  const authOptions = useQuery({
    queryKey:["apps-catalog",tenant,"auth-options"],queryFn:api.composioOnboardingAuthOptions,enabled:canRead&&canManage,retry:false,
  });
  const jacad = useQuery({
    queryKey:["apps-catalog",tenant,"jacad"],queryFn:api.jacadConnection,enabled:canRead&&canManage,staleTime:60_000,retry:false,
  });
  const sponte = useQuery({
    queryKey:["apps-catalog",tenant,"sponte"],queryFn:api.sponteConnection,enabled:canRead&&canManage,staleTime:60_000,retry:false,
  });
  const curatedApps = useMemo(() => curatedCatalog.data?.items.flatMap(group =>
    group.composio_toolkits.map(tool => ({
      slug:tool.slug,name:tool.name,description:group.name,mira_category_label:group.name,
    }))
  ) || [], [curatedCatalog.data]);
  const rows = useMemo(() => unifyAppsCatalog(
    nativeCatalog.data?.connectors || [],
    [...curatedApps,...(externalCatalog.data?.items || [])],
    accounts.data?.items || [],
    {jacad:jacad.data,sponte:sponte.data},
  ),[nativeCatalog.data,curatedApps,externalCatalog.data,accounts.data,jacad.data,sponte.data]);
  const item = rows.find(app => app.id === id);
  const otherApps = item ? rows.filter(app => app.id !== id && app.category === item.category).slice(0,4) : [];
  const website = safeHttpsUrl(profileFor(id)?.website || item?.website);
  const option = item && authOptions.data?.items.find(row =>
    normalizeAppKey(row.toolkit_slug) === normalizeAppKey(item.slug));
  const busy = nativeCatalog.isLoading || curatedCatalog.isLoading ||
    (canManage && externalCatalog.isLoading && !externalCatalog.data);

  async function connectApp() {
    if (connecting || !option) return;
    setConnecting(true);
    try {
      const response = await api.startComposioOnboardingConnection({
        toolkit_slug:option.toolkit_slug,auth_config_id:option.auth_config_id,
      });
      const target = new URL(response.redirect_url);
      if (target.protocol !== "https:" && !(process.env.NODE_ENV === "development" &&
        target.hostname === "localhost" && target.protocol === "http:")) {
        throw new Error("Endereço de autorização inválido.");
      }
      window.location.assign(target.toString());
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível iniciar a conexão.");
      setConnecting(false);
    }
  }

  const actionClass = "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--mira-apps-blue)]";
  return <div className="mira-apps-page min-h-dvh bg-[var(--mira-apps-dark)] text-[var(--mira-apps-white)]">
    <header className="flex min-h-[58px] items-center border-b border-[var(--mira-apps-border)] px-5 md:px-9">
      <nav aria-label="Navegação do catálogo" className="flex min-w-0 items-center gap-2 text-sm">
        <Link className="text-[var(--mira-apps-muted)] hover:text-[var(--mira-apps-white)]" href="/apps">Apps e integrações</Link>
        <span className="text-[var(--mira-apps-muted)]">/</span>
        <span className="truncate font-medium">{item?.name || "Detalhes do aplicativo"}</span>
      </nav>
    </header>
    <main className="mx-auto max-w-[1200px] px-5 pb-20 pt-9 md:px-9 md:pt-12">
      {me.isLoading ? <p role="status" className="text-sm text-[var(--mira-apps-muted)]">Verificando permissões…</p> :
      me.isError || !canRead ? <section role="alert" className="rounded-xl border border-[var(--mira-apps-border)] p-7">
        Você não tem permissão para visualizar integrações neste workspace.
      </section> :
      busy && !item ? <p role="status" className="flex items-center gap-2 text-sm text-[var(--mira-apps-muted)]">
        <RefreshCw size={17} className="animate-spin"/> Carregando detalhes…
      </p> :
      !item ? <div role="alert" className="rounded-2xl border border-[var(--mira-apps-border)] p-7">
        <h1 className="text-xl font-semibold">Aplicativo não encontrado</h1>
        <p className="mt-2 text-sm text-[var(--mira-apps-muted)]">Este app não está disponível no catálogo acessível ao seu workspace. O catálogo pode estar temporariamente indisponível.</p>
        <Link href="/apps" className="mt-5 inline-flex items-center gap-2 text-sm underline">Voltar ao catálogo</Link>
      </div> : <>
        <div className="flex flex-wrap items-start justify-between gap-6 border-b border-[var(--mira-apps-border)] pb-10">
          <div className="flex min-w-0 flex-1 items-start gap-5">
            <AppBrandIcon key={item.id} item={item} large/>
            <div className="min-w-0">
              <p className="mb-1 text-xs font-medium text-[var(--mira-apps-muted)]">INTEGRAÇÃO</p>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{item.name}</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--mira-apps-muted)]">
                {item.description}
              </p>
              <div className="mt-4"><ConnectionState item={item}/></div>
            </div>
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:min-w-[185px]">
            {canManage && item.external && option &&
              <button type="button" onClick={() => void connectApp()} disabled={connecting}
                className={actionClass + " bg-[var(--mira-apps-blue)] text-white disabled:cursor-not-allowed disabled:opacity-60"}>
                {connecting ? "Abrindo autorização…" : item.status === "configured" ? "Conectar outra conta" : "Conectar aplicativo"}
                <ArrowRight size={16} aria-hidden="true"/>
              </button>}
            {canManage && (item.native || item.status === "configured" || item.status === "connected") &&
              <Link href={detailsRoute(item)} className={actionClass + " border border-[var(--mira-apps-border)] bg-[var(--mira-apps-chip)] hover:bg-[var(--mira-apps-hover)]"}>
                Gerenciar integração <ArrowRight size={16} aria-hidden="true"/>
              </Link>}
            {canManage && item.external && !option && !item.native &&
              <p className="max-w-[260px] text-xs leading-5 text-[var(--mira-apps-muted)]">
                Conexão ainda não habilitada. A autenticação precisa ser configurada antes de conectar.
              </p>}
            {!canManage && <p className="text-xs leading-5 text-[var(--mira-apps-muted)]">Somente administradores podem configurar conexões.</p>}
          </div>
        </div>

        <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_285px] lg:gap-16">
          <div className="space-y-10">
            <section aria-labelledby="app-overview" className="space-y-3">
              <h2 id="app-overview" className="text-xl font-semibold">Visão geral</h2>
              <p className="max-w-prose text-sm leading-7 text-[var(--mira-apps-muted)]">
                {profileFor(item.id)?.about || item.description}
              </p>
              <p className="max-w-prose text-sm leading-7 text-[var(--mira-apps-muted)]">
                A MIRA pode reunir informações desta ferramenta com os dados autorizados da organização, respeitando as permissões e o escopo de cada conexão.
              </p>
            </section>
            <section aria-labelledby="app-how" className="space-y-3 border-t border-[var(--mira-apps-border)] pt-8">
              <h2 id="app-how" className="text-xl font-semibold">Como funciona</h2>
              <p className="max-w-prose text-sm leading-7 text-[var(--mira-apps-muted)]">
                {item.native
                  ? "Os conectores nativos utilizam configurações e processos próprios de importação ou sincronização da MIRA. O fluxo e os dados disponíveis variam conforme o sistema e a homologação de cada instituição."
                  : "Quando a autenticação desta ferramenta estiver habilitada, um administrador poderá autorizar uma conta. A autorização registra a conexão no workspace; a execução de ações e o acesso a dados dependem das permissões e políticas aplicáveis."}
              </p>
              <div className="rounded-xl border border-[var(--mira-apps-border)] bg-[var(--mira-apps-card)] p-5">
                <p className="text-xs font-medium text-[var(--mira-apps-muted)]">Estado atual neste workspace</p>
                <div className="mt-3"><ConnectionState item={item}/></div>
                {item.connectedAccountName && <p className="mt-3 break-all text-sm text-[var(--mira-apps-muted)]">
                  Conta registrada: {item.connectedAccountName}
                </p>}
                <p className="mt-3 text-xs leading-5 text-[var(--mira-apps-muted)]">
                  Uma conta registrada ou configurada não garante uma sincronização ativa nem a permissão de execução de ferramentas.
                </p>
              </div>
            </section>
            <section aria-labelledby="app-setup" className="space-y-4 border-t border-[var(--mira-apps-border)] pt-8">
              <h2 id="app-setup" className="text-xl font-semibold">Como configurar</h2>
              <ol className="space-y-5">
                {[
                  ["Verifique as permissões","Um administrador do workspace deve autorizar o acesso e definir quais dados podem ser utilizados."],
                  [item.native ? "Configure o conector" : "Autorize a conta",
                    item.native ? "Abra a área de configuração nativa e informe as credenciais e parâmetros exigidos pelo sistema." :
                    "Se a conexão estiver habilitada, selecione Conectar aplicativo e conclua a autorização no provedor."],
                  ["Valide a disponibilidade","Confirme a conexão e os dados permitidos antes de utilizar esta ferramenta nas operações da MIRA."],
                ].map(([heading,description],index) =>
                  <li key={heading} className="flex gap-4">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-[var(--mira-apps-border)] bg-[var(--mira-apps-chip)] text-sm font-semibold">{index+1}</span>
                    <div><h3 className="text-sm font-semibold">{heading}</h3><p className="mt-1 text-sm leading-6 text-[var(--mira-apps-muted)]">{description}</p></div>
                  </li>)}
              </ol>
            </section>
          </div>
          <aside aria-label="Informações do aplicativo" className="self-start rounded-2xl border border-[var(--mira-apps-border)] bg-[var(--mira-apps-card)] p-6">
            <h2 className="text-sm font-semibold">Sobre o aplicativo</h2>
            <div className="mt-6 space-y-5 text-sm">
              <div><p className="text-xs text-[var(--mira-apps-muted)]">Disponibilizado por</p>
                <p className="mt-1 font-medium">{item.name}</p></div>
              <div><p className="text-xs text-[var(--mira-apps-muted)]">Categoria</p>
                <p className="mt-1 font-medium">{item.category}</p></div>
              <div><p className="text-xs text-[var(--mira-apps-muted)]">Tipo de integração</p>
                <p className="mt-1 font-medium">{item.native && item.external ? "Nativa e via aplicativo" : item.native ? "Conector nativo" : "Aplicativo externo"}</p></div>
              <div><p className="text-xs text-[var(--mira-apps-muted)]">Recursos</p>
                {website ?
                  <a href={website} target="_blank" rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1.5 font-medium text-[var(--mira-apps-blue-light)] hover:underline">
                    Site oficial <ArrowRight size={15} aria-hidden="true"/>
                  </a> : <p className="mt-1 text-sm text-[var(--mira-apps-muted)]">Consulte o administrador para obter a documentação do provedor.</p>}
              </div>
            </div>
          </aside>
        </div>
        {otherApps.length > 0 && <section aria-label={"Outros aplicativos de "+item.category} className="mt-14 border-t border-[var(--mira-apps-border)] pt-8">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Outros apps em {item.category}</h2>
            <Link href="/apps" className="inline-flex items-center gap-2 text-sm text-[var(--mira-apps-muted)] hover:text-[var(--mira-apps-white)]">
              Ver todos <ArrowRight size={15} aria-hidden="true"/>
            </Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {otherApps.map(app => <Link key={app.id} href={`/apps/${encodeURIComponent(app.id)}`}
              className="group rounded-xl border border-[var(--mira-apps-border)] bg-[var(--mira-apps-card)] p-4 transition-colors hover:border-[var(--mira-apps-blue)]">
              <AppBrandIcon item={app}/>
              <h3 className="mt-3 text-sm font-semibold">{app.name}</h3>
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--mira-apps-muted)]">{app.description}</p>
            </Link>)}
          </div>
        </section>}
      </>}
    </main>
  </div>;
}
