"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  BriefcaseBusiness,
  ChartNoAxesCombined,
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
  icon: React.ComponentType<{ className?: string }>;
  /** Match this path and its children (except when false for exact root). */
  match?: "exact" | "prefix";
};

type NavGroup = {
  label: string;
  links: NavLink[];
};

/**
 * Hierarquia oficial da sidebar MIRA (produto comercial).
 * Rotas alinhadas às páginas existentes — não inventar links.
 */
const groups: NavGroup[] = [
  {
    label: "Visão executiva",
    links: [
      { href: "/", label: "Visão geral", icon: LayoutDashboard, match: "exact" },
    ],
  },
  {
    label: "Gestão de alunos",
    links: [
      { href: "/alunos", label: "Alunos", icon: Users, match: "prefix" },
    ],
  },
  {
    label: "Operação",
    links: [
      {
        href: "/trabalho",
        label: "Central de trabalho",
        icon: BriefcaseBusiness,
        match: "prefix",
      },
      {
        href: "/retencao",
        label: "Intervenções",
        icon: Workflow,
        match: "prefix",
      },
    ],
  },
  {
    label: "Inteligência e resultados",
    links: [
      {
        href: "/retencao/logs",
        label: "Resultados",
        icon: ChartNoAxesCombined,
        match: "prefix",
      },
    ],
  },
  {
    label: "Administração da instituição",
    links: [
      {
        href: "/conectores",
        label: "Dados e integrações",
        icon: Database,
        match: "prefix",
      },
      {
        href: "/config",
        label: "Configurações",
        icon: Settings2,
        match: "prefix",
      },
    ],
  },
];

