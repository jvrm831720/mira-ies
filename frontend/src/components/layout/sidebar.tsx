"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  BriefcaseBusiness,
  ChartNoAxesCombined,
  ChevronDown,
  ChevronsUpDown,
  Database,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Settings2,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/lib/auth";
import { api } from "@/lib/api";

type NavLink = {
  href: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  match?: "exact" | "prefix";
};

type NavGroup = {
  id: string;
  label: string;
  links: NavLink[];
};

const groups: NavGroup[] = [
  {
    id: "executiva",
    label: "Visão executiva",
    links: [
      {
        href: "/",
        label: "Visão geral",
        description: "Painel e prioridades",
        icon: LayoutDashboard,
        match: "exact",
      },
    ],
  },
  {
    id: "alunos",
    label: "Gestão de alunos",
    links: [
      {
        href: "/alunos",
        label: "Alunos",
        description: "Base acadêmica",
        icon: Users,
        match: "prefix",
      },
    ],
  },
  {
    id: "operacao",
    label: "Operação",
    links: [
      {
        href: "/trabalho",
        label: "Central de trabalho",
        description: "Filas e tarefas",
        icon: BriefcaseBusiness,
        match: "prefix",
      },
      {
        href: "/retencao",
        label: "Intervenções",
        description: "Ações de retenção",
        icon: Workflow,
        match: "prefix",
      },
    ],
  },
  {
    id: "inteligencia",
    label: "Inteligência e resultados",
    links: [
      {
        href: "/retencao/logs",
        label: "Resultados",
        description: "Indicadores e logs",
        icon: ChartNoAxesCombined,
        match: "prefix",
      },
    ],
  },
  {
    id: "admin",
    label: "Administração",
    links: [
      {
        href: "/conectores",
        label: "Dados e integrações",
        description: "Conectores e imports",
        icon: Database,
        match: "prefix",
      },
      {
        href: "/config",
        label: "Configurações",
        description: "Instituição e acesso",
        icon: Settings2,
        match: "prefix",
      },
    ],
  },
];

