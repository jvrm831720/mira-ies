"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown, ChevronRight, Filter, Layers, RefreshCw, Search, X,
} from "@/components/ui/icons";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ObjectDataTable } from "./object-data-table";
import { ObjectFilterBuilder } from "./object-filter-builder";
import type { ObjectDefaultView, ObjectField, ObjectFilter, ObjectKind, ObjectSort, SavedObjectView } from "./object-index-types";
import { ViewManager } from "./view-manager";
import { defaultViewSpec, validateObjectView } from "./object-index-types";
import { matchesObjectFilters } from "./object-index-utils";
import { activeSorts, pageSelection, sortObjectRows, verifiedCount } from "./object-index-experience";

export type ObjectIndexState = {
  query: string;
  view: string;
  filters: ObjectFilter[];
  sort: ObjectSort | null;
  savedViewId?: string | null;
  propertyLabels?: Record<string, string>;
  sorts?: ObjectSort[];
  density?: "compact" | "comfortable";
  pinned?: string[];
  columnWidths?: Record<string, number>;
  columns: string[];
  pageIndex: number;
  pageSize: 25 | 50 | 100;
};
export function initialObjectIndexState<T>(fields: ObjectField<T>[], view = "todos"): ObjectIndexState {
  const spec = defaultViewSpec(fields);
  return { query: "", view, savedViewId: null, propertyLabels: {}, filters: [], sort: null, sorts: [], density: "comfortable", pinned: [], columnWidths: {}, columns: spec.columns, pageIndex: 0, pageSize: 50 };
}

export type ObjectIndexProps<T extends { id: string }> = {
  objectKey: ObjectKind;
  title: string;
  description?: string;
  fields: ObjectField<T>[];
  rows: T[];
  state: ObjectIndexState;
  onStateChange: (next: ObjectIndexState) => void;
  defaultViews?: ObjectDefaultView[];
  remote?: boolean;
  total?: number;
  hasMore?: boolean;
  partial?: boolean;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  onRefresh?: () => void;
  refreshing?: boolean;
  onOpen?: (row: T) => void;
  actions?: ReactNode;
  emptyTitle?: string;
  emptyAction?: ReactNode;
  selectionActions?: (selectedRows: T[]) => ReactNode;
  extra?: ReactNode;
};

type OpenMenu = "filter" | "sort" | "columns" | null;

