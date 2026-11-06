"use client";

import { useState } from "react";
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

export function AcademicCatalogTable({ title, records, total }: {
  title: string;
  records: CatalogRecord[];
  total: number | undefined;
}) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<ObjectSort | null>(null);
  const [selected, setSelected] = useState<RowSelectionState>({});
  const visible = title === "Professores" ? ["name", "status"] : ["name", "code", "status"];
  const query = search.trim().toLocaleLowerCase("pt-BR");
  const results = records.filter(record =>
    fields.some(field => String(field.getValue(record) ?? "").toLocaleLowerCase("pt-BR").includes(query)),
  );

  return (
    <section className="min-w-0 overflow-hidden rounded-xl border border-[#E6E7EA] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          <p className="mt-1 text-xs text-[#505967]">
            {records.length} na prévia{total === undefined ? "" : ` · ${total} no catálogo`}
          </p>
        </div>
        <input type="search" value={search} onChange={event => setSearch(event.target.value)}
          aria-label={`Buscar na prévia de ${title.toLocaleLowerCase("pt-BR")}`}
          placeholder="Buscar na prévia"
          className="rounded-md border border-[#E6E7EA] px-3 py-2 text-sm focus-visible:outline-[#266DF0]" />
      </div>
      <ObjectDataTable records={results} fields={fields} visible={visible}
        onVisibleChange={() => undefined} sort={sort} onSortChange={setSort}
        selected={selected} onSelectedChange={setSelected}
        emptyText={query ? "Nenhum resultado na prévia." : "Nenhum registro na prévia."} />
    </section>
  );
}
