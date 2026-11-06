"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Check, Database, Search } from "@/components/ui/icons";
import { normalizeAppKey, unifyAppsCatalog, type CatalogApp } from "@/components/apps/apps-catalog-model";

type AuthOption = { toolkit_slug: string; auth_config_id: string; auth_scheme: string };
type Props = { onComplete: () => void };

export function OnboardingIntegrationSetup({ onComplete }: Props) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Todos");
  const [connecting, setConnecting] = useState("");
  const [error, setError] = useState("");
  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false });
  const ready = !!me.data?.tenant_id;
  const native = useQuery({
    queryKey: ["onboarding-integrations", me.data?.tenant_id, "native"],
    queryFn: api.listConnectors, enabled: ready, retry: 1,
  });
  const remote = useQuery({
    queryKey: ["onboarding-integrations", me.data?.tenant_id, "remote"],
    queryFn: api.composioCatalog, enabled: ready, retry: false,
  });
  const accounts = useQuery({
    queryKey: ["onboarding-integrations", me.data?.tenant_id, "accounts"],
    queryFn: api.composioConnections, enabled: ready, retry: false,
  });
  const options = useQuery({
    queryKey: ["onboarding-integrations", me.data?.tenant_id, "auth-options"],
    queryFn: api.composioOnboardingAuthOptions, enabled: ready, retry: false,
  });
  const jacad = useQuery({ queryKey: ["onboarding-integrations", me.data?.tenant_id, "jacad"],
    queryFn: api.jacadConnection, enabled: ready, retry: false });
  const sponte = useQuery({ queryKey: ["onboarding-integrations", me.data?.tenant_id, "sponte"],
    queryFn: api.sponteConnection, enabled: ready, retry: false });

  const catalog = useMemo(() => unifyAppsCatalog(
    native.data?.connectors ?? [],
    remote.data?.items ?? [],
    accounts.data?.items ?? [],
    { jacad: jacad.data, sponte: sponte.data },
  ), [native.data, remote.data, accounts.data, jacad.data, sponte.data]);
  const visible = useMemo(() => catalog.filter(item => (
    (category === "Todos" || item.category === category) &&
    [item.name, item.description, item.category].some(value => value.toLocaleLowerCase("pt-BR").includes(query.trim().toLocaleLowerCase("pt-BR")))
  )), [catalog, query, category]);
  const categories = ["Todos", "Acadêmico", "Comunicação", "Financeiro", "Produtividade", "IA", "Outros"];
  const activeAccounts = (accounts.data?.items ?? []).filter(item => item.status === "active");
  const activeNative = catalog.filter(item => item.native && item.status === "connected");
  const count = activeAccounts.length + activeNative.length;

  async function start(item: CatalogApp, option: AuthOption) {
    if (connecting) return;
    setConnecting(item.id); setError("");
    try {
      const result = await api.startComposioOnboardingConnection({
        toolkit_slug: option.toolkit_slug, auth_config_id: option.auth_config_id,
      });
      // Never accept an arbitrary API response as an OAuth redirect destination.
      const target = new URL(result.redirect_url);
      if (target.protocol !== "https:" && !(process.env.NODE_ENV === "development" && target.hostname === "localhost" && target.protocol === "http:")) {
        throw new Error("O provedor retornou um endereço de autorização inválido.");
      }
      window.location.assign(target.toString());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível iniciar a conexão.");
      setConnecting("");
    }
  }

  function connection(item: CatalogApp) {
    const provider = normalizeAppKey(item.slug);
    return activeAccounts.filter(row => normalizeAppKey(row.toolkit_slug) === provider);
  }

  if (me.isLoading) return <p className="mira-flow-note" role="status">Verificando o workspace e as permissões…</p>;
  if (me.isError || !ready) return <p className="mira-flow-error" role="alert">Não foi possível validar o workspace. Entre novamente com sua conta para configurar integrações.</p>;

  return <div className="mira-flow-connect">
    <div className="mira-flow-connect-overview" role="status">
      <span><Check size={15} aria-hidden="true" /> Workspace protegido</span>
      <strong>{count} {count === 1 ? "conexão reconhecida" : "conexões reconhecidas"}</strong>
    </div>
    <label className="mira-flow-connect-search">
      <Search size={15} aria-hidden="true" />
      <span className="sr-only">Buscar aplicativos</span>
      <input type="search" placeholder="Buscar sistemas e aplicativos" value={query} onChange={event => setQuery(event.target.value)} />
    </label>
    <div className="mira-flow-connect-categories" role="group" aria-label="Categorias de integração">
      {categories.map(value => <button key={value} type="button" aria-pressed={category === value}
        onClick={() => setCategory(value)} className={category === value ? "active" : ""}>{value}</button>)}
    </div>
    {native.isLoading && !native.data ? <p className="mira-flow-note" role="status">Carregando catálogo da MIRA…</p> :
      native.isError && !native.data ? <p className="mira-flow-error" role="alert">O catálogo não pôde ser carregado. <button type="button" onClick={() => void native.refetch()}>Tentar novamente</button></p> :
      <div className="mira-flow-tool-list mira-flow-connect-list">
        {visible.map(item => {
          const verified = connection(item);
          const nativeConnected = item.native && item.status === "connected";
          const option = (options.data?.items ?? []).find(row =>
            normalizeAppKey(row.toolkit_slug) === normalizeAppKey(item.slug));
          const canConnect = item.external && !!option;
          return <div className="mira-flow-connect-row" key={item.id}>
            <span className="mira-flow-tool-icon"><Database size={15} /></span>
            <div className="mira-flow-tool-copy">
              <strong>{item.name}</strong>
              <small>{item.category} · {item.description}</small>
              {verified.length > 0 ? <small>{verified.length} {verified.length === 1 ? "conta autorizada" : "contas autorizadas"}</small> : null}
            </div>
            <div className="mira-flow-connect-action">
              {verified.length > 0 || nativeConnected ? <span className="mira-flow-connected"><Check size={13} /> Conectado</span> : null}
              {canConnect ? <button type="button" disabled={!!connecting} onClick={() => void start(item, option)}
                aria-label={verified.length > 0 ? "Conectar outra conta de " + item.name : "Conectar " + item.name}>
                {connecting === item.id ? "Abrindo…" : verified.length > 0 ? "Adicionar conta" : "Conectar"}
              </button> : item.native ? <Link href="/conectores" target="_blank" rel="noopener noreferrer">Configurar</Link>
                : !verified.length ? <span className="mira-flow-connect-unavailable">Indisponível</span> : null}
            </div>
          </div>;
        })}
        {visible.length === 0 && <p className="mira-flow-note">Nenhuma ferramenta corresponde à pesquisa.</p>}
      </div>
    }
    {remote.isError || options.isError ? <p className="mira-flow-note" role="status">Conexões OAuth indisponíveis neste ambiente. As integrações nativas continuam acessíveis. O administrador pode ativar as ferramentas autorizadas posteriormente.</p> : null}
    {error && <p className="mira-flow-error" role="alert">{error}</p>}
    <div className="mira-flow-connect-footer">
      <p className="mira-flow-note">Conectar uma conta não ativa sincronizações, cobranças, mensagens ou execução de ferramentas. Você pode adicionar outras contas depois.</p>
      <button type="button" className="mira-flow-primary" onClick={onComplete}>
        {count ? "Entrar no workspace" : "Fazer isso depois"} <span aria-hidden="true">→</span>
      </button>
    </div>
  </div>;
}
