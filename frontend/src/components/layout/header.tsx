"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell, Building2, ChevronRight, X } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type HeaderProps = {
  title: string;
  subtitle?: string;
  compact?: boolean;
  breadcrumbs?: string[];
  actions?: ReactNode;
};

/** A shared, compact workspace heading. It never synthesizes notifications. */
export function Header({ title, subtitle, compact = false, breadcrumbs, actions }: HeaderProps) {
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const me = useQuery({
    queryKey: ["org-me"],
    queryFn: () => api.me(),
    retry: false,
    staleTime: 60_000,
  });

  useEffect(() => {
    function outside(event: MouseEvent) {
      if (!panelRef.current?.contains(event.target as Node)) setNotificationsOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") setNotificationsOpen(false);
    }
    document.addEventListener("mousedown", outside);
    window.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      window.removeEventListener("keydown", escape);
    };
  }, []);

  const path = breadcrumbs?.length ? breadcrumbs : [me.data?.tenant_name || "Workspace"];
  return (
    <header className="sticky top-0 z-20 border-b border-[var(--color-border)] bg-[var(--color-canvas)]/95 backdrop-blur-md">
      <div className={cn("flex min-h-[58px] w-full items-center justify-between gap-3 py-2 pl-14 pr-4 md:px-6 xl:px-8", compact && "min-h-[46px]")}>
        {!compact ? (
          <div className="min-w-0 flex-1">
            <nav aria-label="Localização" className="hidden min-w-0 items-center gap-1 text-[11px] text-[var(--color-muted)] sm:flex">
              <Building2 className="h-3 w-3 shrink-0" aria-hidden="true" />
              {path.map((part, index) => (
                <span key={index} className="inline-flex min-w-0 items-center gap-1">
                  {index > 0 ? <ChevronRight className="h-3 w-3 shrink-0" aria-hidden="true" /> : null}
                  <span className="max-w-[180px] truncate">{part}</span>
                </span>
              ))}
              <ChevronRight className="h-3 w-3 shrink-0" aria-hidden="true" />
              <span aria-current="page" className="truncate font-medium text-[var(--color-slate-600)]">{title}</span>
            </nav>
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-0.5">
              <h1 className="truncate text-[17px] font-semibold leading-[25px] tracking-[-0.025em] text-[var(--color-ink)]">
                {title}
              </h1>
              {subtitle ? <p className="hidden truncate text-[11px] text-[var(--color-slate-600)] lg:block">{subtitle}</p> : null}
            </div>
          </div>
        ) : <span className="min-w-0 flex-1" />}

        <div className="flex shrink-0 items-center gap-2">
          {actions}
          <div className="relative" ref={panelRef}>
            <button type="button" aria-label="Informações sobre notificações"
              aria-expanded={notificationsOpen} aria-haspopup="dialog"
              onClick={() => setNotificationsOpen(value => !value)}
              className={cn("grid h-8 w-8 place-items-center rounded-[var(--radius-md)] text-[var(--color-slate-600)] transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]", notificationsOpen && "bg-[var(--color-panel)]")}>
              <Bell className="h-[17px] w-[17px]" aria-hidden="true" />
            </button>
            {notificationsOpen && (
              <section role="dialog" aria-label="Notificações"
                className="absolute right-0 top-[calc(100%+8px)] z-40 w-[min(90vw,330px)] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-overlay)]">
                <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
                  <p className="text-[13px] font-semibold text-[var(--color-ink)]">Notificações</p>
                  <button type="button" aria-label="Fechar notificações" onClick={() => setNotificationsOpen(false)}
                    className="rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-panel)]">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <p role="status" className="px-4 py-8 text-center text-[12px] leading-5 text-[var(--color-slate-600)]">
                  O feed global de notificações ainda não está conectado. Nenhum evento é exibido sem uma fonte real.
                </p>
              </section>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
