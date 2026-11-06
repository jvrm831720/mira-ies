"use client";

import { useDeferredValue, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ObjectDataTable } from "@/components/object-index/object-data-table";
import type { ObjectField, ObjectSort } from "@/components/object-index/object-index-types";
import type { RowSelectionState } from "@tanstack/react-table";

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
    key: "name", title: "Nome", type: "text", primary: true, sortable: true,
    getValue: row => row.name ?? row.display_name ?? row.label ?? row.code,
  },
  { key: "code", title: "Código", type: "identifier", sortable: true, getValue: row => row.code },
  { key: "status", title: "Estado", type: "status", sortable: true, getValue: row => row.status },
];

const PAGE_SIZE = 25;

type CatalogPage = { items: CatalogRecord[]; has_more: boolean };

export function AcademicCatalogTable({ title, resource, total, tenant, user, load }: {
  title: string;
  resource: "programs" | "subjects" | "teachers" | "terms";
  total: number | undefined;
  tenant?: string;
  user?: string | null;
  load: (path: string, init?: RequestInit) => Promise<CatalogPage>;
}) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<ObjectSort | null>(null);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<RowSelectionState>({});
  const query = useDeferredValue(search.trim());
  const params = new URLSearchParams({
    q: query, sort: sort?.key ?? "name", desc: String(sort?.desc ?? false),
    offset: String(page * PAGE_SIZE), limit: String(PAGE_SIZE),
  });
  const result = useQuery({
    queryKey: ["native-academic", tenant, user, resource, params.toString()],
    queryFn: ({ signal }) => load(`/records/${resource}?${params}`, { signal }),
    enabled: Boolean(tenant && user),
    retry: false,
  });

  return (
    <section className="min-w-0 overflow-hidden rounded-xl border border-[#E6E7EA] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {total !== undefined && <p className="mt-1 text-xs text-[#505967]">{total} no catálogo</p>}
        </div>
        <input type="search" value={search} maxLength={180}
          onChange={event => { setSearch(event.target.value); setPage(0); setSelected({}); }}
          aria-label={`Buscar em ${title.toLocaleLowerCase("pt-BR")}`}
          placeholder="Buscar no catálogo"
          className="rounded-md border border-[#E6E7EA] px-3 py-2 text-sm focus-visible:outline-[#266DF0]" />
      </div>
      {result.isError ? <div role="alert" className="flex flex-wrap items-center gap-3 p-4 text-sm">
        Não foi possível carregar os registros.
        <button type="button" className="underline" onClick={() => void result.refetch()}>Tentar novamente</button>
      </div> : <ObjectDataTable records={result.data?.items ?? []} fields={fields}
        visible={["name", "code", "status"]} onVisibleChange={() => undefined}
        sort={sort} onSortChange={value => { setSort(value); setPage(0); setSelected({}); }}
        selected={selected} onSelectedChange={setSelected} manualSorting loading={result.isLoading}
        emptyText={query ? "Nenhum resultado para a busca." : "Nenhum registro encontrado."} />}
      <div className="flex flex-wrap items-center justify-end gap-3 border-t p-3 text-xs">
        <button type="button" disabled={page === 0} className="disabled:opacity-40"
          onClick={() => { setPage(page - 1); setSelected({}); }}>Anterior</button>
        <span aria-live="polite">Página {page + 1}</span>
        <button type="button" disabled={!result.data?.has_more || query !== search.trim()}
          className="disabled:opacity-40"
          onClick={() => { setPage(page + 1); setSelected({}); }}>Próxima</button>
      </div>
    </section>
  );
}