function isActive(pathname: string, link: NavLink): boolean {
  if (link.match === "exact" || link.href === "/") return pathname === "/";
  if (link.href === "/retencao") {
    return (
      pathname === "/retencao" ||
      (pathname.startsWith("/retencao/") &&
        !pathname.startsWith("/retencao/logs"))
    );
  }
  if (link.href === "/retencao/logs") {
    return (
      pathname === "/retencao/logs" || pathname.startsWith("/retencao/logs/")
    );
  }
  return pathname === link.href || pathname.startsWith(link.href + "/");
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(groups.map((g) => [g.id, true]))
  );
  const accountRef = useRef<HTMLDivElement>(null);

  const me = useQuery({
    queryKey: ["org-me"],
    queryFn: () => api.me(),
    retry: false,
    staleTime: 60_000,
  });

  const orgName = me.data?.tenant_name || "Sua instituição";
  const displayName = me.data?.display_name || me.data?.email || "Conta";
  const role = me.data?.role;
  const email = me.data?.email;

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!accountRef.current?.contains(e.target as Node)) setAccountOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Auto-expand group that contains the active route
  useEffect(() => {
    setOpenGroups((prev) => {
      const next = { ...prev };
      for (const g of groups) {
        if (g.links.some((l) => isActive(pathname, l))) next[g.id] = true;
      }
      return next;
    });
  }, [pathname]);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  function toggleGroup(id: string) {
    setOpenGroups((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Abrir menu de navegação"
        className="fixed left-3 top-3 z-40 grid h-10 w-10 place-items-center rounded-lg border border-[#E5E7EB] bg-white text-[#111827] shadow-sm md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Fechar menu de navegação"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-40 bg-[#111827]/35 md:hidden"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex min-h-screen shrink-0 flex-col",
          "border-r border-[#E5E7EB] bg-[#F8FAFC] text-[#111827]",
          "transition-[width,transform] duration-200 ease-out",
          "md:sticky md:top-0 md:z-20",
          collapsed ? "w-[68px]" : "w-[264px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          "md:flex"
        )}
      >
        {/* ── Header ─────────────────────────────────────────────── */}
        <div
          className={cn(
            "flex h-[52px] shrink-0 items-center border-b border-[#E5E7EB] bg-white",
            collapsed ? "justify-center px-2" : "gap-2 px-3"
          )}
        >
          <div className={cn("flex min-w-0 flex-1 items-center gap-2", collapsed && "flex-none justify-center")}>
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#111827]">
              <Image
                src="/favicon.svg"
                alt=""
                width={16}
                height={16}
                className="h-4 w-4 brightness-0 invert"
                priority
              />
            </span>
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <Image
                  src="/mira-logo.svg"
                  alt="MIRA"
                  width={64}
                  height={18}
                  className="h-[18px] w-auto brightness-0"
                  priority
                />
                <p className="truncate text-[10px] leading-tight text-[#667085]">{orgName}</p>
              </div>
            )}
          </div>

          {mobileOpen ? (
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              aria-label="Fechar menu"
              className="grid h-8 w-8 place-items-center rounded-md text-[#667085] hover:bg-[#F3F4F6] md:hidden"
            >
              <X className="h-4 w-4" />
            </button>
          ) : !collapsed ? (
            <button
              type="button"
              onClick={() => setCollapsed(true)}
              aria-label="Recolher menu lateral"
              title="Recolher"
              className="hidden h-8 w-8 shrink-0 place-items-center rounded-md text-[#667085] transition hover:bg-[#F3F4F6] hover:text-[#111827] md:grid"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          ) : null}
        </div>

        {/* ── Nav ────────────────────────────────────────────────── */}
        <nav
          aria-label="Navegação principal"
          className={cn(
            "flex flex-1 flex-col overflow-y-auto overflow-x-hidden py-2",
            collapsed ? "px-1.5" : "px-2"
          )}
        >
          {groups.map((group) => {
            const isOpen = collapsed ? true : openGroups[group.id] !== false;
            const hasActive = group.links.some((l) => isActive(pathname, l));

            return (
              <div key={group.id} className={cn("mb-1", collapsed && "mb-2")}>
                {/* Section header — Cloudflare style */}
                {!collapsed && (
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.id)}
                    aria-expanded={isOpen}
                    className={cn(
                      "mb-0.5 flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-left",
                      "text-[11px] font-semibold uppercase tracking-[0.06em] text-[#667085]",
                      "transition hover:bg-white hover:text-[#111827]"
                    )}
                  >
                    <ChevronDown
                      className={cn(
                        "h-3.5 w-3.5 shrink-0 transition-transform duration-150",
                        !isOpen && "-rotate-90"
                      )}
                    />
                    <span className="truncate">{group.label}</span>
                    {hasActive && !isOpen && (
                      <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#2563EB]" />
                    )}
                  </button>
                )}

                {isOpen && (
                  <div className={cn("relative", !collapsed && "ml-2 border-l border-[#E5E7EB] pl-2")}>
                    {group.links.map((link) => {
                      const active = isActive(pathname, link);
                      const Icon = link.icon;
                      return (
                        <Link
                          key={link.href + link.label}
                          href={link.href}
                          aria-label={link.label}
                          aria-current={active ? "page" : undefined}
                          onClick={() => setMobileOpen(false)}
                          className={cn(
                            "group relative flex items-center rounded-md transition-colors duration-100",
                            collapsed
                              ? "mx-auto mb-1 h-10 w-10 justify-center"
                              : "mb-0.5 gap-2.5 px-2 py-1.5",
                            active
                              ? "bg-white text-[#111827] shadow-[0_1px_2px_rgba(16,24,40,0.06)] ring-1 ring-[#E5E7EB]"
                              : "text-[#344054] hover:bg-white/80 hover:text-[#111827]"
                          )}
                        >
                          <Icon
                            className={cn(
                              "h-4 w-4 shrink-0",
                              active
                                ? "text-[#2563EB]"
                                : "text-[#667085] group-hover:text-[#344054]"
                            )}
                          />
                          {!collapsed && (
                            <span className="min-w-0 flex-1">
                              <span
                                className={cn(
                                  "block truncate text-[13px] leading-tight",
                                  active ? "font-semibold" : "font-medium"
                                )}
                              >
                                {link.label}
                              </span>
                              <span className="mt-0.5 block truncate text-[11px] leading-tight text-[#667085]">
                                {link.description}
                              </span>
                            </span>
                          )}

                          {collapsed && (
                            <span
                              role="tooltip"
                              className={cn(
                                "pointer-events-none absolute left-[calc(100%+8px)] z-50",
                                "rounded-md bg-[#111827] px-2.5 py-1.5",
                                "text-[12px] font-medium text-white shadow-lg",
                                "opacity-0 transition-opacity",
                                "group-hover:opacity-100 group-focus-visible:opacity-100"
                              )}
                            >
                              <span className="block">{link.label}</span>
                              <span className="block text-[10px] font-normal text-white/60">
                                {link.description}
                              </span>
                            </span>
                          )}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* ── Footer ─────────────────────────────────────────────── */}
        <div
          className={cn(
            "relative shrink-0 border-t border-[#E5E7EB] bg-white",
            collapsed ? "p-1.5" : "p-2"
          )}
          ref={accountRef}
        >
          <button
            type="button"
            onClick={() => setAccountOpen((v) => !v)}
            aria-expanded={accountOpen}
            aria-haspopup="menu"
            aria-label={`Conta: ${displayName}`}
            className={cn(
              "flex w-full items-center rounded-md transition hover:bg-[#F8FAFC]",
              collapsed ? "h-10 justify-center" : "gap-2.5 px-2 py-2"
            )}
          >
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#EFF6FF] text-[11px] font-semibold text-[#1D4ED8]">
              {(displayName || "U").slice(0, 1)}
            </span>
            {!collapsed && (
              <>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-[12px] font-semibold text-[#111827]">
                    {displayName}
                  </span>
                  <span className="block truncate text-[10px] text-[#667085]">
                    {role || email || "Sessão ativa"}
                  </span>
                </span>
                <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-[#667085]" />
              </>
            )}
          </button>

          {accountOpen && (
            <div
              role="menu"
              className={cn(
                "absolute z-30 overflow-hidden rounded-lg border border-[#E5E7EB] bg-white shadow-[0_12px_40px_rgba(16,24,40,0.12)]",
                collapsed
                  ? "bottom-12 left-[60px] w-[220px]"
                  : "bottom-[calc(100%+4px)] left-2 right-2"
              )}
            >
              <div className="border-b border-[#E5E7EB] px-3 py-2.5">
                <p className="truncate text-[12px] font-semibold text-[#111827]">{displayName}</p>
                <p className="truncate text-[10px] text-[#667085]">
                  {orgName}
                  {role ? ` · ${role}` : ""}
                </p>
              </div>
              <div className="p-1">
                <Link
                  href="/config"
                  role="menuitem"
                  onClick={() => {
                    setAccountOpen(false);
                    setMobileOpen(false);
                  }}
                  className="flex items-center gap-2 rounded-md px-2.5 py-2 text-[12px] text-[#344054] hover:bg-[#F8FAFC]"
                >
                  <Settings2 className="h-3.5 w-3.5 text-[#667085]" />
                  Preferências
                </Link>
                <button
                  type="button"
                  role="menuitem"
                  onClick={logout}
                  className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-[12px] text-[#344054] hover:bg-[#F8FAFC]"
                >
                  <LogOut className="h-3.5 w-3.5 text-[#667085]" />
                  Sair da conta
                </button>
              </div>
            </div>
          )}

          {collapsed && (
            <button
              type="button"
              onClick={() => setCollapsed(false)}
              title="Expandir menu"
              aria-label="Expandir menu lateral"
              className="mt-1 flex h-9 w-full items-center justify-center rounded-md text-[#667085] transition hover:bg-[#F8FAFC] hover:text-[#111827]"
            >
              <PanelLeftOpen className="h-4 w-4" />
            </button>
          )}
        </div>
      </aside>
    </>
  );
}