function isActive(pathname: string, link: NavLink): boolean {
  if (link.match === "exact" || link.href === "/") {
    return pathname === "/";
  }
  // Resultados (/retencao/logs) must win over Intervenções (/retencao)
  if (link.href === "/retencao") {
    return (
      pathname === "/retencao" ||
      (pathname.startsWith("/retencao/") && !pathname.startsWith("/retencao/logs"))
    );
  }
  if (link.href === "/retencao/logs") {
    return pathname === "/retencao/logs" || pathname.startsWith("/retencao/logs/");
  }
  return pathname === link.href || pathname.startsWith(link.href + "/");
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
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

  // Close account menu on outside click
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!accountRef.current?.contains(e.target as Node)) {
        setAccountOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  // Close mobile drawer on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <>
      {/* Mobile open trigger */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Abrir menu de navegação"
        className="fixed left-3 top-3 z-40 grid h-10 w-10 place-items-center rounded-xl border border-neutral-200 bg-white text-neutral-800 shadow-sm md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Mobile backdrop */}
      {mobileOpen && (
        <button
          type="button"
          aria-label="Fechar menu de navegação"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex min-h-screen shrink-0 flex-col",
          "bg-[#0f1012] text-white",
          "transition-[width,transform] duration-200 ease-out",
          "md:sticky md:top-0 md:z-20",
          collapsed ? "w-[72px]" : "w-[256px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          "md:flex"
        )}
      >
        {/* ── Header: logo + collapse ─────────────────────────────── */}
        <div
          className={cn(
            "flex h-14 shrink-0 items-center border-b border-white/[0.06]",
            collapsed ? "justify-center px-2" : "justify-between px-4"
          )}
        >
          <div className={cn("overflow-hidden", collapsed ? "w-9" : "w-[96px]")}>
            <Image
              src="/mira-logo.svg"
              alt="MIRA"
              width={96}
              height={24}
              className="h-auto w-[96px] max-w-none"
              priority
            />
          </div>

          {mobileOpen && (
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              aria-label="Fechar menu"
              className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-white/55 transition hover:bg-white/[0.08] hover:text-white md:hidden"
            >
              <X className="h-4 w-4" />
            </button>
          )}

          {!collapsed && !mobileOpen && (
            <button
              type="button"
              onClick={() => setCollapsed(true)}
              aria-label="Recolher menu lateral"
              title="Recolher"
              className="hidden h-8 w-8 shrink-0 place-items-center rounded-lg text-white/45 transition hover:bg-white/[0.08] hover:text-white md:grid"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* ── Optional institutional context (compact) ────────────── */}
        {!collapsed && (
          <div className="px-3 pt-3">
            <p
              className="truncate px-2 text-[10px] font-medium uppercase tracking-[0.16em] text-white/35"
              title={orgName}
            >
              {orgName}
            </p>
          </div>
        )}

        {/* ── Main navigation ─────────────────────────────────────── */}
        <nav
          aria-label="Navegação principal"
          className={cn(
            "flex flex-1 flex-col overflow-y-auto py-3",
            collapsed ? "gap-4 px-2" : "gap-5 px-3"
          )}
        >
          {groups.map((group) => (
            <div key={group.label}>
              {!collapsed && (
                <p className="mb-1.5 px-2.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/35">
                  {group.label}
                </p>
              )}
              <div className="space-y-0.5">
                {group.links.map((link) => {
                  const active = isActive(pathname, link);
                  const Icon = link.icon;
                  return (
                    <Link
                      key={link.href + link.label}
                      href={link.href}
                      title={collapsed ? link.label : undefined}
                      aria-label={link.label}
                      aria-current={active ? "page" : undefined}
                      onClick={() => setMobileOpen(false)}
                      className={cn(
                        "group relative flex shrink-0 items-center rounded-lg transition-colors duration-150",
                        collapsed
                          ? "h-11 justify-center px-0"
                          : "h-10 gap-3 px-2.5 text-[13px]",
                        active
                          ? "bg-white/[0.09] font-medium text-white"
                          : "text-white/60 hover:bg-white/[0.05] hover:text-white/90"
                      )}
                    >
                      {/* Active indicator — left rail in brand blue */}
                      {active && (
                        <span
                          aria-hidden
                          className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--brand-indigo)]"
                        />
                      )}
                      <Icon
                        className={cn(
                          "h-[18px] w-[18px] shrink-0 transition-colors",
                          active
                            ? "text-[var(--brand-indigo)]"
                            : "text-white/45 group-hover:text-white/75"
                        )}
                      />
                      {!collapsed && (
                        <span className="truncate leading-none">{link.label}</span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* ── Footer: account ─────────────────────────────────────── */}
        <div
          className={cn(
            "shrink-0 border-t border-white/[0.06]",
            collapsed ? "p-2" : "p-3"
          )}
          ref={accountRef}
        >
          <button
            type="button"
            onClick={() => setAccountOpen((v) => !v)}
            aria-expanded={accountOpen}
            aria-haspopup="menu"
            aria-label={`Conta: ${displayName}`}
            title={collapsed ? displayName : undefined}
            className={cn(
              "flex w-full items-center rounded-lg transition",
              "hover:bg-white/[0.06]",
              collapsed ? "h-11 justify-center" : "gap-2.5 px-2 py-2"
            )}
          >
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white/[0.1] text-[11px] font-semibold uppercase tracking-wide text-white/80">
              {(displayName || "U").slice(0, 1)}
            </span>
            {!collapsed && (
              <>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-[12px] font-medium leading-tight text-white">
                    {displayName}
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] text-white/40">
                    {role ? `${role}` : email || "Sessão ativa"}
                  </span>
                </span>
                <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-white/35" />
              </>
            )}
          </button>

          {accountOpen && (
            <div
              role="menu"
              className={cn(
                "absolute z-30 overflow-hidden rounded-xl border border-white/[0.08] bg-[#1a1c1f] shadow-2xl",
                collapsed
                  ? "bottom-14 left-[68px] w-[200px]"
                  : "bottom-[calc(100%+4px)] left-3 right-3"
              )}
            >
              <div className="border-b border-white/[0.06] px-3 py-2.5">
                <p className="truncate text-[12px] font-medium text-white">
                  {displayName}
                </p>
                <p className="mt-0.5 truncate text-[10px] text-white/40">
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
                  className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[12px] text-white/70 transition hover:bg-white/[0.06] hover:text-white"
                >
                  <Settings2 className="h-3.5 w-3.5 text-white/40" />
                  Preferências
                </Link>
                <button
                  type="button"
                  role="menuitem"
                  onClick={logout}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[12px] text-white/70 transition hover:bg-white/[0.06] hover:text-white"
                >
                  <LogOut className="h-3.5 w-3.5 text-white/40" />
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
              className="mt-1 flex h-9 w-full items-center justify-center rounded-lg text-white/45 transition hover:bg-white/[0.06] hover:text-white"
            >
              <PanelLeftOpen className="h-4 w-4" />
            </button>
          )}
        </div>
      </aside>
    </>
  );
}
