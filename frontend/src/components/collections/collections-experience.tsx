"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { api } from "@/lib/api";
import { collectionsApi, type CollectionCase } from "@/lib/collections-api";
import { ObjectIndex, initialObjectIndexState, type ObjectIndexState } from "@/components/object-index/object-index";
import type { ObjectField } from "@/components/object-index/object-index-types";
import { CaseDetail, Currency, Time } from "./collection-case-detail";

const STATUS = [
  { value: "open", label: "Aberta" }, { value: "agreement", label: "Em acordo" },
  { value: "paid", label: "Paga (origem)" }, { value: "disputed", label: "Contestada" },
  { value: "cancelled", label: "Cancelada" }, { value: "unknown", label: "Não determinada" },
];
const STATUS_LABEL = Object.fromEntries(STATUS.map(item => [item.value, item.label]));
const FIELDS: ObjectField<CollectionCase>[] = [
  { key: "external_ref", title: "Referência", type: "text", primary: true, width: 220,
    getValue: row => row.external_ref, sortable: true,
    render: row => <span className="font-medium text-[var(--color-blue)]">{row.external_ref}</span> },
  { key: "status", title: "Estado", type: "status", width: 140,
    getValue: row => row.status, filterable: true, sortable: true, options: STATUS,
    render: row => <span className="mira-tag mira-tag--blue">{STATUS_LABEL[row.status] ?? row.status}</span> },
  { key: "balance", title: "Saldo informado", type: "currency", width: 160,
    getValue: row => row.balance == null ? null : Number(row.balance), sortable: true,
    render: row => <Currency value={row.balance} /> },
  { key: "source", title: "Origem", type: "text", width: 180, getValue: row => row.source, sortable: true },
  { key: "updated_at", title: "Atualização", type: "datetime", width: 170,
    getValue: row => row.updated_at, sortable: true, render: row => <Time value={row.updated_at} /> },
];
const DEFAULT_VIEWS = [
  { id: "todos", title: "Todos" },
  { id: "abertos", title: "Em aberto", filterKey: "status:open" },
  { id: "acordos", title: "Em acordo", filterKey: "status:agreement" },
  { id: "pagos", title: "Pagos na origem", filterKey: "status:paid" },
];
function serverStatus(state: ObjectIndexState): string[] {
  const filtered = state.filters.filter(item => item.key === "status" && ["eq", "in"].includes(item.op));
  const selected = filtered.length
    ? filtered.flatMap(item => Array.isArray(item.value) ? item.value.map(String) : [String(item.value ?? "")])
    : [];
  const viewStatus = DEFAULT_VIEWS.find(view => view.id === state.view)?.filterKey?.split(":")[1];
  return (viewStatus ? selected.filter(value => value === viewStatus).length || !filtered.length ? [viewStatus] : ["__none__"] : selected)
    .filter(value => STATUS.some(item => item.value === value) || value === "__none__");
}

export function CollectionsExperience() {
  const [state, setState] = useState(() => initialObjectIndexState(FIELDS));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const profile = me.data?.operation_profile;
  const allowedProfile = ["collection", "debt_collection", "billing", "cobranca"].includes(profile ?? "");
  const allowed = allowedProfile && hasNavigationPermission(me.data, "audit.view")
    && (!Array.isArray(me.data?.enabled_modules) || me.data.enabled_modules.includes("billing"));
  const tenant = me.data?.tenant_id ?? "";
  const user = me.data?.user_id ?? "";
  const statuses = useMemo(() => serverStatus(state), [state]);
  const statusSignature = statuses.join(",");
  const cases = useQuery({
    queryKey: ["collections", "cases", tenant, user, state.query, statusSignature, state.sort, state.pageIndex, state.pageSize],
    queryFn: () => collectionsApi.cases({
      q: state.query,
      statuses: statuses.includes("__none__") ? ["__none__"] : statuses,
      limit: state.pageSize, offset: state.pageIndex * state.pageSize,
      sort: state.sort?.key, desc: state.sort?.desc,
    }),
    enabled: allowed && Boolean(tenant), retry: false, staleTime: 20_000,
  });
  const detail = useQuery({
    queryKey: ["collections", "detail", tenant, user, selectedId],
    queryFn: () => collectionsApi.detail(selectedId!),
    enabled: allowed && Boolean(selectedId) && Boolean(tenant), retry: false, staleTime: 20_000,
  });
  useEffect(() => { setSelectedId(null); setState(initialObjectIndexState(FIELDS)); }, [tenant, user]);
  if (me.isLoading) return <main className="mira-page p-7 text-xs text-[var(--color-muted)]" role="status">Verificando acesso…</main>;
  if (me.isError || !allowed) return <main className="mira-page p-7 text-sm text-[var(--color-muted)]" role="alert">A área de cobrança não está disponível para este workspace ou cargo.</main>;
  return <main className="mira-page space-y-5 p-5 md:p-7">
    <Header title="Cobrança" subtitle="Casos e obrigações informadas por fontes verificadas" />
    <p className="rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3 text-xs text-[var(--color-slate-600)]">
      Consulta somente leitura. Não é possível criar acordos, alterar dívidas ou enviar cobranças nesta tela.
      Filtros de estado e ordenação são aplicados no servidor a todo o conjunto do workspace.
    </p>
    <div className={selectedId ? "grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]" : ""}>
      <ObjectIndex<CollectionCase>
        objectKey="collections" title="Casos financeiros"
        description="Origem verificada · contagem integral · visualizações pessoais"
        fields={FIELDS} rows={cases.data?.items ?? []} state={state}
        onStateChange={next => { setSelectedId(null); setState(next); }}
        defaultViews={DEFAULT_VIEWS} remote total={cases.data?.total}
        loading={cases.isLoading || cases.isFetching} error={cases.isError}
        onRetry={() => void cases.refetch()} onRefresh={() => void cases.refetch()}
        refreshing={cases.isFetching} onOpen={row => setSelectedId(row.id)}
        emptyTitle="Nenhum caso corresponde aos filtros."
      />
      {selectedId && <CaseDetail record={detail.data} loading={detail.isLoading}
        error={detail.isError} onClose={() => setSelectedId(null)} />}
    </div>
  </main>;
}
