"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check, ChevronDown, ChevronRight, Filter, Layers, Plus, RefreshCw, Search, X,
} from "@/components/ui/icons";
import { api } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import {
  createSavedObjectView, deleteSavedObjectView, listSavedObjectViews, updateSavedObjectView,
} from "@/lib/object-index-api";
import { cn } from "@/lib/utils";
import { ObjectDataTable } from "./object-data-table";
import { ObjectFilterBuilder } from "./object-filter-builder";
import type { ObjectDefaultView, ObjectField, ObjectFilter, ObjectKind, ObjectSort, ObjectViewSpec } from "./object-index-types";
import { defaultViewSpec, validateObjectView } from "./object-index-types";
import { matchesObjectFilters } from "./object-index-utils";

export type ObjectIndexState = {
  query: string;
  view: string;
  filters: ObjectFilter[];
  sort: ObjectSort | null;
  columns: string[];
  pageIndex: number;
  pageSize: 25 | 50 | 100;
};
export function initialObjectIndexState<T>(fields: ObjectField<T>[], view = "todos"): ObjectIndexState {
  const spec = defaultViewSpec(fields);
  return { query: "", view, filters: [], sort: null, columns: spec.columns, pageIndex: 0, pageSize: 50 };
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
  partial?: boolean;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  onRefresh?: () => void;
  refreshing?: boolean;
  onOpen?: (row: T) => void;
  actions?: ReactNode;
  emptyTitle?: string;
  extra?: ReactNode;
};

type OpenMenu = "filter" | "sort" | "columns" | "views" | null;

