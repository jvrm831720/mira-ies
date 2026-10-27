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
  match?: "exact" | "prefix";
};

type NavGroup = {
  label: string;
  links: NavLink[];
};

/**
 * Hierarquia oficial da sidebar MIRA.
 * Rotas alinhadas às páginas existentes.
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
    links: [{ href: "/alunos", label: "Alunos", icon: Users, match: "prefix" }],
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
      if (!accountRef.current?.contains(e.target as Node)) {
        setAccountOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <>
      {/* Mobile trigger */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Abrir menu de navegação"
        className="fixed left-3 top-3 z-40 grid h-10 w-10 place-items-center rounded-xl border border-[#E5E7EB] bg-white text-[#111827] shadow-sm md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Fechar menu de navegação"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-40 bg-[#111827]/40 backdrop-blur-[2px] md:hidden"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex min-h-screen shrink-0 flex-col",
          "border-r border-[#E5E7EB] bg-white text-[#111827]",
          "transition-[width,transform] duration-200 ease-out",
          "md:sticky md:top-0 md:z-20",
          collapsed ? "w-[72px]" : "w-[260px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          "md:flex"
        )}
      >
        {/* Header */}
        <div
          className={cn(
            "flex h-14 shrink-0 items-center",
            collapsed ? "justify-center px-2" : "justify-between gap-2 px-4"
          )}
        >
          <div
            className={cn(
              "flex min-w-0 items-center gap-2.5 overflow-hidden",
              collapsed && "justify-center"
            )}
          >
            <span
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#111827] text-white shadow-sm"
              aria-hidden
            >
              <Image
                src="/favicon.svg"
                alt=""
                width={18}
                height={18}
                className="h-[18px] w-[18px] brightness-0 invert"
                priority
              />
            </span>
            {!collapsed && (
              <div className="min-w-0">
                <Image
                  src="/mira-logo.svg"
                  alt="MIRA"
                  width={72}
                  height={20}
                  className="h-5 w-auto max-w-[88px] object-contain object-left brightness-0"
                  priority
                />
              </div>
            )}
          </div>

          {mobileOpen && (
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              aria-label="Fechar menu"
              className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-[#667085] transition hover:bg-[#F3F4F6] hover:text-[#111827] md:hidden"
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
              className="hidden h-8 w-8 shrink-0 place-items-center rounded-full text-[#667085] transition hover:bg-[#F3F4F6] hover:text-[#111827] md:grid"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          )}

          {collapsed && (
            <button
              type="button"
              onClick={() => setCollapsed(false)}
              aria-label="Expandir menu lateral"
              title="Expandir"
              className="absolute right-2 top-3 hidden h-7 w-7 place-items-center rounded-full border border-[#E5E7EB] bg-white text-[#667085] shadow-sm transition hover:bg-[#F8FAFC] hover:text-[#111827] md:grid"
            >
              <PanelLeftOpen className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {!collapsed && (
          <div className="px-4 pb-1">
            <p
              className="truncate text-[10px] font-semibold uppercase tracking-[0.14em] text-[#667085]"
              title={orgName}
            >
              {orgName}
            </p>
          </div>
        )}

        <nav
          aria-label="Navegação principal"
          className={cn(
            "flex flex-1 flex-col overflow-y-auto overflow-x-hidden py-3",
            collapsed ? "gap-3 px-2" : "gap-5 px-3"
          )}
        >
          {groups.map((group) => (
            <div key={group.label}>
              {!collapsed && (
                <p className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#667085]">
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
                      aria-label={link.label}
                      aria-current={active ? "page" : undefined}
                      onClick={() => setMobileOpen(false)}
                      className={cn(
                        "group relative flex shrink-0 items-center rounded-xl transition-colors duration-150",
                        collapsed
                          ? "h-11 justify-center px-0"
                          : "h-10 gap-3 px-3 text-[13px] leading-none",
                        active
                          ? "bg-[#F3F4F6] font-semibold text-[#111827]"
                          : "font-medium text-[#667085] hover:bg-[#F8FAFC] hover:text-[#111827]"
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-[18px] w-[18px] shrink-0 transition-colors",
                          active
                            ? "text-[#2563EB]"
                            : "text-[#667085] group-hover:text-[#111827]"
                        )}
                      />
                      {!collapsed && <span className="truncate">{link.label}</span>}

                      {collapsed && (
                        <span
                          role="tooltip"
                          className={cn(
                            "pointer-events-none absolute left-[calc(100%+10px)] z-50",
                            "whitespace-nowrap rounded-lg bg-[#111827] px-2.5 py-1.5",
                            "text-[12px] font-medium text-white shadow-lg",
                            "opacity-0 transition-opacity duration-150",
                            "group-hover:opacity-100 group-focus-visible:opacity-100"
                          )}
                        >
                          {link.label}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div
          className={cn(
            "relative shrink-0 border-t border-[#E5E7EB]",
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
            className={cn(
              "flex w-full items-center rounded-xl transition",
              "hover:bg-[#F8FAFC]",
              collapsed ? "h-11 justify-center" : "gap-2.5 px-2 py-2"
            )}
          >
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#EFF6FF] text-[11px] font-semibold uppercase tracking-wide text-[#1D4ED8]">
              {(displayName || "U").slice(0, 1)}
            </span>
            {!collapsed && (
              <>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-[12px] font-semibold leading-tight text-[#111827]">
                    {displayName}
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] text-[#667085]">
                    {role ? `${role}` : email || "Sessão ativa"}
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
                "absolute z-30 overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-[0_16px_48px_rgba(17,24,39,0.12)]",
                collapsed
                  ? "bottom-14 left-[68px] w-[220px]"
                  : "bottom-[calc(100%+6px)] left-3 right-3"
              )}
            >
              <div className="border-b border-[#E5E7EB] px-3 py-2.5">
                <p className="truncate text-[12px] font-semibold text-[#111827]">
                  {displayName}
                </p>
                <p className="mt-0.5 truncate text-[10px] text-[#667085]">
                  {orgName}
                  {role ? ` · ${role}` : ""}
                </p>
              </div>
              <div className="p-1.5">
                <Link
                  href="/config"
                  role="menuitem"
                  onClick={() => {
                    setAccountOpen(false);
                    setMobileOpen(false);
                  }}
                  className="flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-[12px] font-medium text-[#667085] transition hover:bg-[#F8FAFC] hover:text-[#111827]"
                >
                  <Settings2 className="h-3.5 w-3.5 text-[#667085]" />
                  Preferências
                </Link>
                <button
                  type="button"
                  role="menuitem"
                  onClick={logout}
                  className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-[12px] font-medium text-[#667085] transition hover:bg-[#F8FAFC] hover:text-[#111827]"
                >
                  <LogOut className="h-3.5 w-3.5 text-[#667085]" />
                  Sair da conta
                </button>
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
