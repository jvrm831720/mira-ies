"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, ArrowRight, X } from "@/components/ui/icons";
import { cn } from "@/lib/utils";
import { searchNavigation, type NavigationGroup } from "./navigation";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groups: NavigationGroup[];
  loading?: boolean;
  error?: boolean;
};

export function CommandPalette({ open, onOpenChange, groups, loading, error }: Props) {
  const router = useRouter();
  const labelId = useId();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const results = useMemo(() => searchNavigation(groups, query), [groups, query]);
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
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    setQuery("");
    setSelected(0);
    requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      document.body.style.overflow = oldOverflow;
      previousFocus.current?.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open || !results.length) return;
    itemRefs.current[safeSelected]?.scrollIntoView({ block: "nearest" });
  }, [safeSelected, open, results.length]);

  function navigate(href: string) {
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
    } else if (event.key === "Tab") {
      // Keep focus inside the active modal without adding an inert hidden control.
      event.preventDefault();
    }
  }

  if (!open) return null;

  return (
    <div role="presentation" className="fixed inset-0 z-[80] flex items-start justify-center px-3 pt-[min(14vh,110px)] sm:px-6">
      <button type="button" aria-label="Fechar busca" tabIndex={-1}
        onClick={() => onOpenChange(false)}
        className="absolute inset-0 bg-[var(--color-ink)]/35" />
      <section role="dialog" aria-modal="true" aria-labelledby={labelId}
        className="relative z-10 w-full max-w-[600px] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-canvas)] shadow-[var(--shadow-overlay)]">
        <h2 id={labelId} className="sr-only">Busca e navegação da MIRA</h2>
        <div className="flex h-14 items-center gap-3 border-b border-[var(--color-border)] px-4">
          <Search className="h-[18px] w-[18px] shrink-0 text-[var(--color-muted)]" aria-hidden="true" />
          <input ref={inputRef} value={query} onChange={event => { setQuery(event.target.value); setSelected(0); }}
            onKeyDown={onInputKeyDown}
            role="combobox" aria-expanded="true" aria-controls={listId}
            aria-activedescendant={results[safeSelected] ? listId + "-item-" + safeSelected : undefined}
            aria-autocomplete="list" aria-label="Buscar páginas autorizadas"
            placeholder="Buscar páginas e módulos…" autoComplete="off"
            className="h-full min-w-0 flex-1 border-0 bg-transparent text-[13px] text-[var(--color-ink)] outline-none placeholder:text-[var(--color-muted)]" />
          <button type="button" onClick={() => onOpenChange(false)} aria-label="Fechar"
            className="rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div id={listId} role="listbox" aria-label="Páginas disponíveis"
          className="max-h-[min(58vh,430px)] overflow-y-auto p-2">
          {loading ? <p role="status" className="px-3 py-10 text-center text-[13px] text-[var(--color-slate-600)]">Carregando navegação…</p>
          : error ? <p role="alert" className="px-3 py-10 text-center text-[13px] text-[var(--color-slate-600)]">Não foi possível verificar suas permissões. Tente novamente.</p>
          : results.length ? results.map((item, index) => {
            const Icon = item.icon;
            return (
              <button key={item.href} id={listId + "-item-" + index}
                ref={node => { itemRefs.current[index] = node; }}
                type="button" role="option" aria-selected={index === safeSelected}
                onMouseEnter={() => setSelected(index)}
                onClick={() => navigate(item.href)}
                className={cn("flex w-full items-center gap-3 rounded-[var(--radius-lg)] px-3 py-2.5 text-left text-[13px] transition-colors duration-[var(--motion-standard)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]",
                  index === safeSelected ? "bg-[var(--color-panel)] text-[var(--color-ink)]" : "text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]")}>
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate font-medium">{item.label}</span>
                <span className="text-[11px] text-[var(--color-muted)]">{item.category}</span>
                {index === safeSelected ? <ArrowRight className="h-3.5 w-3.5 text-[var(--color-muted)]" aria-hidden="true" /> : null}
              </button>
            );
          }) : <p className="px-3 py-10 text-center text-[13px] text-[var(--color-slate-600)]">
            Nenhuma página disponível para esta busca e suas permissões.
          </p>}
        </div>
        <div className="flex items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2 text-[11px] text-[var(--color-muted)]">
          <span>↑ ↓ selecionar · Enter abrir · Esc fechar</span>
          <span>Apenas páginas disponíveis</span>
        </div>
      </section>
    </div>
  );
}
