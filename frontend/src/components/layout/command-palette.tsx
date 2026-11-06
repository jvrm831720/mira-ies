"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Search, ArrowRight, X, Users } from "@/components/ui/icons";
import type { LucideIcon } from "@/components/ui/icons";
import { listStudentIndex } from "@/lib/object-index-api";
import { cn } from "@/lib/utils";
import { searchNavigation, type NavigationGroup } from "./navigation";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groups: NavigationGroup[];
  tenantId?: string;
  loading?: boolean;
  error?: boolean;
};
type Command = { href: string; label: string; category: string; icon: LucideIcon; detail?: string };

const QUICK_ACTIONS = [
  { href: "/trabalho", label: "Abrir fila do coordenador", category: "Ação rápida", icon: Users, terms: "fila pendencias atividades" },
  { href: "/campanhas", label: "Gerenciar campanhas", category: "Ação rápida", icon: ArrowRight, terms: "campanha retencao" },
  { href: "/resultados", label: "Consultar permanência", category: "Ação rápida", icon: ArrowRight, terms: "resultados permanencia relatorio" },
];

export function CommandPalette({ open, onOpenChange, groups, tenantId, loading, error }: Props) {
  const router = useRouter();
  const labelId = useId();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const canSearchStudents = groups.some(group => group.items.some(item => item.href === "/alunos"));

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedQuery(query.trim()), 180);
    return () => window.clearTimeout(timeout);
  }, [query]);

  const studentResults = useQuery({
    queryKey: ["command-students", tenantId, debouncedQuery],
    queryFn: () => listStudentIndex({ limit: 8, offset: 0, q: debouncedQuery, sort: "name_asc", view: "todos" }),
    enabled: open && !!tenantId && canSearchStudents && debouncedQuery.length >= 2 && !loading && !error,
    staleTime: 20_000,
    retry: false,
  });
  const results = useMemo<Command[]>(() => {
    const needle = query.trim().toLocaleLowerCase("pt-BR");
    const navigation: Command[] = searchNavigation(groups, query).map(item =>
      ({ href: item.href, label: item.label, category: item.category, icon: item.icon }));
    const actions: Command[] = QUICK_ACTIONS.filter(action =>
      groups.some(group => group.items.some(item => item.href === action.href)) &&
      (!needle || (action.label + " " + action.terms).toLocaleLowerCase("pt-BR").includes(needle))
    ).map(action => ({ href: action.href, label: action.label, category: action.category, icon: action.icon }));
    const students: Command[] = debouncedQuery === query.trim() && debouncedQuery.length >= 2
      ? (studentResults.data?.students || []).map(student => ({
        href: "/alunos/" + encodeURIComponent(student.id),
        label: student.nome || "Aluno sem nome",
        category: "Aluno",
        icon: Users,
        detail: student.matricula || student.curso || undefined,
      }))
      : [];
    const unique = new Map<string, Command>();
    for (const item of [...students, ...actions, ...navigation]) if (!unique.has(item.href)) unique.set(item.href, item);
    return [...unique.values()];
  }, [groups, query, studentResults.data, debouncedQuery]);
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
    }
  }
  function trapFocus(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('input, button:not(:disabled):not([tabindex="-1"])') || []);
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
      className="relative z-10 w-full max-w-[600px] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-[var(--color-canvas)] shadow-[var(--shadow-overlay)]">
      <h2 id={labelId} className="sr-only">Busca global da MIRA</h2>
      <div className="flex h-14 items-center gap-3 border-b border-[var(--color-border)] px-4">
        <Search className="h-[18px] w-[18px] shrink-0 text-[var(--color-muted)]" aria-hidden="true" />
        <input ref={inputRef} value={query} onChange={event => { setQuery(event.target.value); setSelected(0); }}
          onKeyDown={onInputKeyDown} role="combobox" aria-expanded="true" aria-controls={listId}
          aria-activedescendant={results[safeSelected] ? listId + "-item-" + safeSelected : undefined}
          aria-autocomplete="list" aria-label="Buscar páginas, alunos e ações autorizadas"
          placeholder="Buscar aluno, campanha, relatório ou ação…" autoComplete="off"
          className="h-full min-w-0 flex-1 border-0 bg-transparent text-[length:var(--type-body-compact)] text-[var(--color-ink)] outline-none placeholder:text-[var(--color-muted)]" />
        <button type="button" aria-label="Fechar" onClick={() => onOpenChange(false)}
          className="rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]"><X className="h-4 w-4"/></button>
      </div>
      <div id={listId} role="listbox" aria-label="Resultados autorizados" className="max-h-[min(58vh,430px)] overflow-y-auto p-2">
        {loading ? <p role="status" className="px-3 py-10 text-center text-[length:var(--type-body-compact)]">Carregando permissões…</p> :
          error ? <p role="alert" className="px-3 py-10 text-center text-[length:var(--type-body-compact)]">Não foi possível verificar suas permissões.</p> : <>
          {results.map((item, index) => {
            const Icon = item.icon;
            return <button key={item.href} id={listId + "-item-" + index}
              ref={node => { itemRefs.current[index] = node; }} role="option" aria-selected={index === safeSelected}
              type="button" onMouseEnter={() => setSelected(index)} onClick={() => navigate(item.href)}
              className={cn("flex w-full items-center gap-3 rounded-[var(--radius-lg)] px-3 py-2.5 text-left text-[length:var(--type-body-compact)] transition-colors duration-[var(--motion-standard)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)] motion-reduce:transition-none",
                index === safeSelected ? "bg-[var(--color-panel)] text-[var(--color-ink)]" : "text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]")}>
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true"/>
              <span className="min-w-0 flex-1 truncate font-medium">{item.label}{item.detail && <span className="block truncate text-[length:var(--type-caption)] font-normal text-[var(--color-muted)]">{item.detail}</span>}</span>
              <span className="text-[length:var(--type-caption)] text-[var(--color-muted)]">{item.category}</span>
              {index === safeSelected && <ArrowRight className="h-3.5 w-3.5" aria-hidden="true"/>}
            </button>;
          })}
          {canSearchStudents && query.trim().length >= 2 && studentResults.isFetching &&
            <p role="status" className="px-3 py-2 text-xs text-[var(--color-muted)]">Buscando alunos autorizados…</p>}
          {studentResults.isError && <p role="alert" className="px-3 py-2 text-xs text-[var(--color-red)]">Busca de alunos indisponível. As páginas continuam acessíveis.</p>}
          {!results.length && !studentResults.isFetching && <p className="px-3 py-10 text-center text-[length:var(--type-body-compact)] text-[var(--color-slate-600)]">
            Nenhum resultado disponível para esta busca.
          </p>}
        </>}
      </div>
      <div className="flex justify-between border-t border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2 text-[length:var(--type-caption)] text-[var(--color-muted)]">
        <span>↑ ↓ selecionar · Enter abrir · Esc fechar</span><span>Somente informações autorizadas</span>
      </div>
    </section>
  </div>;
}
