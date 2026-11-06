"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight, Building2, Check, ChevronsUpDown, LogOut,
  Menu, PanelLeftClose, PanelLeftOpen, Search, Settings2, X,
} from "@/components/ui/icons";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { listWorkspaces, switchWorkspace } from "@/lib/workspaces-api";
import type { WorkspaceItem } from "@/lib/workspaces-api";
import { activeNavigationHref, getVisibleNavigation } from "./navigation";
import { CommandPalette } from "./command-palette";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const accountRef = useRef<HTMLDivElement>(null);
  const mobileOpener = useRef<HTMLButtonElement>(null);

  const me = useQuery({
    queryKey: ["org-me"],
    queryFn: () => api.me(),
    retry: false,
    staleTime: 60_000,
  });
  const workspaces = useQuery({
    queryKey: ["org-workspaces"],
    queryFn: listWorkspaces,
    retry: false,
    staleTime: 60_000,
  });
  const switcher = useMutation({
    mutationFn: (item: WorkspaceItem) => switchWorkspace({
      membership_id: item.membership_id || undefined,
      tenant_id: item.tenant_id,
    }),
    onSuccess: result => {
      toast.success("Workspace alterado para " + result.tenant_name + ".");
      queryClient.clear();
      window.location.assign("/");
    },
    onError: (error: Error) => toast.error(error.message || "Não foi possível trocar de workspace."),
  });

  const visibleGroups = useMemo(() => getVisibleNavigation(me.data), [me.data]);
  const activeHref = activeNavigationHref(visibleGroups, pathname);
  const canConfigure = visibleGroups.some(group => group.items.some(item => item.href === "/config"));
  const orgName = me.data?.tenant_name || "Workspace";
  const displayName = me.data?.display_name || me.data?.email || "Conta";
  const role = me.data?.role || "Membro";
  const email = me.data?.email || "";
  const workspaceItems = workspaces.data?.workspaces || [];

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem("mira:sidebar-collapsed") === "true");
    } catch { /* preference storage is optional */ }
  }, []);

  useEffect(() => {
    setMobileOpen(false);
    setAccountOpen(false);
    setWorkspaceOpen(false);
  }, [pathname]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileOpen(false);
        setAccountOpen(false);
        setWorkspaceOpen(false);
      }
    }
    function onDocumentClick(event: MouseEvent) {
      if (!workspaceRef.current?.contains(event.target as Node)) setWorkspaceOpen(false);
      if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onDocumentClick);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onDocumentClick);
    };
  }, []);

  function toggleCollapsed() {
    setCollapsed(previous => {
      const next = !previous;
      try { window.localStorage.setItem("mira:sidebar-collapsed", String(next)); } catch { /* optional */ }
      return next;
    });
  }

  function closeMobile() {
    setMobileOpen(false);
    mobileOpener.current?.focus();
  }

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <>
      <button ref={mobileOpener} type="button"
        aria-label="Abrir navegação" aria-controls="mira-workspace-navigation" aria-expanded={mobileOpen}
        onClick={() => setMobileOpen(true)}
        className="fixed left-3 top-3 z-30 grid h-9 w-9 place-items-center rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-white text-[var(--color-slate-600)] shadow-sm focus-visible:ring-2 focus-visible:ring-[var(--color-blue)] md:hidden">
        <Menu className="h-4 w-4" />
      </button>
      {mobileOpen && <button type="button" aria-label="Fechar menu lateral" onClick={closeMobile}
        className="fixed inset-0 z-40 bg-[var(--color-ink)]/40 md:hidden" />}

      <aside id="mira-workspace-navigation"
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-dvh w-[270px] min-h-0 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-canvas)] text-[var(--color-ink)]",
          "transition-[width,transform] duration-[var(--motion-standard)] ease-out motion-reduce:transition-none",
          "md:sticky md:top-0 md:z-20 md:h-dvh md:translate-x-0",
          collapsed ? "md:w-[64px]" : "md:w-[252px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}>
        <div className={cn("shrink-0 px-3 pt-3", collapsed && "md:px-2")}>
          <div className="mb-2 flex items-center gap-2">
            <div className={cn("flex min-w-0 flex-1 items-center gap-2 px-2", collapsed && "md:justify-center md:px-0")}>
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[var(--radius-md)] bg-[var(--color-ink)]">
                <Image src="/mira-mark.svg" alt="Marca MIRA" width={22} height={15} className="h-[15px] w-auto brightness-0 invert" priority />
              </span>
              <span className={cn("truncate text-[13px] font-semibold tracking-[-0.02em]", collapsed && "md:hidden")}>MIRA</span>
            </div>
            <button type="button" onClick={closeMobile} aria-label="Fechar navegação"
              className="grid h-8 w-8 place-items-center rounded-[var(--radius-md)] text-[var(--color-muted)] hover:bg-[var(--color-panel)] md:hidden">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="relative" ref={workspaceRef}>
            <button type="button" aria-label={"Workspace: " + orgName}
              aria-expanded={workspaceOpen} aria-haspopup="menu"
              onClick={() => { setWorkspaceOpen(value => !value); setAccountOpen(false); }}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-[var(--radius-lg)] border border-transparent px-2 py-2 text-left transition-colors duration-[var(--motion-standard)] hover:border-[var(--color-border)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]",
                collapsed && "md:justify-center md:px-0"
              )}>
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-panel)] text-[11px] font-semibold">
                {orgName.slice(0, 2).toUpperCase()}
              </span>
              <span className={cn("min-w-0 flex-1", collapsed && "md:hidden")}>
                <span className="block truncate text-[12px] font-semibold">{orgName}</span>
                <span className="block truncate text-[11px] text-[var(--color-muted)]">Trocar workspace</span>
              </span>
              <ChevronsUpDown className={cn("h-3.5 w-3.5 shrink-0 text-[var(--color-muted)]", collapsed && "md:hidden")} aria-hidden="true" />
            </button>
            {workspaceOpen && <div role="menu" aria-label="Seus workspaces"
              className={cn(
                "absolute z-[60] w-[260px] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-overlay)]",
                "left-0 top-[calc(100%+6px)]",
                collapsed && "md:left-[calc(100%+8px)] md:top-0"
              )}>
              <div className="border-b border-[var(--color-border)] px-3 py-2 text-[11px] font-semibold text-[var(--color-slate-600)]">Seus workspaces</div>
              <div className="max-h-[260px] overflow-y-auto p-1.5">
                {workspaces.isLoading ? <p role="status" className="px-3 py-3 text-[12px] text-[var(--color-muted)]">Carregando…</p>
                  : workspaces.isError ? <div className="px-3 py-3 text-[12px] text-[var(--color-slate-600)]">
                    <p>Não foi possível carregar workspaces.</p>
                    <button type="button" onClick={() => void workspaces.refetch()} className="mt-1 font-medium text-[var(--color-blue)]">Tentar novamente</button>
                  </div>
                  : workspaceItems.length ? workspaceItems.map(item =>
                    <button key={item.membership_id || item.tenant_id}
                      type="button" role="menuitem" disabled={item.is_current || switcher.isPending || item.status !== "active"}
                      aria-current={item.is_current ? "true" : undefined}
                      onClick={() => switcher.mutate(item)}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-[var(--radius-md)] px-2 py-2 text-left text-[12px] transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)] disabled:cursor-default",
                        item.is_current && "bg-[var(--color-panel)]"
                      )}>
                      <Building2 className="h-4 w-4 shrink-0 text-[var(--color-muted)]" aria-hidden="true" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{item.tenant_name}</span>
                        <span className="block text-[10px] text-[var(--color-muted)]">{item.role}</span>
                      </span>
                      {item.is_current ? <Check className="h-4 w-4 text-[var(--color-blue)]" /> : <ArrowLeftRight className="h-3.5 w-3.5 text-[var(--color-muted)]" />}
                    </button>
                  ) : <p className="px-3 py-3 text-[12px] text-[var(--color-muted)]">Nenhum workspace disponível.</p>}
              </div>
            </div>}
          </div>
          <button type="button" onClick={() => setCommandOpen(true)}
            aria-label="Buscar páginas (Ctrl+K ou Cmd+K)"
            className={cn(
              "my-3 flex h-9 w-full items-center gap-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 text-left text-[12px] text-[var(--color-slate-600)] transition-colors duration-[var(--motion-standard)] hover:bg-white focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]",
              collapsed && "md:justify-center md:px-0"
            )}>
            <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className={cn("min-w-0 flex-1 truncate", collapsed && "md:hidden")}>Buscar</span>
            <kbd className={cn("rounded border border-[var(--color-border)] bg-white px-1.5 py-0.5 text-[10px]", collapsed && "md:hidden")}>⌘ K</kbd>
          </button>
        </div>

        <nav aria-label="Navegação principal" className={cn("min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 pb-3", collapsed && "md:px-2")}>
          {me.isLoading ? <p role="status" className="px-2 py-4 text-[12px] text-[var(--color-muted)]">Carregando navegação…</p>
            : me.isError ? <div className="px-2 py-4 text-[12px] text-[var(--color-slate-600)]">
              <p>Não foi possível verificar seu acesso.</p>
              <button type="button" onClick={() => void me.refetch()} className="mt-2 text-[var(--color-blue)]">Tentar novamente</button>
            </div>
            : <div className="flex flex-col gap-4">
              {visibleGroups.map(group => (
                <section key={group.id}>
                  <h2 className={cn("mb-1 px-2.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]", collapsed && "md:sr-only")}>{group.label}</h2>
                  <div className="space-y-0.5">
                    {group.items.map(item => {
                      const Icon = item.icon;
                      const active = item.href === activeHref;
                      return (
                        <Link key={item.href} href={item.href} aria-label={item.label}
                          aria-current={active ? "page" : undefined} title={collapsed ? item.label : undefined}
                          onClick={() => setMobileOpen(false)}
                          className={cn(
                            "group flex h-9 items-center gap-2.5 rounded-[var(--radius-md)] px-2.5 text-[12px] font-medium transition-colors duration-[var(--motion-standard)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]",
                            collapsed && "md:justify-center md:px-0",
                            active ? "bg-[var(--color-panel)] font-semibold text-[var(--color-ink)]" : "text-[var(--color-slate-600)] hover:bg-[var(--color-panel)] hover:text-[var(--color-ink)]"
                          )}>
                          <Icon className="h-4 w-4 shrink-0 text-[var(--color-muted)] group-hover:text-[var(--color-ink)]" aria-hidden="true" />
                          <span className={cn("min-w-0 flex-1 truncate", collapsed && "md:hidden")}>{item.label}</span>
                          {active && <span className={cn("h-1.5 w-1.5 rounded-full bg-[var(--color-blue)]", collapsed && "md:hidden")} aria-hidden="true" />}
                        </Link>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>}
        </nav>

        <div className={cn("relative shrink-0 border-t border-[var(--color-border)] p-2.5", collapsed && "md:px-2")} ref={accountRef}>
          <button type="button" aria-expanded={accountOpen} aria-haspopup="menu"
            onClick={() => { setAccountOpen(value => !value); setWorkspaceOpen(false); }}
            className={cn("flex w-full items-center gap-2.5 rounded-[var(--radius-md)] px-2 py-2 text-left transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]", collapsed && "md:justify-center md:px-0")}>
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] text-[11px] font-semibold">{displayName.slice(0, 1).toUpperCase()}</span>
            <span className={cn("min-w-0 flex-1", collapsed && "md:hidden")}>
              <span className="block truncate text-[12px] font-semibold">{displayName}</span>
              <span className="block truncate text-[11px] text-[var(--color-muted)]">{role}</span>
            </span>
            <ChevronsUpDown className={cn("h-3.5 w-3.5 text-[var(--color-muted)]", collapsed && "md:hidden")} aria-hidden="true" />
          </button>
          {accountOpen && <div role="menu" aria-label="Conta"
            className={cn(
              "absolute bottom-[calc(100%+6px)] left-2 right-2 z-[60] overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-overlay)]",
              collapsed && "md:bottom-0 md:left-[calc(100%+8px)] md:right-auto md:w-[238px]"
            )}>
            <div className="border-b border-[var(--color-border)] px-3 py-2.5">
              <p className="truncate text-[12px] font-semibold">{displayName}</p>
              <p className="truncate text-[11px] text-[var(--color-muted)]">{email}</p>
            </div>
            {canConfigure && <Link role="menuitem" href="/config" onClick={() => setAccountOpen(false)}
              className="flex items-center gap-2 px-3 py-2.5 text-[12px] text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]">
              <Settings2 className="h-4 w-4" /> Configurações
            </Link>}
            <button type="button" role="menuitem" onClick={logout}
              className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[12px] text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]">
              <LogOut className="h-4 w-4" /> Sair da conta
            </button>
          </div>}
          <button type="button" onClick={toggleCollapsed} aria-label={collapsed ? "Expandir navegação" : "Recolher navegação"}
            className="mt-1 hidden h-8 w-full items-center justify-center gap-2 rounded-[var(--radius-md)] text-[11px] font-medium text-[var(--color-muted)] transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)] md:flex">
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <><PanelLeftClose className="h-4 w-4" /> Recolher menu</>}
          </button>
        </div>
      </aside>
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen}
        groups={visibleGroups} tenantId={me.data?.tenant_id} userId={me.data?.user_id} loading={me.isLoading} error={me.isError} />
    </>
  );
}
