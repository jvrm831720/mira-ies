"use client";


import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { useObjectNavigationState, useObjectScrollRestoration } from "@/components/layout/navigation-context-provider";
import { api } from "@/lib/api";
import { collectionsApi, type CollectionCase } from "@/lib/collections-api";
import { ObjectIndex } from "@/components/object-index/object-index";
import { activeSorts, encodeSorts } from "@/components/object-index/object-index-experience";
import type { ObjectField } from "@/components/object-index/object-index-types";
import { Currency, Time } from "./collection-case-detail";
import { CollectionCaseDrawer } from "./collection-record-experience";
import { canReadCollectionRecord } from "./collection-record-access";

const STATUS = [
  { value: "open", label: "Aberta" }, { value: "agreement", label: "Em acordo" },
  { value: "paid", label: "Paga (origem)" }, { value: "disputed", label: "Contestada" },
  { value: "cancelled", label: "Cancelada" }, { value: "unknown", label: "Não determinada" },
];
const STATUS_LABEL = Object.fromEntries(STATUS.map(item => [item.value, item.label]));
const FIELDS: ObjectField<CollectionCase>[] = [
  { key: "external_ref", title: "Referência", type: "text", primary: true, width: 220,
    getValue: row => row.external_ref, sortable: true, filterable: true,
    render: row => <span className="font-medium text-[var(--color-blue)]">{row.external_ref}</span> },
  { key: "status", title: "Estado", type: "status", width: 140,
    getValue: row => row.status, filterable: true, sortable: true, options: STATUS,
    render: row => <span className="mira-tag mira-tag--blue">{STATUS_LABEL[row.status] ?? row.status}</span> },
  { key: "balance", title: "Saldo informado", type: "currency", width: 160,
    getValue: row => row.balance == null ? null : Number(row.balance), sortable: true, filterable: true,
    render: row => <Currency value={row.balance} /> },
  { key: "source", title: "Origem", type: "text", width: 180, getValue: row => row.source, sortable: true, filterable: true },
  { key: "updated_at", title: "Atualização", type: "datetime", width: 170,
    getValue: row => row.updated_at, sortable: true, filterable: true, render: row => <Time value={row.updated_at} /> },
];
const DEFAULT_VIEWS = [
  { id: "todos", title: "Todos" },
  { id: "abertos", title: "Em aberto", filterKey: "status:open" },
  { id: "acordos", title: "Em acordo", filterKey: "status:agreement" },
  { id: "pagos", title: "Pagos na origem", filterKey: "status:paid" },
];
export function CollectionsExperience() {
  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const { state, onStateChange, selectedId, openRecord, closeRecord, listingHref } = useObjectNavigationState({
    fields: FIELDS, views: DEFAULT_VIEWS,
    tenantId: me.data?.tenant_id, userId: me.data?.user_id,
  });
  const allowed = canReadCollectionRecord(me.data);
  const tenant = me.data?.tenant_id ?? "";
  const user = me.data?.user_id ?? "";
  const sorts = activeSorts(state).filter(item => FIELDS.some(field => field.key === item.key && field.sortable));
  const sortSignature = encodeSorts(sorts);
  const viewStatus = DEFAULT_VIEWS.find(view => view.id === state.view)?.filterKey?.split(":")[1];
  const filters = [
    ...state.filters,
    ...(viewStatus ? [{ key: "status" as const, op: "eq" as const, value: viewStatus }] : []),
  ];
  const filterSignature = JSON.stringify(filters);
  const cases = useQuery({
    queryKey: ["collections", "cases", tenant, user, state.query, filterSignature, sortSignature, state.pageIndex, state.pageSize],
    queryFn: () => collectionsApi.cases({
      q: state.query,
      filters: filterSignature !== "[]" ? filterSignature : undefined,
      sorts: sortSignature || undefined,
      limit: state.pageSize, offset: state.pageIndex * state.pageSize,
    }),
    enabled: allowed && Boolean(tenant), retry: false, staleTime: 20_000,
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
    <div>
      <ObjectIndex<CollectionCase>
        objectKey="collections" title="Casos financeiros"
        description="Origem verificada · contagem integral · views pessoais e do workspace"
        fields={FIELDS} rows={cases.data?.items ?? []} state={state}
        onStateChange={onStateChange}
        defaultViews={DEFAULT_VIEWS} remote total={cases.data?.total} hasMore={cases.data?.has_more}
        loading={cases.isLoading || cases.isFetching} error={cases.isError}
        onRetry={() => void cases.refetch()} onRefresh={() => void cases.refetch()}
        refreshing={cases.isFetching} onOpen={row => openRecord(row.id)}
        emptyTitle="Nenhum caso corresponde aos filtros."
      />
    </div>
    <CollectionCaseDrawer caseId={selectedId} onClose={closeRecord} listingHref={listingHref}
      tenantId={tenant} userId={user} allowed={allowed} />
  </main>;
}
