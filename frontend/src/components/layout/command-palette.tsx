"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Search, ArrowRight, X, Users, CreditCard, BriefcaseBusiness, FileClock, Layers } from "@/components/ui/icons";
import { cn } from "@/lib/utils";
import { isUnifiedExperienceEnabled } from "@/lib/experience-rollout";
import { universalSearch } from "@/lib/universal-search-api";
import { mergeSearchResults, type SearchPaletteEntry } from "@/lib/search-providers";
import type { NavigationGroup } from "./navigation";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groups: NavigationGroup[];
  tenantId?: string;
  userId?: string;
  loading?: boolean;
  error?: boolean;
};
const ICONS = {
  students: Users, collections: CreditCard, work: BriefcaseBusiness,
  views: Layers, campaigns: FileClock, navigation: ArrowRight,
} as const;

export function CommandPalette({ open, onOpenChange, groups, tenantId, userId, loading, error }: Props) {
  const router = useRouter();
  const labelId = useId();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const navigating = useRef(false);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selected, setSelected] = useState(0);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedQuery(query.trim()), 180);
    return () => window.clearTimeout(timeout);
  }, [query]);

  const federated = isUnifiedExperienceEnabled(tenantId);
  const searching = debouncedQuery.length >= 2 && debouncedQuery === query.trim();
  const remote = useQuery({
    queryKey: ["universal-search", tenantId, userId, debouncedQuery],
    queryFn: ({ signal }) => universalSearch(debouncedQuery, signal),
    enabled: federated && open && !!tenantId && !!userId && searching && !loading && !error,
    staleTime: 15_000, retry: false,
  });
  const results = useMemo<SearchPaletteEntry[]>(() => mergeSearchResults(
    federated && searching && !remote.isError ? remote.data?.results || [] : [],
    loading || error ? [] : groups,
    query,
  ), [remote.data, remote.isError, federated, searching, loading, error, groups, query]);
  const safeSelected = results.length ? Math.min(selected, results.length - 1) : 0;
  const unavailable = Object.entries(federated ? remote.data?.providers || {} : {})
    .filter(([, value]) => value.status === "unavailable")
    .map(([key]) => key);

  useEffect(() => {
    function shortcuts(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(true);
      } else if (event.key === "Escape" && open) {
        event.preventDefault();
        onOpenChange(false);
      }
    }
    window.addEventListener("keydown", shortcuts);
    return () => window.removeEventListener("keydown", shortcuts);
  }, [onOpenChange, open]);

  useEffect(() => {
    if (!open) return;
    navigating.current = false;
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    setQuery("");
    setDebouncedQuery("");
    setSelected(0);
    requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      document.body.style.overflow = previousOverflow;
      if (!navigating.current) previousFocus.current?.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open || !results.length) return;
    itemRefs.current[safeSelected]?.scrollIntoView({ block: "nearest" });
  }, [safeSelected, open, results.length]);

  function navigate(result: SearchPaletteEntry) {
    // The provider adapter already validated the URL and module, and this
    // control only navigates. It never executes an API mutation silently.
    navigating.current = true;
    onOpenChange(false);
    router.push(result.href);
  }
  function onInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (results.length) setSelected(value => (value + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (results.length) setSelected(value => (value - 1 + results.length) % results.length);
    } else if (event.key === "Enter" && results[safeSelected]) {
      event.preventDefault();
      navigate(results[safeSelected]);
    }
  }
  function trapFocus(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
      'input, button:not(:disabled):not([tabindex="-1"])'
    ) || []);
    if (!controls.length) return;
    if (event.shiftKey && document.activeElement === controls[0]) {
      event.preventDefault(); controls[controls.length - 1].focus();
    } else if (!event.shiftKey && document.activeElement === controls[controls.length - 1]) {
      event.preventDefault(); controls[0].focus();
    }
  }

  if (!open) return null;
  return <div role="presentation"
    className="fixed inset-0 z-[80] flex items-start justify-center px-3 pt-[min(14vh,110px)] sm:px-6">
    <button type="button" aria-label="Fechar busca" tabIndex={-1} onClick={() => onOpenChange(false)}
      className="absolute inset-0 bg-[var(--color-ink)]/35" />
    <section ref={dialogRef} onKeyDown={trapFocus} role="dialog" aria-modal="true" aria-labelledby={labelId}
      className="relative z-10 w-full max-w-[640px] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-canvas)] shadow-[var(--shadow-overlay)]">
      <h2 id={labelId} className="sr-only">Busca universal da MIRA</h2>
      <div className="flex h-14 items-center gap-3 border-b border-[var(--color-border)] px-4">
        <Search className="h-[18px] w-[18px] shrink-0 text-[var(--color-muted)]" aria-hidden="true" />
        <input ref={inputRef} value={query} maxLength={80}
          onChange={event => { setQuery(event.target.value); setSelected(0); }}
          onKeyDown={onInputKeyDown} role="combobox" aria-expanded="true" aria-controls={listId}
          aria-activedescendant={results[safeSelected] ? listId + "-item-" + safeSelected : undefined}
          aria-autocomplete="list" aria-label="Pesquisar registros, atividades, views, campanhas e páginas"
          placeholder={federated ? "Buscar em todo o workspace…" : "Buscar páginas autorizadas…"} autoComplete="off"
          className="h-full min-w-0 flex-1 border-0 bg-transparent text-[length:var(--type-body-compact)] text-[var(--color-ink)] outline-none placeholder:text-[var(--color-muted)]" />
        <kbd className="hidden shrink-0 rounded border border-[var(--color-border)] px-1.5 py-0.5 text-[length:var(--type-caption)] text-[var(--color-muted)] sm:block">
          Esc
        </kbd>
        <button type="button" aria-label="Fechar" onClick={() => onOpenChange(false)}
          className="rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div id={listId} role="listbox" aria-label="Resultados autorizados"
        className="max-h-[min(62vh,490px)] overflow-y-auto p-2">
        {loading ? <p role="status" className="px-3 py-10 text-center text-xs">Carregando permissões…</p>
          : error ? <p role="alert" className="px-3 py-10 text-center text-xs">
            Não foi possível validar as permissões deste workspace.
          </p> : <>
            {results.map((entry, index) => {
              const Icon = ICONS[entry.category];
              return <button key={entry.key} id={listId + "-item-" + index}
                ref={node => { itemRefs.current[index] = node; }}
                role="option" aria-selected={index === safeSelected}
                type="button" onMouseEnter={() => setSelected(index)} onClick={() => navigate(entry)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-[var(--radius-lg)] px-3 py-2.5 text-left text-[length:var(--type-body-compact)] transition-colors duration-[var(--motion-standard)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)] motion-reduce:transition-none",
                  index === safeSelected ? "bg-[var(--color-panel)] text-[var(--color-ink)]" :
                    "text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]"
                )}>
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate font-medium">
                  {entry.title}
                  <span className="block truncate text-[length:var(--type-caption)] font-normal text-[var(--color-muted)]">
                    {entry.detail}
                  </span>
                </span>
                <span className="text-[length:var(--type-caption)] text-[var(--color-muted)]">
                  {entry.categoryLabel}
                </span>
                {index === safeSelected && <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />}
              </button>;
            })}
            {federated && query.trim().length >= 2 && (!searching || remote.isFetching) &&
              <p role="status" className="px-3 py-2 text-xs text-[var(--color-muted)]">
                Buscando em registros, tarefas, views e campanhas…
              </p>}
            {federated && searching && remote.isError &&
              <p role="alert" className="px-3 py-2 text-xs text-[var(--color-red)]">
                A busca de registros está indisponível; páginas autorizadas continuam acessíveis.
              </p>}
            {federated && searching && remote.data?.partial &&
              <p role="status" className="px-3 py-2 text-xs text-[var(--color-slate-600)]">
                Busca parcial: algumas categorias estão temporariamente indisponíveis
                {unavailable.length ? " (" + unavailable.length + ")" : ""}. Outros resultados permanecem acessíveis.
              </p>}
            {!results.length && (!federated || !remote.isFetching) && (!query.trim() || searching) &&
              <p className="px-3 py-10 text-center text-xs text-[var(--color-slate-600)]">
                Nenhum resultado autorizado para esta busca.
              </p>}
          </>}
      </div>
      <div className="flex justify-between gap-2 border-t border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2 text-[length:var(--type-caption)] text-[var(--color-muted)]">
        <span>↑ ↓ selecionar · Enter abrir · Esc fechar</span>
        <span>Somente navegação · Nenhuma ação crítica executada</span>
      </div>
    </section>
  </div>;
}
