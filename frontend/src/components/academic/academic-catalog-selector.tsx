"use client";

import { useDeferredValue, useState } from "react";
import { useQuery } from "@tanstack/react-query";

type Option = { id: string; name: string; code: string };
type Page = { items: Option[]; has_more: boolean };
export type AcademicResource = "programs" | "subjects" | "teachers" | "terms" | "classes" | "curricula";

export function AcademicCatalogSelector({ id, label, resource, required, value, tenant, user, load, onChange, programId, status }: {
  programId?: string;
  status?: string;
  id: string;
  label: string;
  resource: AcademicResource;
  required?: boolean;
  value: string;
  tenant?: string;
  user?: string | null;
  load: (path: string, init?: RequestInit) => Promise<Page>;
  onChange: (value: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [chosen, setChosen] = useState<Option>();
  const query = useDeferredValue(search.trim());
  const params = new URLSearchParams({ q: query, offset: String(offset), limit: "25" });
  if (programId) params.set("program_id", programId);
  if (status) params.set("status", status);
  const result = useQuery({
    queryKey: ["native-academic", tenant, user, "selector", resource, params.toString()],
    queryFn: ({ signal }) => load(`/records/${resource}?${params}`, { signal }),
    enabled: Boolean(tenant && user),
    retry: false,
  });
  const items = result.data?.items ?? [];
  const selected = chosen?.id === value ? chosen : undefined;

  return <div className="space-y-2">
    <input type="search" aria-label={`Buscar opções para ${label}`} placeholder="Buscar opções"
      value={search} maxLength={180}
      onChange={event => { setSearch(event.target.value); setOffset(0); }}
      className="h-9 w-full rounded-lg border border-[#D0D5DD] px-2 text-xs" />
    <select id={id} required={required} value={value}
      onChange={event => {
        setChosen(items.find(item => item.id === event.target.value) ?? selected);
        onChange(event.target.value);
      }}
      className="h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-2 text-xs">
      <option value="">Selecionar</option>
      {selected && !items.some(item => item.id === selected.id) &&
        <option value={selected.id}>{selected.name}</option>}
      {items.map(item => <option key={item.id} value={item.id}>
        {item.name === item.code ? item.name : `${item.name} · ${item.code}`}
      </option>)}
    </select>
    {result.isError && <p role="alert" className="text-xs">
      Falha ao carregar opções. <button type="button" className="underline" onClick={() => void result.refetch()}>Tentar novamente</button>
    </p>}
    {!result.isError && <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
      <button type="button" disabled={offset === 0} className="disabled:opacity-40"
        onClick={() => setOffset(offset - 25)}>Anterior</button>
      <span role="status">{result.isLoading ? "Carregando…" : items.length ? `Página ${offset / 25 + 1}` : "Nenhuma opção"}</span>
      <button type="button" disabled={!result.data?.has_more || query !== search.trim()} className="disabled:opacity-40"
        onClick={() => setOffset(offset + 25)}>Próxima</button>
    </div>}
  </div>;
}
