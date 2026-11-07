"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  ArrowRight, BriefcaseBusiness, CreditCard, FileClock, Layers, Search, Users, X,
} from "@/components/ui/icons";
import type { LucideIcon } from "@/components/ui/icons";
import { searchUniversal, type SearchProvider } from "@/lib/universal-search-api";
import { safeSearchDestination } from "@/lib/search-destinations";
import { cn } from "@/lib/utils";
import { searchNavigation, type NavigationGroup } from "./navigation";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groups: NavigationGroup[];
  tenantId?: string;
  userId?: string | null;
  loading?: boolean;
  error?: boolean;
};
type Command = {
  id: string; href: string; label: string; category: string;
  icon: LucideIcon; detail?: string; provider?: SearchProvider; approximate?: boolean;
};

const PROVIDERS: Record<SearchProvider, {
  category: string; icon: LucideIcon; root: string | null;
}> = {
  students: { category: "Aluno", icon: Users, root: "/alunos" },
  collections: { category: "Caso financeiro", icon: CreditCard, root: "/cobranca" },
  work: { category: "Trabalho humano", icon: BriefcaseBusiness, root: "/trabalho" },
  views: { category: "Visualização salva", icon: Layers, root: null },
  campaigns: { category: "Campanha de permanência", icon: FileClock, root: "/campanhas" },
};
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

  const trimmed = query.trim();
  const allowedRoots = useMemo(() =>
    [...new Set(groups.flatMap(group => group.items.map(item => item.href)))],
  [groups]);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedQuery(query.trim()), 200);
    return () => window.clearTimeout(timeout);
  }, [query]);

  const federated = useQuery({
    queryKey: ["federated-search", tenantId, userId, debouncedQuery],
    queryFn: ({ signal }) => searchUniversal(debouncedQuery, signal),
    enabled: open && Boolean(tenantId && userId) && !loading && !error &&
      debouncedQuery.length >= 2 && debouncedQuery.length <= 80,
    retry: false, staleTime: 15_000,
  });

  const serverCurrent = debouncedQuery === trimmed && trimmed.length >= 2;
  const results = useMemo<Command[]>(() => {
    const navigation: Command[] = searchNavigation(groups, query).map(item => ({
      id: "nav:" + item.href, href: item.href, label: item.label,
      category: item.category, icon: item.icon,
    }));
    const remote: Command[] = serverCurrent
      ? (federated.data?.results || [])
        .filter(item => safeSearchDestination(item, allowedRoots))
        .map(item => ({
          id: item.provider + ":" + item.id,
          href: item.href, label: item.title, category: PROVIDERS[item.provider].category,
          icon: PROVIDERS[item.provider].icon, detail: item.subtitle,
          provider: item.provider, approximate: item.match === "approximate",
        }))
      : [];
    const distinct = new Map<string, Command>();
    // Never dedupe two different campaigns merely because both open /campanhas.
    for (const item of [...remote, ...navigation]) {
      if (!distinct.has(item.id)) distinct.set(item.id, item);
    }
    return [...distinct.values()].slice(0, 40);
  }, [groups, query, serverCurrent, federated.data, allowedRoots]);
  const safeSelected = results.length ? Math.min(selected, results.length - 1) : 0;

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
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    setQuery("");
    setDebouncedQuery("");
    setSelected(0);
    requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      document.body.style.overflow = oldOverflow;
      if (!navigating.current) previousFocus.current?.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open || !results.length) return;
    itemRefs.current[safeSelected]?.scrollIntoView({ block: "nearest" });
  }, [safeSelected, open, results.length]);

  function navigate(href: string) {
    // Only navigation: no action execution, side-effect API or confirmation bypass.
    navigating.current = true;
    onOpenChange(false);
    router.push(href);
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
      navigate(results[safeSelected].href);
    }
  }
  function trapFocus(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
      'input, button:not(:disabled):not([tabindex="-1"])',
    ) || []);
    if (!controls.length) return;
    if (event.shiftKey && document.activeElement === controls[0]) {
      event.preventDefault();
      controls[controls.length - 1].focus();
    } else if (!event.shiftKey && document.activeElement === controls[controls.length - 1]) {
      event.preventDefault();
      controls[0].focus();
    }
  }
  if (!open) return null;
  return <div role="presentation" className="fixed inset-0 z-[80] flex items-start justify-center px-3 pt-[min(14vh,110px)] sm:px-6">
    <button type="button" aria-label="Fechar busca" tabIndex={-1} onClick={() => onOpenChange(false)}
      className="absolute inset-0 bg-[var(--color-ink)]/35" />
    <section ref={dialogRef} onKeyDown={trapFocus} role="dialog" aria-modal="true" aria-labelledby={labelId}
      className="relative z-10 w-full max-w-[620px] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-canvas)] shadow-[var(--shadow-overlay)]">
      <h2 id={labelId} className="sr-only">Busca universal da MIRA</h2>
      <div className="flex h-14 items-center gap-3 border-b border-[var(--color-border)] px-4">
        <Search className="h-[18px] w-[18px] shrink-0 text-[var(--color-muted)]" aria-hidden="true" />
        <input ref={inputRef} value={query}
          onChange={event => { setQuery(event.target.value); setSelected(0); }}
          onKeyDown={onInputKeyDown} role="combobox" aria-expanded="true" aria-controls={listId}
          aria-activedescendant={results[safeSelected] ? listId + "-item-" + safeSelected : undefined}
          aria-autocomplete="list" aria-label="Buscar registros, atividades, views, campanhas e páginas"
          placeholder="Buscar em todo o workspace…" maxLength={80} autoComplete="off"
          className="h-full min-w-0 flex-1 border-0 bg-transparent text-[length:var(--type-body-compact)] text-[var(--color-ink)] outline-none placeholder:text-[var(--color-muted)]" />
        <button type="button" aria-label="Fechar" onClick={() => onOpenChange(false)}
          className="rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]"><X className="h-4 w-4" /></button>
      </div>
      <div id={listId} role="listbox" aria-label="Resultados autorizados" aria-busy={serverCurrent && federated.isFetching}
        className="max-h-[min(60vh,450px)] overflow-y-auto p-2">
        {loading ? <p role="status" className="px-3 py-10 text-center text-xs">Carregando permissões…</p> :
          error ? <p role="alert" className="px-3 py-10 text-center text-xs">Não foi possível verificar suas permissões.</p> : <>
            {results.map((item, index) => {
              const Icon = item.icon;
              return <button key={item.id} id={listId + "-item-" + index}
                ref={node => { itemRefs.current[index] = node; }}
                role="option" aria-selected={index === safeSelected} type="button"
                onMouseEnter={() => setSelected(index)} onClick={() => navigate(item.href)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-[var(--radius-lg)] px-3 py-2.5 text-left text-[length:var(--type-body-compact)] transition-colors duration-[var(--motion-standard)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)] motion-reduce:transition-none",
                  index === safeSelected ? "bg-[var(--color-panel)] text-[var(--color-ink)]" :
                    "text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]",
                )}>
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate font-medium">
                  {item.label}
                  {item.detail && <span className="block truncate text-[length:var(--type-caption)] font-normal text-[var(--color-muted)]">
                    {item.detail}{item.approximate ? " · Aproximação" : ""}
                  </span>}
                </span>
                <span className="shrink-0 text-[length:var(--type-caption)] text-[var(--color-muted)]">{item.category}</span>
                {index === safeSelected && <ArrowRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              </button>;
            })}
            {serverCurrent && federated.isFetching &&
              <p role="status" className="px-3 py-2 text-xs text-[var(--color-muted)]">
                Pesquisando fontes autorizadas…
              </p>}
            {serverCurrent && federated.isError &&
              <p role="alert" className="px-3 py-2 text-xs text-[var(--color-red)]">
                A busca federada está indisponível. A navegação permanece acessível.
                <button type="button" className="ml-2 font-semibold underline"
                  onClick={() => void federated.refetch()}>Tentar novamente</button>
              </p>}
            {serverCurrent && federated.data?.partial &&
              <p role="status" className="px-3 py-2 text-xs text-[var(--color-muted)]">
                Alguns provedores não responderam. Os resultados exibidos são parciais;
                nenhum total global foi calculado.
              </p>}
            {!results.length && !federated.isFetching && <p className="px-3 py-10 text-center text-xs text-[var(--color-slate-600)]">
              Nenhum resultado autorizado nesta busca.
            </p>}
          </>}
      </div>
      <footer className="flex flex-wrap justify-between gap-2 border-t border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2 text-[length:var(--type-caption)] text-[var(--color-muted)]">
        <span>↑ ↓ selecionar · Enter abrir · Esc fechar</span>
        <span>Somente navegação · Fontes limitadas por segurança</span>
      </footer>
    </section>
  </div>;
}
