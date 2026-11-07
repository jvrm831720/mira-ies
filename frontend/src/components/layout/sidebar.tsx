"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight, Building2, Check, ChevronRight, LogOut,
  Menu, PanelLeftClose, PanelLeftOpen, Search, Settings2, X,
} from "@/components/ui/icons";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { listWorkspaces, switchWorkspace } from "@/lib/workspaces-api";
import type { WorkspaceItem } from "@/lib/workspaces-api";
import {
  activeNavigationHref, getVisibleNavigation, hasNavigationPermission,
  type NavigationItem,
} from "./navigation";
import { CommandPalette } from "./command-palette";
import { useNavigationContext } from "./navigation-context-provider";

/**
 * MIRA workspace sidebar.
 * Attio's dark, compact navigation is the visual reference; markup and logic are
 * original to MIRA. The existing authenticated route/role/module contracts win.
 */
const sidebarSections: Array<{ id: string; label: string; paths: string[] }> = [
  { id: "records", label: "Registros", paths: ["/alunos", "/academico", "/cobranca"] },
  { id: "lists", label: "Listas e jornadas", paths: ["/alunos/grupos", "/campanhas", "/retencao", "/academico/jornadas", "/academico/servicos"] },
  { id: "operations", label: "Operação", paths: ["/disparos", "/retencao/logs"] },
  { id: "data", label: "Dados", paths: ["/apps", "/dados", "/conectores", "/conectores/financeiro", "/importar", "/importacoes"] },
];
const quickPaths = ["/", "/trabalho", "/monitoramento", "/resultados", "/workflows"];