export function ObjectIndex<T extends { id: string }>({
  objectKey, title, description, fields, rows, state, onStateChange,
  defaultViews = [{ id: "todos", title: "Todos" }],
  remote = false, total, hasMore, partial = false, loading = false, error = false,
  onRetry, onRefresh, refreshing, onOpen, actions, emptyTitle, emptyAction, selectionActions, extra,
}: ObjectIndexProps<T>) {
  const me = useQuery({ queryKey: ["org-me"], queryFn: () => api.me(), retry: false, staleTime: 60_000 });
  const userTenant = me.data?.tenant_id;
  const userId = me.data?.user_id;
  const [menu, setMenu] = useState<OpenMenu>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const menuRef = useRef<HTMLDivElement>(null);
  const query = useDeferredValue(state.query);
  const fieldMap = useMemo(() => new Map(fields.map(field => [field.key, field])), [fields]);
  const sorts = activeSorts(state);
  const density = state.density === "compact" ? "compact" : "comfortable";
  const pinned = (state.pinned || []).filter(key => state.columns.includes(key) && fields.some(field => field.key === key));
  const widths = state.columnWidths || {};
  const effectiveFields = useMemo(() => fields.map(field => {
    const label = state.propertyLabels?.[field.key];
    return label && label.trim().length >= 2 ? { ...field, title: label } : field;
  }), [fields, state.propertyLabels]);
  const visibleFields = useMemo(() => effectiveFields.filter(field => field.primary || state.columns.includes(field.key))
    .sort((a,b) => state.columns.indexOf(a.key) - state.columns.indexOf(b.key)), [effectiveFields, state.columns]);

  const matches = useMemo(() => {
    if (remote) return rows;
    const viewFilter = defaultViews.find(view => view.id === state.view)?.filterKey;
    let result = rows.filter(row => {
      const matchesView = !viewFilter || (() => {
        const [key, expected] = viewFilter.split(":");
        const field = fieldMap.get(key);
        return field != null && String(field.getValue(row)) === expected;
      })();
      const q = query.trim().toLocaleLowerCase("pt-BR");
      return matchesView && (!q || fields.some(field => {
        const val = field.getValue(row);
        return val != null && String(val).toLocaleLowerCase("pt-BR").includes(q);
      })) && matchesObjectFilters(row, fields, state.filters);
    });
    result = sortObjectRows(result, fields, activeSorts(state));
    return result;
  }, [remote, rows, query, state.filters, state.sort, state.sorts, state.view, defaultViews, fields, fieldMap]);

  const exactTotal = remote ? verifiedCount(true, partial, total) : matches.length;
  const visibleRows = remote ? matches : matches.slice(state.pageIndex * state.pageSize, (state.pageIndex + 1) * state.pageSize);
  const pageCount = exactTotal == null ? null : Math.max(1, Math.ceil(exactTotal / state.pageSize));
  const selectedRows = pageSelection(visibleRows, selected);
  const selectedCount = selectedRows.length;
  const effectiveViewSpec = validateObjectView(fields, {
    version: 1, filters: state.filters, sort: sorts[0] || null, sorts,
    density, pinned, columnWidths: widths, columns: state.columns, page_size: state.pageSize,
    property_labels: state.propertyLabels || {},
  });

  function change(patch: Partial<ObjectIndexState>, resetPage = true) {
    if (resetPage || patch.pageIndex !== undefined || patch.pageSize !== undefined) setSelected({});
    onStateChange({ ...state, ...patch, pageIndex: resetPage ? 0 : (patch.pageIndex ?? state.pageIndex) });
  }
  function changeSorts(next: ObjectSort[]) {
    change({ sort: next[0] || null, sorts: next.slice(0, 3) });
  }
  function switchView(id: string) {
    setMenu(null);
    change({
      view: id, savedViewId: null, propertyLabels: {}, query: "", filters: [],
      sort: null, sorts: [], columns: fields.map(field => field.key),
    });
  }
  function applySavedView(view: SavedObjectView) {
    if (!view.config || view.schema_status === "unsupported") return;
    const spec = validateObjectView(fields, view.config);
    setMenu(null);
    change({
      savedViewId: view.id, view: "todos", query: "", filters: spec.filters,
      sort: spec.sort, sorts: spec.sorts || (spec.sort ? [spec.sort] : []),
      density: spec.density || "comfortable", pinned: spec.pinned || [],
      columnWidths: spec.columnWidths || {}, columns: spec.columns,
      propertyLabels: spec.property_labels || {}, pageSize: spec.page_size,
    });
  }
  function updateColumns(columns: string[]) { change({ columns, pinned: pinned.filter(key => columns.includes(key)) }, false); }
  function updatePresentation(patch: Partial<ObjectIndexState>) { change(patch, false); }

  // Never retain a previous page or workspace selection, even when record IDs overlap.
  useEffect(() => { setSelected({}); }, [objectKey, userTenant, userId, state.pageIndex, state.pageSize,
    state.query, state.view, state.savedViewId, state.filters, state.sort, state.sorts]);

  useEffect(() => {
    function keydown(event: KeyboardEvent) { if (event.key === "Escape") setMenu(null); }
    function click(event: MouseEvent) { if (!menuRef.current?.contains(event.target as Node)) setMenu(null); }
    document.addEventListener("keydown", keydown);
    document.addEventListener("mousedown", click);
    return () => { document.removeEventListener("keydown", keydown); document.removeEventListener("mousedown", click); };
  }, []);

  return <section ref={menuRef} className="mira-page min-w-0 bg-[var(--color-canvas)] text-[var(--color-ink)]">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-4 sm:px-6">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <Layers className="h-[18px] w-[18px] text-[var(--color-slate-600)]" aria-hidden="true" />
          <h1 className="truncate text-lg font-semibold tracking-[-0.025em]">{title}</h1>
          {!loading && !partial && exactTotal !== null && <span className="text-[length:var(--type-caption)] tabular-nums text-[var(--color-muted)]">
            {exactTotal?.toLocaleString("pt-BR")}
          </span>}
        </div>
        {description && <p className="mt-1 text-xs text-[var(--color-slate-600)]">{description}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {actions}
        {onRefresh && <button type="button" onClick={onRefresh} disabled={refreshing}
          aria-label="Atualizar registros"
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-3 text-xs font-medium text-[var(--color-ink)] hover:bg-[var(--color-panel)] disabled:opacity-50">
          <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} /> Atualizar
        </button>}
      </div>
    </div>

    <div className="relative border-b border-[var(--color-border)] px-4 sm:px-6">
      <div className="flex min-h-[43px] items-center gap-1 overflow-x-auto">
        {defaultViews.map(view =>
          <button key={view.id} type="button" onClick={() => switchView(view.id)}
            aria-current={!state.savedViewId && state.view === view.id ? "page" : undefined}
            className={cn("shrink-0 border-b-2 px-3 py-3 text-xs font-medium transition-colors duration-[var(--motion-standard)]",
              !state.savedViewId && state.view === view.id ? "border-[var(--color-ink)] text-[var(--color-ink)]" : "border-transparent text-[var(--color-slate-600)] hover:text-[var(--color-ink)]")}>
            {view.title}
          </button>)}
        <ViewManager objectKey={objectKey} fields={fields} tenantId={userTenant} userId={userId}
          activeId={state.savedViewId} currentConfig={effectiveViewSpec} onApply={applySavedView} />
      </div>
    </div>

    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] px-4 py-2.5 sm:px-6">
      <label className="relative flex h-9 min-w-[180px] flex-1 items-center sm:max-w-[340px]">
        <Search className="absolute left-2.5 h-4 w-4 text-[var(--color-muted)]" aria-hidden="true" />
        <input type="search" value={state.query} onChange={event => change({ query: event.target.value })}
          aria-label={"Buscar em " + title}
          placeholder="Buscar registros…"
          className="h-full w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white pl-9 pr-3 text-xs outline-none focus:border-[var(--color-blue)] focus:ring-2 focus:ring-[var(--color-blue)]/10" />
      </label>
      <div className="relative">
        <button type="button" aria-expanded={menu === "filter"} onClick={() => setMenu(menu === "filter" ? null : "filter")}
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-2.5 text-xs text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]">
          <Filter className="h-3.5 w-3.5" /> Filtrar {state.filters.length ? "(" + state.filters.length + ")" : ""}
        </button>
        {menu === "filter" && <div className="absolute right-0 top-[calc(100%+5px)] z-30 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-overlay)]">
          <ObjectFilterBuilder fields={effectiveFields} filters={state.filters} onChange={next => change({ filters: next })} onClose={() => setMenu(null)} />
        </div>}
      </div>
      <div className="relative">
        <button type="button" aria-expanded={menu === "sort"} onClick={() => setMenu(menu === "sort" ? null : "sort")}
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-2.5 text-xs text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]">
          Ordenar <ChevronDown className="h-3 w-3" />
        </button>
        {menu === "sort" && <div role="group" aria-label="Ordenações aplicadas"
          className="absolute right-0 top-[calc(100%+5px)] z-30 w-[285px] rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-3 shadow-[var(--shadow-overlay)]">
          <p className="mb-2 text-xs font-semibold">Ordenação múltipla</p>
          {sorts.length === 0 && <p className="mb-2 text-xs text-[var(--color-muted)]">Ordem padrão do servidor</p>}
          {sorts.map((item, index) => <div key={item.key} className="mb-2 flex items-center gap-2">
            <span className="w-4 shrink-0 text-[length:var(--type-overline)] tabular-nums text-[var(--color-muted)]">{index + 1}</span>
            <span className="min-w-0 flex-1 truncate text-xs">{fields.find(field => field.key === item.key)?.title || item.key}</span>
            <button type="button" aria-label={"Inverter " + item.key} className="rounded border px-2 py-1 text-xs"
              onClick={() => changeSorts(sorts.map(sort => sort.key === item.key ? { ...sort, desc: !sort.desc } : sort))}>
              {item.desc ? "↓" : "↑"}
            </button>
            <button type="button" aria-label={"Remover " + item.key} className="rounded px-1 text-[var(--color-muted)]"
              onClick={() => changeSorts(sorts.filter(sort => sort.key !== item.key))}><X className="h-3 w-3" /></button>
          </div>)}
          <label className="block text-xs text-[var(--color-muted)]">Adicionar critério (até 3)
            <select aria-label="Adicionar ordenação" value="" disabled={sorts.length >= 3}
              onChange={event => {
                const value = event.target.value;
                if (value && !sorts.some(sort => sort.key === value)) changeSorts([...sorts, { key: value, desc: false }]);
              }} className="mt-1 h-9 w-full rounded border border-[var(--color-border)] bg-white px-2 text-xs">
              <option value="">Selecionar coluna…</option>
              {fields.filter(field => field.sortable && !sorts.some(sort => sort.key === field.key))
                .map(field => <option key={field.key} value={field.key}>{field.title}</option>)}
            </select>
          </label>
          <div className="mt-2 flex justify-between">
            <button type="button" className="text-xs text-[var(--color-slate-600)] hover:underline"
              onClick={() => changeSorts([])}>Limpar ordenações</button>
            <button type="button" className="text-xs font-semibold text-[var(--color-blue)]"
              onClick={() => setMenu(null)}>Concluir</button>
          </div>
        </div>}
      </div>
      <label className="flex h-9 items-center gap-1.5 text-xs text-[var(--color-slate-600)]">
        Densidade
        <select value={density} aria-label="Densidade da tabela" onChange={event =>
          updatePresentation({ density: event.target.value as "compact" | "comfortable" })}
          className="h-9 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-2 text-xs">
          <option value="comfortable">Confortável</option>
          <option value="compact">Compacta</option>
        </select>
      </label>
      <div className="relative">
        <button type="button" aria-expanded={menu === "columns"} onClick={() => setMenu(menu === "columns" ? null : "columns")}
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-2.5 text-xs text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]">
          Propriedades <ChevronDown className="h-3 w-3" />
        </button>
        {menu === "columns" && <div className="absolute right-0 top-[calc(100%+5px)] z-30 w-[280px] rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-2 shadow-[var(--shadow-overlay)]">
          <p className="px-2 py-1.5 text-[length:var(--type-caption)] font-semibold">Colunas disponíveis</p>
          {fields.map(field => <div key={field.key} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-[var(--color-panel)]">
            <label className="flex min-w-0 flex-1 items-center gap-2 text-xs">
              <input type="checkbox" checked={field.primary || state.columns.includes(field.key)}
                disabled={field.primary} onChange={event => {
                  const next = event.target.checked ? [...state.columns, field.key]
                    : state.columns.filter(key => key !== field.key);
                  updateColumns(next);
                }} className="h-3.5 w-3.5 accent-[var(--color-blue)]" />
              <span className="truncate">{field.title}</span>
            </label>
            {!field.primary && ["up", "down"].map(direction => <button type="button" key={direction}
              aria-label={"Mover " + field.title + " " + (direction === "up" ? "para cima" : "para baixo")}
              disabled={!state.columns.includes(field.key)}
              onClick={() => {
                const next = [...state.columns];
                const i = next.indexOf(field.key), j = i + (direction === "up" ? -1 : 1);
                if (i < 0 || j < 0 || j >= next.length || fieldMap.get(next[j])?.primary) return;
                [next[i], next[j]] = [next[j], next[i]];
                updateColumns(next);
              }} className="rounded px-1 text-[length:var(--type-caption)] text-[var(--color-muted)] hover:bg-white disabled:opacity-30">
              {direction === "up" ? "↑" : "↓"}
            </button>)}
          </div>)}
          <button type="button" onClick={() => updateColumns(fields.map(field => field.key))}
            className="mt-2 w-full border-t border-[var(--color-border)] px-2 py-2 text-left text-xs text-[var(--color-blue)]">
            Restaurar padrão
          </button>
        </div>}
      </div>
    </div>

    {!!state.filters.length && <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] px-4 py-2 sm:px-6">
      {state.filters.map((filter, index) => <button key={index} type="button"
        aria-label={"Remover filtro " + (fieldMap.get(filter.key)?.title || filter.key)}
        onClick={() => change({ filters: state.filters.filter((_, i) => i !== index) })}
        className="inline-flex items-center gap-1 rounded-[var(--radius-xs)] border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1 text-[length:var(--type-caption)] text-[var(--color-slate-600)]">
        {fieldMap.get(filter.key)?.title || filter.key}: {filter.op}{filter.value != null ? " " + String(filter.value) : ""} <X className="h-3 w-3" />
      </button>)}
      <button type="button" onClick={() => change({ filters: [] })}
        className="text-[length:var(--type-caption)] text-[var(--color-blue)] hover:underline">Limpar filtros</button>
    </div>}

    {extra}
    {error ? <div role="alert" className="p-6 text-center">
      <p className="text-[length:var(--type-body-compact)] text-[var(--color-red)]">Não foi possível consultar os registros.</p>
      {onRetry && <button type="button" onClick={onRetry} className="mt-2 text-xs text-[var(--color-blue)] hover:underline">Tentar novamente</button>}
    </div> : <>
      {partial && <p role="note" className="border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2 text-[length:var(--type-caption)] text-[var(--color-slate-600)] sm:px-6">
        Prévia limitada: busca, filtros, ordenação e seleção referem-se somente aos {rows.length} registros carregados, não a toda a base.
      </p>}
      {selectedCount > 0 && <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] bg-[var(--color-blue-tint)] px-4 py-2 text-xs sm:px-6">
        <p className="font-medium text-[var(--color-blue-ink)]">{selectedCount} selecionado(s) nesta página</p>
        <div className="flex items-center gap-2">
          {selectionActions?.(selectedRows)}
          {selectedCount === 1 && onOpen && <button type="button" onClick={() => {
            const item = visibleRows.find(row => selected[row.id]);
            if (item) onOpen(item);
          }} className="font-semibold text-[var(--color-blue-ink)] hover:underline">Abrir registro</button>}
          <button type="button" onClick={() => setSelected({})} className="flex items-center gap-1 text-[var(--color-blue-ink)] hover:underline">
            <X className="h-3 w-3" /> Limpar
          </button>
        </div>
      </div>}
      <ObjectDataTable records={visibleRows} fields={visibleFields}
        visible={state.columns} onVisibleChange={updateColumns}
        sorts={sorts} onSortsChange={changeSorts}
        density={density} pinned={pinned} onPinnedChange={next => updatePresentation({ pinned: next })}
        columnWidths={widths} onWidthsChange={next => updatePresentation({ columnWidths: next })}
        selected={selected} onSelectedChange={setSelected}
        onOpen={onOpen} loading={loading}
        emptyText={emptyTitle || (state.query || state.filters.length ? "Nenhum registro corresponde aos filtros." : "Nenhum registro disponível.")}
        emptyAction={emptyAction} />
      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--color-border)] px-4 py-3 text-[length:var(--type-caption)] text-[var(--color-slate-600)] sm:px-6">
        <span className="tabular-nums">{loading ? "Carregando…" : remote
          ? exactTotal === null
            ? visibleRows.length + " registros nesta página · total não verificado"
            : exactTotal > 0
              ? ((state.pageIndex * state.pageSize) + 1) + "–" + ((state.pageIndex * state.pageSize) + visibleRows.length) + " de " + exactTotal.toLocaleString("pt-BR")
              : "0 registros"
          : matches.length + " registro(s)" + (partial ? " na prévia" : "")}</span>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5">
            Por página
            <select aria-label="Registros por página" value={state.pageSize}
              onChange={event => change({ pageSize: Number(event.target.value) as 25 | 50 | 100 })}
              className="h-8 rounded-[var(--radius-md)] border border-[var(--color-border)] px-1.5 text-[length:var(--type-caption)]">
              <option value={25}>25</option><option value={50}>50</option><option value={100}>100</option>
            </select>
          </label>
          <button type="button" disabled={state.pageIndex === 0 || loading}
            onClick={() => change({ pageIndex: state.pageIndex - 1 }, false)}
            aria-label="Página anterior"
            className="grid h-8 w-8 place-items-center rounded-[var(--radius-md)] border border-[var(--color-border)] disabled:opacity-40">
            <ChevronRight className="h-3.5 w-3.5 rotate-180" />
          </button>
          <span className="tabular-nums">{state.pageIndex + 1}{pageCount === null ? "" : " / " + pageCount}</span>
          <button type="button" disabled={loading || (pageCount === null ? hasMore !== true : state.pageIndex + 1 >= pageCount)}
            onClick={() => change({ pageIndex: state.pageIndex + 1 }, false)}
            aria-label="Próxima página"
            className="grid h-8 w-8 place-items-center rounded-[var(--radius-md)] border border-[var(--color-border)] disabled:opacity-40">
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </footer>
    </>}


  </section>;
}
