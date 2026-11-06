"use client";

import { useDeferredValue, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ObjectIndex, initialObjectIndexState } from "@/components/object-index/object-index";
import type { ObjectField } from "@/components/object-index/object-index-types";

export type CatalogRecord = {
  id: string;
  name?: string;
  code?: string;
  display_name?: string;
  label?: string;
  status: string;
};

const fields: ObjectField<CatalogRecord>[] = [
  {
    key: "name", title: "Nome", type: "text", primary: true, sortable: true, filterable: true,
    getValue: row => row.name ?? row.display_name ?? row.label ?? row.code,
  },
  { key: "code", title: "Código", type: "identifier", sortable: true, filterable: true, getValue: row => row.code },
  { key: "status", title: "Estado", type: "status", sortable: true, filterable: true, getValue: row => row.status },
];


type CatalogPage = { items: CatalogRecord[]; total: number };

export function AcademicCatalogTable({ title, resource, total, tenant, user, load }: {
  title: string;
  resource: "programs" | "subjects" | "teachers" | "terms";
  total: number | undefined;
  tenant?: string;
  user?: string | null;
  load: (path: string, init?: RequestInit) => Promise<CatalogPage>;
}) {
  const [state, setState] = useState(() => initialObjectIndexState(fields));
  const query = useDeferredValue(state.query);
  const body = {
    query: query.slice(0, 180), filters: state.filters, sort: state.sort,
    columns: state.columns, page_size: state.pageSize, offset: state.pageIndex * state.pageSize,
  };
  const result = useQuery({
    queryKey: ["native-academic", tenant, user, resource, "index", body],
    queryFn: ({ signal }) => load(`/${resource}/index`, {
      method: "POST", body: JSON.stringify(body), signal,
    }),
    enabled: Boolean(tenant && user), retry: false,
  });
  return <ObjectIndex objectKey={`academic_${resource}`} title={title}
    description={total === undefined ? undefined : `${total} registros no catálogo`}
    fields={fields} rows={result.data?.items ?? []} state={state} onStateChange={setState}
    remote total={result.data?.total ?? 0} loading={result.isLoading} error={result.isError}
    onRetry={() => void result.refetch()} onRefresh={() => void result.refetch()}
    refreshing={result.isFetching} />;
}