function recordTone(href: string): string {
  if (href === "/cobranca") return "bg-[var(--mira-sidebar-billing)]";
  if (href === "/academico") return "bg-[var(--mira-sidebar-academic)]";
  return "bg-[var(--mira-sidebar-primary)]";
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { clearScroll } = useNavigationContext();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [closedSections, setClosedSections] = useState<Record<string, boolean>>({});
  const workspaceRef = useRef<HTMLDivElement>(null);
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
      clearScroll();
      queryClient.clear();
      window.location.assign("/");
    },
    onError: (error: Error) => toast.error(error.message || "Não foi possível trocar de workspace."),
  });

  const groups = useMemo(() => getVisibleNavigation(me.data), [me.data]);
  const items = useMemo(() => groups.flatMap(group => group.items), [groups]);
  const byPath = useMemo(() => new Map(items.map(item => [item.href, item])), [items]);
  const quickItems = useMemo(
    () => quickPaths.map(path => byPath.get(path)).filter((item): item is NavigationItem => !!item),
    [byPath],
  );
  const visibleSections = useMemo(() => sidebarSections.map(section => ({
    ...section,
    items: section.paths.map(path => byPath.get(path)).filter((item): item is NavigationItem => !!item),
  })).filter(section => section.items.length > 0), [byPath]);
  const activeHref = activeNavigationHref(groups, pathname);
  const orgName = me.data?.tenant_name || "Workspace";
  const displayName = me.data?.display_name || me.data?.email || "Conta";
  const email = me.data?.email || "";
  const workspaceItems = workspaces.data?.workspaces || [];
  const canConfigure = items.some(item => item.href === "/config");
  const canSeeMembers = items.some(item => item.href === "/membros");
  const canInvite = canSeeMembers && hasNavigationPermission(me.data, "members.manage");
  const canSeeRoles = items.some(item => item.href === "/membros/cargos");
  const canSeePlan = items.some(item => item.href === "/fatura");

  useEffect(() => {
    try { setCollapsed(window.localStorage.getItem("mira:sidebar-collapsed") === "true"); }
    catch { /* Optional preference storage. */ }
  }, []);

  useEffect(() => {
    setMobileOpen(false);
    setWorkspaceOpen(false);
  }, [pathname]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileOpen(false);
        setWorkspaceOpen(false);
      }
    }
    function onDocumentClick(event: MouseEvent) {
      if (!workspaceRef.current?.contains(event.target as Node)) setWorkspaceOpen(false);
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
      try { window.localStorage.setItem("mira:sidebar-collapsed", String(next)); }
      catch { /* Optional preference storage. */ }
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

  function onLinkClick() {
    setMobileOpen(false);
    setWorkspaceOpen(false);
  }

  function NavLink({ item, record = false }: { item: NavigationItem; record?: boolean }) {
    const Icon = item.icon;
    const active = activeHref === item.href;
    const label = item.href === "/" ? "Início" : item.label;
    return (
      <Link
        href={item.href}
        aria-label={label}
        aria-current={active ? "page" : undefined}
        title={collapsed ? label : undefined}
        onClick={onLinkClick}
        className={cn(
          "group flex h-[29px] w-full items-center gap-2 rounded-[9px] px-2 text-[length:var(--mira-sidebar-type-14)] font-medium leading-5",
          "outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-[var(--mira-sidebar-focus)] motion-reduce:transition-none",
          "text-[var(--mira-sidebar-ink)] hover:bg-[var(--mira-sidebar-hover)]",
          active && "bg-[var(--mira-sidebar-hover)]",
          collapsed && "md:justify-center md:px-0",
        )}
      >
        {record
          ? <span aria-hidden="true" className={cn("h-4 w-4 shrink-0 rounded-[5px]", recordTone(item.href))} />
          : <Icon aria-hidden="true" className="h-[17px] w-[17px] shrink-0 text-[var(--mira-sidebar-icon)] group-hover:text-[var(--mira-sidebar-ink)]" />}
        <span className={cn("min-w-0 flex-1 truncate", collapsed && "md:hidden")}>{label}</span>
      </Link>
    );
  }

  return (
    <>
      <button
        ref={mobileOpener}
        type="button"
        aria-label="Abrir navegação"
        aria-controls="mira-workspace-navigation"
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen(true)}
        className="fixed left-3 top-3 z-30 grid h-9 w-9 place-items-center rounded-lg border border-[var(--mira-sidebar-outline)] bg-[var(--mira-sidebar-bg)] text-[var(--mira-sidebar-ink)] focus-visible:ring-2 focus-visible:ring-[var(--mira-sidebar-focus)] md:hidden"
      >
        <Menu className="h-4 w-4" />
      </button>
      {mobileOpen && <button
        type="button"
        aria-label="Fechar menu lateral"
        onClick={closeMobile}
        className="fixed inset-0 z-40 bg-black/50 md:hidden"
      />}

      <aside
        id="mira-workspace-navigation"
        aria-label="Navegação do workspace"
        style={{ fontFamily: "Inter, sans-serif" }}
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-dvh w-[275px] min-h-0 shrink-0 flex-col border-r border-[var(--mira-sidebar-edge)]",
          "bg-[var(--mira-sidebar-bg)] font-sans text-[var(--mira-sidebar-ink)] antialiased",
          "transition-[width,transform] duration-180 ease-out motion-reduce:transition-none",
          "md:sticky md:top-0 md:z-20 md:h-dvh md:translate-x-0",
          collapsed ? "md:w-[54px]" : "md:w-[275px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="relative z-30 shrink-0 border-b border-[var(--mira-sidebar-divider)]" ref={workspaceRef}>
          <div className={cn("flex h-[48px] items-center", collapsed && "md:justify-center")}>
            <button
              type="button"
              aria-label={"Workspace: " + orgName}
              aria-expanded={workspaceOpen}
              aria-haspopup="menu"
              onClick={() => setWorkspaceOpen(value => !value)}
              className={cn(
                "flex h-full min-w-0 flex-1 items-center gap-[10px] px-3 text-left",
                "hover:bg-[var(--mira-sidebar-menu)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--mira-sidebar-focus)]",
                collapsed && "md:flex-none md:px-2",
              )}
            >
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-[6px] border border-[var(--mira-sidebar-mark-outline)] bg-[var(--mira-sidebar-mark-bg)]">
                <Image src="/mira-mark.svg" alt="Marca MIRA" width={18} height={13} className="h-[13px] w-auto brightness-0 invert" priority />
              </span>
              <span className={cn("min-w-0 flex-1 truncate text-[length:var(--mira-sidebar-type-16)] font-semibold tracking-[-0.02em]", collapsed && "md:hidden")}>{orgName}</span>
            </button>
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-label={collapsed ? "Expandir navegação" : "Recolher navegação"}
              className={cn(
                "mr-2 hidden h-7 w-7 shrink-0 place-items-center rounded-[6px] text-[var(--mira-sidebar-secondary)] hover:bg-[var(--mira-sidebar-divider)] hover:text-white md:grid",
                collapsed && "md:absolute md:left-[54px] md:top-2 md:rounded-l-none md:border md:border-[var(--mira-sidebar-menu-hover)] md:bg-[var(--mira-sidebar-menu)]",
              )}
            >
              {collapsed ? <PanelLeftOpen className="h-[15px] w-[15px]" /> : <PanelLeftClose className="h-[15px] w-[15px]" />}
            </button>
            <button type="button" onClick={closeMobile} aria-label="Fechar navegação"
              className="mr-2 grid h-8 w-8 shrink-0 place-items-center rounded-md text-[var(--mira-sidebar-icon)] hover:bg-[var(--mira-sidebar-divider)] md:hidden">
              <X className="h-4 w-4" />
            </button>
          </div>
          {workspaceOpen && <div
            role="menu" aria-label="Workspace e conta"
            className={cn(
              "absolute left-2 top-[54px] z-[70] w-[280px] overflow-hidden rounded-[12px]",
              "border border-[var(--mira-sidebar-outline)] bg-[var(--mira-sidebar-menu)] py-1.5 text-[var(--mira-sidebar-ink)] shadow-[0_20px_55px_rgba(0,0,0,0.55)]",
              collapsed && "md:left-[62px] md:top-0",
            )}
          >
            <div className="px-3 py-2 text-[length:var(--mira-sidebar-type-12)] font-semibold">{orgName}</div>
            {workspaces.isLoading
              ? <p role="status" className="px-3 py-2 text-xs text-[var(--mira-sidebar-icon)]">Carregando workspaces…</p>
              : workspaces.isError
                ? <button role="menuitem" type="button" onClick={() => void workspaces.refetch()}
                    className="block w-full px-3 py-2 text-left text-xs hover:bg-[var(--mira-sidebar-menu-hover)]">Tentar novamente</button>
                : workspaceItems.length > 1 && <div className="max-h-40 overflow-y-auto border-b border-[var(--mira-sidebar-outline)] pb-1">
                  {workspaceItems.map(item => <button
                    key={item.membership_id || item.tenant_id}
                    type="button" role="menuitem"
                    disabled={item.is_current || switcher.isPending || item.status !== "active"}
                    onClick={() => switcher.mutate(item)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-[length:var(--mira-sidebar-type-14)] hover:bg-[var(--mira-sidebar-menu-hover)] disabled:opacity-60"
                  >
                    <Building2 aria-hidden="true" className="h-4 w-4 shrink-0 text-[var(--mira-sidebar-icon)]" />
                    <span className="min-w-0 flex-1 truncate">{item.tenant_name}</span>
                    {item.is_current ? <Check aria-hidden="true" className="h-4 w-4" /> : <ArrowLeftRight aria-hidden="true" className="h-4 w-4 opacity-50" />}
                  </button>)}
                </div>
            }
            <div className="border-t border-[var(--mira-sidebar-outline)] py-1">
              {canConfigure && <Link role="menuitem" href="/config" onClick={onLinkClick}
                className="block px-8 py-2 text-[length:var(--mira-sidebar-type-14)] hover:bg-[var(--mira-sidebar-menu-hover)]">Configurações do workspace</Link>}
              {canSeeMembers && <Link role="menuitem" href="/membros" onClick={onLinkClick}
                className="block px-8 py-2 text-[length:var(--mira-sidebar-type-14)] hover:bg-[var(--mira-sidebar-menu-hover)]">Membros da equipe</Link>}
              {canSeeRoles && <Link role="menuitem" href="/membros/cargos" onClick={onLinkClick}
                className="block px-8 py-2 text-[length:var(--mira-sidebar-type-14)] hover:bg-[var(--mira-sidebar-menu-hover)]">Cargos e permissões</Link>}
              {canSeePlan && <Link role="menuitem" href="/fatura" onClick={onLinkClick}
                className="block px-8 py-2 text-[length:var(--mira-sidebar-type-14)] hover:bg-[var(--mira-sidebar-menu-hover)]">Plano MIRA</Link>}
            </div>
            <div className="border-t border-[var(--mira-sidebar-outline)] py-1">
              <div className="truncate px-8 py-2 text-[length:var(--mira-sidebar-type-11)] text-[var(--mira-sidebar-muted)]" title={email}>{displayName}</div>
              <button type="button" role="menuitem" onClick={logout}
                className="flex w-full items-center gap-2 px-8 py-2 text-left text-[length:var(--mira-sidebar-type-14)] hover:bg-[var(--mira-sidebar-menu-hover)]">
                <LogOut aria-hidden="true" className="h-4 w-4" /> Sair da conta
              </button>
            </div>
          </div>}
        </div>

        <div className={cn("shrink-0 px-2 pt-2", collapsed && "md:px-2")}>
          <button
            type="button" onClick={() => setCommandOpen(true)}
            aria-label="Buscar páginas (Ctrl+K ou Cmd+K)"
            className={cn(
              "flex h-[30px] w-full items-center gap-2 rounded-[9px] border border-[var(--mira-sidebar-section)]",
              "bg-[var(--mira-sidebar-deep)] px-2 text-left text-[length:var(--mira-sidebar-type-14)] text-[var(--mira-sidebar-ink)]",
              "hover:bg-[var(--mira-sidebar-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--mira-sidebar-focus)]",
              collapsed && "md:justify-center md:px-0",
            )}
          >
            <Search aria-hidden="true" className="h-[15px] w-[15px] shrink-0 text-[var(--mira-sidebar-icon)]" />
            <span className={cn("min-w-0 flex-1 truncate", collapsed && "md:hidden")}>Buscar</span>
            <span className={cn("flex items-center gap-1", collapsed && "md:hidden")} aria-hidden="true">
              <kbd className="rounded-[4px] border border-[var(--mira-sidebar-separator)] px-1 text-[length:var(--mira-sidebar-type-10)] leading-[17px] text-[var(--mira-sidebar-muted)]">CTRL</kbd>
              <kbd className="rounded-[4px] border border-[var(--mira-sidebar-separator)] px-1 text-[length:var(--mira-sidebar-type-10)] leading-[17px] text-[var(--mira-sidebar-muted)]">K</kbd>
            </span>
          </button>
        </div>

        <nav
          aria-label="Navegação principal"
          className={cn(
            "min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-2 pb-3 pt-2",
            "scrollbar-thin scrollbar-thumb-[var(--mira-sidebar-control)]",
          )}
        >
          {me.isLoading
            ? <p role="status" className="px-2 py-4 text-xs text-[var(--mira-sidebar-icon)]">Carregando navegação…</p>
            : me.isError
              ? <div className="px-2 py-4 text-xs text-[var(--mira-sidebar-icon)]">
                  <p>Não foi possível verificar seu acesso.</p>
                  <button type="button" onClick={() => void me.refetch()} className="mt-2 text-[var(--mira-sidebar-accent)]">Tentar novamente</button>
                </div>
              : <>
                <div className="space-y-[1px]">
                  {quickItems.map(item => <NavLink key={item.href} item={item} />)}
                </div>
                {visibleSections.map(section => {
                  const isClosed = closedSections[section.id] === true;
                  return <section key={section.id} className="mt-[17px]">
                    <button
                      type="button"
                      aria-label={section.label}
                      aria-expanded={!isClosed}
                      onClick={() => setClosedSections(previous => ({ ...previous, [section.id]: !previous[section.id] }))}
                      className={cn(
                        "group flex h-7 w-full items-center justify-between rounded-[6px] px-[30px] text-left",
                        "text-[length:var(--mira-sidebar-type-12)] font-medium text-[var(--mira-sidebar-caption)] hover:bg-[var(--mira-sidebar-hover)] hover:text-[var(--mira-sidebar-ink)]",
                        collapsed && "md:justify-center md:px-0",
                      )}
                    >
                      <span className={cn("truncate", collapsed && "md:sr-only")}>{section.label}</span>
                      <ChevronRight aria-hidden="true" className={cn("h-3 w-3 opacity-0 transition-transform group-hover:opacity-100", !isClosed && "rotate-90", collapsed && "md:hidden")} />
                    </button>
                    {!isClosed && <div className="mt-[2px] space-y-[1px]">
                      {section.items.map(item => <NavLink key={item.href} item={item} record={section.id === "records"} />)}
                    </div>}
                  </section>;
                })}
              </>
          }
        </nav>

        <div className={cn("shrink-0 border-t border-[var(--mira-sidebar-foot-divider)] px-2 py-2", collapsed && "md:px-2")}>
          {canInvite && <Link
            href="/membros"
            onClick={onLinkClick}
            aria-label="Convidar membros"
            title={collapsed ? "Convidar membros" : undefined}
            className={cn(
              "flex h-[29px] items-center gap-2 rounded-[9px] px-2 text-[length:var(--mira-sidebar-type-14)] text-[var(--mira-sidebar-ink)]",
              "hover:bg-[var(--mira-sidebar-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--mira-sidebar-focus)]",
              collapsed && "md:justify-center md:px-0",
            )}
          >
            <span aria-hidden="true" className="text-[length:var(--mira-sidebar-type-17)] leading-none text-[var(--mira-sidebar-icon)]">+</span>
            <span className={cn("truncate", collapsed && "md:hidden")}>Convidar membros</span>
          </Link>}
          <button type="button" onClick={() => setWorkspaceOpen(true)}
            className={cn(
              "flex h-[29px] w-full items-center gap-2 rounded-[9px] border-t border-[var(--mira-sidebar-foot-divider)] px-2 text-left text-[length:var(--mira-sidebar-type-11)] text-[var(--mira-sidebar-caption)]",
              "hover:bg-[var(--mira-sidebar-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--mira-sidebar-focus)]",
              collapsed && "md:justify-center md:px-0",
            )}
            title={collapsed ? "Conta e workspace" : undefined}
          >
            <Settings2 aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
            <span className={cn("min-w-0 flex-1 truncate", collapsed && "md:hidden")}>{displayName}</span>
          </button>
        </div>
      </aside>
      <CommandPalette
        open={commandOpen}
        onOpenChange={setCommandOpen}
        groups={groups}
        tenantId={me.data?.tenant_id}
        userId={me.data?.user_id ?? undefined}
        loading={me.isLoading}
        error={me.isError}
      />
    </>
  );
}
