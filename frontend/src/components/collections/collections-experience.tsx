"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { useObjectNavigationState, useObjectScrollRestoration } from "@/components/layout/navigation-context-provider";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { api } from "@/lib/api";
import { collectionsApi, type CollectionCase } from "@/lib/collections-api";
import { ObjectIndex, type ObjectIndexState } from "@/components/object-index/object-index";
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
  // Remote ObjectIndex filters must be evaluated over the full tenant dataset,
  // never just the current page. Every supported choice operator is mapped here.
  let allowed = STATUS.map(item => item.value);
  for (const filter of state.filters.filter(item => item.key === "status")) {
    const values = (Array.isArray(filter.value) ? filter.value : [filter.value])
      .filter(value => value != null).map(String);
    switch (filter.op) {
      case "eq": case "in":
        allowed = allowed.filter(status => values.includes(status));
        break;
      case "neq":
        allowed = allowed.filter(status => !values.includes(status));
        break;
      case "empty":
        allowed = [];
        break;
      default:
        // No free-form operators are accepted for a status choice.
        allowed = [];
    }
  }
  const viewStatus = DEFAULT_VIEWS.find(view => view.id === state.view)?.filterKey?.split(":")[1];
  return viewStatus ? allowed.filter(status => status === viewStatus) : allowed;
}

export function CollectionsExperience() {
  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const { state, onStateChange, selectedId, openRecord, closeRecord, listingHref } = useObjectNavigationState({
    fields: FIELDS, views: DEFAULT_VIEWS,
    tenantId: me.data?.tenant_id, userId: me.data?.user_id,
  });
  const profile = me.data?.operation_profile;
  const educationWithBilling = profile === "institution"
    && Array.isArray(me.data?.enabled_modules) && me.data.enabled_modules.includes("billing");
  const allowedProfile = ["collection", "debt_collection", "billing", "cobranca"].includes(profile ?? "") || educationWithBilling;
  const allowed = allowedProfile && hasNavigationPermission(me.data, "audit.view")
    && (!Array.isArray(me.data?.enabled_modules) || me.data.enabled_modules.includes("billing"));
  const tenant = me.data?.tenant_id ?? "";
  const user = me.data?.user_id ?? "";
  const statuses = useMemo(() => serverStatus(state), [state]);
  const statusSignature = statuses.join(",");
  const cases = useQuery({
    queryKey: ["collections", "cases", tenant, user, state.query, statusSignature, state.sort, state.pageIndex, state.pageSize],
    queryFn: () => statuses.length === 0 ? Promise.resolve({
      items: [], total: 0, limit: state.pageSize,
      offset: state.pageIndex * state.pageSize, has_more: false,
    }) : collectionsApi.cases({
      q: state.query,
      statuses,
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
  useObjectScrollRestoration({
    tenantId: tenant, userId: user, listingHref, selectedId,
    ready: Boolean(cases.data && !cases.isError && !cases.isFetching),
  });
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
        onStateChange={onStateChange}
        defaultViews={DEFAULT_VIEWS} remote total={cases.data?.total}
        loading={cases.isLoading || cases.isFetching} error={cases.isError}
        onRetry={() => void cases.refetch()} onRefresh={() => void cases.refetch()}
        refreshing={cases.isFetching} onOpen={row => openRecord(row.id)}
        emptyTitle="Nenhum caso corresponde aos filtros."
      />
      {selectedId && <CaseDetail record={detail.data} loading={detail.isLoading}
        error={detail.isError} onClose={closeRecord} />}
    </div>
  </main>;
}