export function ObjectIndex<T extends { id: string }>({
  objectKey, title, description, fields, rows, state, onStateChange,
  defaultViews = [{ id: "todos", title: "Todos" }],
  remote = false, total, partial = false, loading = false, error = false,
  onRetry, onRefresh, refreshing, onOpen, actions, emptyTitle, extra,
}: ObjectIndexProps<T>) {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["org-me"], queryFn: () => api.me(), retry: false, staleTime: 60_000 });
  const userTenant = me.data?.tenant_id;
  const userId = me.data?.user_id;
  const saved = useQuery({
    queryKey: ["object-views", userTenant, userId, objectKey],
    queryFn: () => listSavedObjectViews(objectKey),
    enabled: Boolean(userTenant && userId),
    retry: false, staleTime: 30_000,
  });
  const save = useMutation({
    mutationFn: (payload: { name: string; config: ObjectViewSpec }) => createSavedObjectView(objectKey, payload.name, payload.config),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["object-views", userTenant, userId, objectKey] }); },
  });
  const updateSaved = useMutation({
    mutationFn: (payload: { id: string; name: string; config: ObjectViewSpec }) => updateSavedObjectView(payload.id, payload.name, payload.config),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["object-views", userTenant, userId, objectKey] }); },
  });
  const removeSaved = useMutation({
    mutationFn: deleteSavedObjectView,
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["object-views", userTenant, userId, objectKey] }); },
  });

  const [menu, setMenu] = useState<OpenMenu>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [activeSavedId, setActiveSavedId] = useState<string | null>(null);
  const [viewName, setViewName] = useState("");
  const [editingView, setEditingView] = useState<"new" | "rename" | null>(null);
  const [viewError, setViewError] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const query = useDeferredValue(state.query);
  const fieldMap = useMemo(() => new Map(fields.map(field => [field.key, field])), [fields]);
  const activeSaved = saved.data?.views.find(item => item.id === activeSavedId);
  const visibleFields = useMemo(() => fields.filter(field => field.primary || state.columns.includes(field.key))
    .sort((a,b) => state.columns.indexOf(a.key) - state.columns.indexOf(b.key)), [fields, state.columns]);

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
    if (state.sort) {
      const field = fieldMap.get(state.sort.key);
      if (field?.sortable) {
        result = [...result].sort((a, b) => {
          const aa = field.getValue(a), bb = field.getValue(b);
          if (aa == null && bb == null) return a.id.localeCompare(b.id);
          if (aa == null) return 1;
          if (bb == null) return -1;
          const diff = typeof aa === "number" && typeof bb === "number"
            ? aa - bb : String(aa).localeCompare(String(bb), "pt-BR", { numeric: true });
          return state.sort?.desc ? -diff : diff;
        });
      }
    }
    return result;
  }, [remote, rows, query, state.filters, state.sort, state.view, defaultViews, fields, fieldMap]);

  const count = remote ? (total ?? rows.length) : matches.length;
  const visibleRows = remote ? matches : matches.slice(state.pageIndex * state.pageSize, (state.pageIndex + 1) * state.pageSize);
  const pageCount = Math.max(1, Math.ceil(count / state.pageSize));
  const selectedCount = Object.values(selected).filter(Boolean).length;
  const savedLabel = activeSaved?.name || defaultViews.find(view => view.id === state.view)?.title || "Todos";
  const effectiveViewSpec = validateObjectView(fields, {
    version: 1, filters: state.filters, sort: state.sort, columns: state.columns, page_size: state.pageSize,
  });

  function change(patch: Partial<ObjectIndexState>, resetPage = true) {
    setSelected({});
    onStateChange({ ...state, ...patch, pageIndex: resetPage ? 0 : (patch.pageIndex ?? state.pageIndex) });
  }
  function switchView(id: string, savedId: string | null = null) {
    setMenu(null);
    setSelected({});
    setActiveSavedId(savedId);
    if (!savedId) {
      change({ view: id, query: "", filters: [], sort: null, columns: fields.map(field => field.key) });
      return;
    }
    const view = saved.data?.views.find(item => item.id === savedId);
    if (!view) return;
    const spec = validateObjectView(fields, view.config);
    change({ view: "todos", query: "", filters: spec.filters, sort: spec.sort, columns: spec.columns, pageSize: spec.page_size });
  }
  function updateColumns(columns: string[]) { change({ columns }); }
  function saveView(action: "new" | "rename") {
    const name = viewName.trim();
    if (name.length < 2) { setViewError("Informe pelo menos 2 caracteres."); return; }
    setViewError("");
    const task = action === "rename" && activeSaved
      ? updateSaved.mutateAsync({ id: activeSaved.id, name, config: effectiveViewSpec })
      : save.mutateAsync({ name, config: effectiveViewSpec });
    void task.then(view => {
      setEditingView(null);
      setViewName("");
      setActiveSavedId(view.id);
      setMenu(null);
      void queryClient.invalidateQueries({ queryKey: ["object-views", userTenant, userId, objectKey] });
    }).catch(e => setViewError(e instanceof Error ? e.message : "Não foi possível salvar."));
  }
  function duplicateView() {
    setViewName(savedLabel + " (cópia)");
    setEditingView("new");
    setMenu(null);
  }
  function deleteView() {
    if (!activeSaved) return;
    if (!window.confirm('Excluir a visualização pessoal "' + activeSaved.name + '"?')) return;
    void removeSaved.mutateAsync(activeSaved.id).then(() => {
      setActiveSavedId(null);
      switchView("todos");
    }).catch(e => setViewError(e instanceof Error ? e.message : "Falha ao excluir."));
  }

  useEffect(() => {
    function keydown(event: KeyboardEvent) { if (event.key === "Escape") { setMenu(null); setEditingView(null); } }
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
          <h1 className="truncate text-[18px] font-semibold tracking-[-0.025em]">{title}</h1>
          {!loading && typeof total === "number" && <span className="text-[11px] tabular-nums text-[var(--color-muted)]">
            {total.toLocaleString("pt-BR")}
          </span>}
        </div>
        {description && <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">{description}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {actions}
        {onRefresh && <button type="button" onClick={onRefresh} disabled={refreshing}
          aria-label="Atualizar registros"
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-3 text-[12px] font-medium text-[var(--color-ink)] hover:bg-[var(--color-panel)] disabled:opacity-50">
          <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} /> Atualizar
        </button>}
      </div>
    </div>

    <div className="relative border-b border-[var(--color-border)] px-4 sm:px-6">
      <div className="flex min-h-[43px] items-center gap-1 overflow-x-auto">
        {defaultViews.map(view =>
          <button key={view.id} type="button" onClick={() => switchView(view.id)}
            aria-current={!activeSavedId && state.view === view.id ? "page" : undefined}
            className={cn("shrink-0 border-b-2 px-3 py-3 text-[12px] font-medium transition-colors duration-[var(--motion-standard)]",
              !activeSavedId && state.view === view.id ? "border-[var(--color-ink)] text-[var(--color-ink)]" : "border-transparent text-[var(--color-slate-600)] hover:text-[var(--color-ink)]")}>
            {view.title}
          </button>)}
        <div className="relative ml-2">
          <button type="button" aria-expanded={menu === "views"} aria-haspopup="menu"
            onClick={() => setMenu(menu === "views" ? null : "views")}
            className={cn("inline-flex h-8 shrink-0 items-center gap-1.5 rounded-[var(--radius-md)] px-2.5 text-[12px] hover:bg-[var(--color-panel)]",
              activeSavedId ? "font-semibold text-[var(--color-ink)]" : "text-[var(--color-slate-600)]")}>
            {activeSavedId ? savedLabel : "Minhas visualizações"} <ChevronDown className="h-3.5 w-3.5" />
          </button>
          {menu === "views" && <div role="menu" className="absolute left-0 top-[calc(100%+7px)] z-40 w-[260px] rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-2 shadow-[var(--shadow-overlay)]">
            <p className="px-2 py-1 text-[10px] font-semibold uppercase text-[var(--color-muted)]">Pessoais · persistidas</p>
            {saved.isLoading && <p className="px-2 py-2 text-[11px] text-[var(--color-muted)]">Carregando…</p>}
            {saved.isError && <p role="alert" className="px-2 py-2 text-[11px] text-[var(--color-red)]">Não foi possível carregar suas visualizações.</p>}
            {!saved.isLoading && saved.data?.views.length === 0 && <p className="px-2 py-3 text-[11px] text-[var(--color-muted)]">Nenhuma visualização pessoal ainda.</p>}
            {saved.data?.views.map(view => <button key={view.id} type="button" role="menuitem"
              onClick={() => switchView(view.id, view.id)}
              className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-[12px] hover:bg-[var(--color-panel)]">
              <span className="truncate">{view.name}</span>
              {view.id === activeSavedId && <Check className="h-3.5 w-3.5 text-[var(--color-blue)]" />}
            </button>)}
            <div className="my-1 border-t border-[var(--color-border)]" />
            <button type="button" role="menuitem" onClick={() => { setMenu(null); setEditingView("new"); setViewName(""); }}
              className="flex w-full items-center gap-1.5 rounded-md px-2 py-2 text-left text-[12px] hover:bg-[var(--color-panel)]">
              <Plus className="h-3.5 w-3.5" /> Salvar visualização atual
            </button>
            {activeSaved && <>
              <button type="button" role="menuitem" onClick={() => {
                void updateSaved.mutateAsync({ id: activeSaved.id, name: activeSaved.name, config: effectiveViewSpec }).then(
                  () => { setMenu(null); void queryClient.invalidateQueries({ queryKey: ["object-views", userTenant, userId, objectKey] }); }
                ).catch(e => setViewError(e instanceof Error ? e.message : "Falha ao atualizar."));
              }} className="w-full rounded-md px-2 py-2 text-left text-[12px] hover:bg-[var(--color-panel)]">Atualizar configuração</button>
              <button type="button" role="menuitem" onClick={() => { setEditingView("rename"); setViewName(activeSaved.name); setMenu(null); }}
                className="w-full rounded-md px-2 py-2 text-left text-[12px] hover:bg-[var(--color-panel)]">Renomear</button>
              <button type="button" role="menuitem" onClick={duplicateView}
                className="w-full rounded-md px-2 py-2 text-left text-[12px] hover:bg-[var(--color-panel)]">Duplicar</button>
              <button type="button" role="menuitem" onClick={deleteView}
                className="w-full rounded-md px-2 py-2 text-left text-[12px] text-[var(--color-red)] hover:bg-[var(--color-panel)]">Excluir</button>
            </>}
          </div>}
        </div>
      </div>
    </div>

    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] px-4 py-2.5 sm:px-6">
      <label className="relative flex h-9 min-w-[180px] flex-1 items-center sm:max-w-[340px]">
        <Search className="absolute left-2.5 h-4 w-4 text-[var(--color-muted)]" aria-hidden="true" />
        <input type="search" value={state.query} onChange={event => change({ query: event.target.value })}
          aria-label={"Buscar em " + title}
          placeholder="Buscar registros…"
          className="h-full w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white pl-9 pr-3 text-[12px] outline-none focus:border-[var(--color-blue)] focus:ring-2 focus:ring-[var(--color-blue)]/10" />
      </label>
      <div className="relative">
        <button type="button" aria-expanded={menu === "filter"} onClick={() => setMenu(menu === "filter" ? null : "filter")}
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-2.5 text-[12px] text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]">
          <Filter className="h-3.5 w-3.5" /> Filtrar {state.filters.length ? "(" + state.filters.length + ")" : ""}
        </button>
        {menu === "filter" && <div className="absolute right-0 top-[calc(100%+5px)] z-30 rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-overlay)]">
          <ObjectFilterBuilder fields={fields} filters={state.filters} onChange={next => change({ filters: next })} onClose={() => setMenu(null)} />
        </div>}
      </div>
      <div className="relative">
        <button type="button" aria-expanded={menu === "sort"} onClick={() => setMenu(menu === "sort" ? null : "sort")}
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-2.5 text-[12px] text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]">
          Ordenar <ChevronDown className="h-3 w-3" />
        </button>
        {menu === "sort" && <div className="absolute right-0 top-[calc(100%+5px)] z-30 w-[210px] rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-2 shadow-[var(--shadow-overlay)]">
          <button type="button" onClick={() => { change({ sort: null }); setMenu(null); }} className="w-full px-2 py-1.5 text-left text-[12px] hover:bg-[var(--color-panel)]">Ordem padrão</button>
          {fields.filter(field => field.sortable).map(field => <div key={field.key} className="flex items-center gap-1">
            <span className="min-w-0 flex-1 truncate px-2 text-[12px]">{field.title}</span>
            {([false, true] as const).map(desc => <button key={String(desc)} type="button"
              aria-label={"Ordenar " + field.title + (desc ? " decrescente" : " crescente")}
              onClick={() => { change({ sort: { key: field.key, desc } }); setMenu(null); }}
              className={cn("rounded-md px-1.5 py-1 text-[11px] hover:bg-[var(--color-panel)]", state.sort?.key === field.key && state.sort.desc === desc && "bg-[var(--color-blue-tint)] text-[var(--color-blue)]")}>
              {desc ? "↓" : "↑"}
            </button>)}
          </div>)}
        </div>}
      </div>
      <div className="relative">
        <button type="button" aria-expanded={menu === "columns"} onClick={() => setMenu(menu === "columns" ? null : "columns")}
          className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-2.5 text-[12px] text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]">
          Propriedades <ChevronDown className="h-3 w-3" />
        </button>
        {menu === "columns" && <div className="absolute right-0 top-[calc(100%+5px)] z-30 w-[280px] rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-2 shadow-[var(--shadow-overlay)]">
          <p className="px-2 py-1.5 text-[11px] font-semibold">Colunas disponíveis</p>
          {fields.map(field => <div key={field.key} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-[var(--color-panel)]">
            <label className="flex min-w-0 flex-1 items-center gap-2 text-[12px]">
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
              }} className="rounded px-1 text-[11px] text-[var(--color-muted)] hover:bg-white disabled:opacity-30">
              {direction === "up" ? "↑" : "↓"}
            </button>)}
          </div>)}
          <button type="button" onClick={() => updateColumns(fields.map(field => field.key))}
            className="mt-2 w-full border-t border-[var(--color-border)] px-2 py-2 text-left text-[12px] text-[var(--color-blue)]">
            Restaurar padrão
          </button>
        </div>}
      </div>
    </div>

    {!!state.filters.length && <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] px-4 py-2 sm:px-6">
      {state.filters.map((filter, index) => <button key={index} type="button"
        aria-label={"Remover filtro " + (fieldMap.get(filter.key)?.title || filter.key)}
        onClick={() => change({ filters: state.filters.filter((_, i) => i !== index) })}
        className="inline-flex items-center gap-1 rounded-[var(--radius-xs)] border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1 text-[11px] text-[var(--color-slate-600)]">
        {fieldMap.get(filter.key)?.title || filter.key}: {filter.op}{filter.value != null ? " " + String(filter.value) : ""} <X className="h-3 w-3" />
      </button>)}
      <button type="button" onClick={() => change({ filters: [] })}
        className="text-[11px] text-[var(--color-blue)] hover:underline">Limpar filtros</button>
    </div>}

    {extra}
    {error ? <div role="alert" className="p-6 text-center">
      <p className="text-[13px] text-[var(--color-red)]">Não foi possível consultar os registros.</p>
      {onRetry && <button type="button" onClick={onRetry} className="mt-2 text-[12px] text-[var(--color-blue)] hover:underline">Tentar novamente</button>}
    </div> : <>
      {partial && <p role="note" className="border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2 text-[11px] text-[var(--color-slate-600)] sm:px-6">
        Prévia limitada: busca, filtros, ordenação e seleção referem-se somente aos {rows.length} registros carregados, não a toda a base.
      </p>}
      {selectedCount > 0 && <div className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-blue-tint)] px-4 py-2 text-[12px] sm:px-6">
        <p className="font-medium text-[var(--color-blue-ink)]">{selectedCount} selecionado(s) nesta página</p>
        <div className="flex items-center gap-2">
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
        sort={state.sort} onSortChange={sort => change({ sort })}
        manualSorting selected={selected} onSelectedChange={setSelected}
        onOpen={onOpen} loading={loading}
        emptyText={emptyTitle || (state.query || state.filters.length ? "Nenhum registro corresponde aos filtros." : "Nenhum registro disponível.")} />
      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--color-border)] px-4 py-3 text-[11px] text-[var(--color-slate-600)] sm:px-6">
        <span className="tabular-nums">{loading ? "Carregando…" : remote
          ? count ? ((state.pageIndex * state.pageSize) + 1) + "–" + ((state.pageIndex * state.pageSize) + visibleRows.length) + " de " + count.toLocaleString("pt-BR") : "0 registros"
          : count + " registro(s)" + (partial ? " na prévia" : "")}</span>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5">
            Por página
            <select aria-label="Registros por página" value={state.pageSize}
              onChange={event => change({ pageSize: Number(event.target.value) as 25 | 50 | 100 })}
              className="h-8 rounded-[var(--radius-md)] border border-[var(--color-border)] px-1.5 text-[11px]">
              <option value={25}>25</option><option value={50}>50</option><option value={100}>100</option>
            </select>
          </label>
          <button type="button" disabled={state.pageIndex === 0 || loading}
            onClick={() => change({ pageIndex: state.pageIndex - 1 }, false)}
            aria-label="Página anterior"
            className="grid h-8 w-8 place-items-center rounded-[var(--radius-md)] border border-[var(--color-border)] disabled:opacity-40">
            <ChevronRight className="h-3.5 w-3.5 rotate-180" />
          </button>
          <span className="tabular-nums">{state.pageIndex + 1} / {pageCount}</span>
          <button type="button" disabled={state.pageIndex + 1 >= pageCount || loading}
            onClick={() => change({ pageIndex: state.pageIndex + 1 }, false)}
            aria-label="Próxima página"
            className="grid h-8 w-8 place-items-center rounded-[var(--radius-md)] border border-[var(--color-border)] disabled:opacity-40">
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </footer>
    </>}

    <Dialog open={Boolean(editingView || viewError)}
      onOpenChange={open => { if (!open) { setEditingView(null); setViewError(""); } }}
      title={editingView === "rename" ? "Renomear visualização" : "Salvar visualização pessoal"}
      description="Uma configuração pessoal, sem armazenar os dados consultados."
      className="max-w-[420px]">
      <form onSubmit={event => { event.preventDefault(); if (editingView) saveView(editingView); }}
        className="space-y-4">
        {editingView && <label className="block text-[12px] text-[var(--color-slate-600)]">Nome
          <input autoFocus value={viewName} maxLength={80} onChange={event => setViewName(event.target.value)}
            className="mt-1 h-10 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 text-[13px] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]" />
        </label>}
        {viewError && <p role="alert" className="text-[12px] text-[var(--color-red)]">{viewError}</p>}
        {editingView && <button type="submit" disabled={save.isPending || updateSaved.isPending}
          className="h-9 w-full rounded-[var(--radius-md)] bg-[var(--color-ink)] px-4 text-[12px] font-medium text-white disabled:opacity-50">
          {save.isPending || updateSaved.isPending ? "Salvando…" : "Salvar"}
        </button>}
      </form>
    </Dialog>
  </section>;
}
