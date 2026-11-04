"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BriefcaseBusiness,
  Building2,
  ChartNoAxesCombined,
  ClipboardCheck,
  ChevronDown,
  ChevronsUpDown,
  Database,
  LayoutDashboard,
  Layers,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings2,
  ShieldCheck,
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
      {
        href: "/alunos/grupos",
        label: "Grupos de alunos",
        description: "Segmentos por sinais e critérios",
        icon: Layers,
        match: "prefix",
      },
      {
        href: "/monitoramento",
        label: "Monitoramento",
        description: "Prioridades e risco atual",
        icon: Activity,
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
        description: "Planejamento, aprovação e execução",
        icon: Workflow,
        match: "prefix",
      },
      {
        href: "/campanhas",
        label: "Campanhas inteligentes",
        description: "Propostas, revisão e aprovação",
        icon: ClipboardCheck,
        match: "prefix",
      },
    ],
  },
  {
    id: "inteligencia",
    label: "Inteligência e resultados",
      links: [
        {
          href: "/resultados",
          label: "Resultados de permanência",
          description: "Rematrícula, evasão e outcomes acadêmicos",
          icon: ChartNoAxesCombined,
          match: "prefix",
        },
        {
          href: "/retencao/logs",
          label: "Histórico de contatos",
          description: "Execução e entrega de intervenções",
          icon: Activity,
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
      {
        href: "/membros",
        label: "Membros",
        description: "Equipe e convites",
        icon: Users,
        match: "exact",
      },
      {
        href: "/membros/cargos",
        label: "Cargos e permissões",
        description: "Acesso por função e módulo",
        icon: ShieldCheck,
        match: "prefix",
      },
    ],
  },
];

function isActive(pathname: string, link: NavLink): boolean {
  if (link.match === "exact" || link.href === "/") return pathname === "/";
  if (link.href === "/alunos") {
    return (
      pathname === "/alunos" ||
      (pathname.startsWith("/alunos/") && !pathname.startsWith("/alunos/grupos"))
    );
  }
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
  const [orgOpen, setOrgOpen] = useState(false);
  const [navQuery, setNavQuery] = useState("");
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(groups.map((g) => [g.id, true]))
  );
  const accountRef = useRef<HTMLDivElement>(null);
  const orgRef = useRef<HTMLDivElement>(null);

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

  const filteredGroups = useMemo(() => {
    const q = navQuery.trim().toLocaleLowerCase("pt-BR");
    if (!q) return groups;
    return groups
      .map((g) => ({
        ...g,
        links: g.links.filter(
          (l) =>
            l.label.toLocaleLowerCase("pt-BR").includes(q) ||
            l.description.toLocaleLowerCase("pt-BR").includes(q) ||
            g.label.toLocaleLowerCase("pt-BR").includes(q)
        ),
      }))
      .filter((g) => g.links.length > 0);
  }, [navQuery]);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!accountRef.current?.contains(e.target as Node)) setAccountOpen(false);
      if (!orgRef.current?.contains(e.target as Node)) setOrgOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

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
          "fixed inset-y-0 left-0 z-50 flex h-dvh min-h-0 shrink-0 flex-col",
          "border-r border-[#E5E7EB] bg-[#F8FAFC] text-[#111827]",
          "transition-[width,transform] duration-200 ease-out",
          "md:sticky md:top-0 md:z-20 md:h-screen",
          collapsed ? "w-[72px]" : "w-[272px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          "md:flex"
        )}
      >
        <div
          className={cn(
            "shrink-0 border-b border-[#E5E7EB] bg-[#F8FAFC]",
            collapsed ? "px-2 py-3" : "px-3 py-4"
          )}
        >
          <div className={cn("relative", collapsed && "flex justify-center")} ref={orgRef}>
            <button
              type="button"
              onClick={() => setOrgOpen((v) => !v)}
              aria-expanded={orgOpen}
              aria-haspopup="listbox"
              aria-label={`Organização: ${orgName}`}
              className={cn(
                "flex w-full items-center rounded-lg transition hover:bg-white",
                collapsed ? "h-10 w-10 justify-center" : "gap-2.5 px-2 py-2"
              )}
            >
              {collapsed ? (
                <Image
                  src="/mira-mark.svg"
                  alt="MIRA"
                  width={32}
                  height={20}
                  className="h-5 w-auto"
                  priority
                />
              ) : (
                <>
                  <Image
                    src="/mira-mark.svg"
                    alt=""
                    width={36}
                    height={22}
                    className="h-[22px] w-auto shrink-0"
                    priority
                  />
                  <span className="min-w-0 flex-1 text-left">
                    <span className="block truncate text-[13px] font-semibold text-[#111827]">
                      {orgName}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px] text-[#667085]">MIRA</span>
                  </span>
                  <ChevronsUpDown className="h-4 w-4 shrink-0 text-[#667085]" />
                </>
              )}
            </button>

            {orgOpen && (
              <div
                role="listbox"
                className={cn(
                  "absolute z-40 overflow-hidden rounded-xl border border-[#E5E7EB] bg-white shadow-[0_12px_40px_rgba(16,24,40,0.12)]",
                  collapsed
                    ? "left-[calc(100%+8px)] top-0 w-[240px]"
                    : "left-0 right-0 top-[calc(100%+6px)]"
                )}
              >
                <div className="border-b border-[#E5E7EB] px-3 py-2">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#98A2B3]" />
                    <input
                      type="search"
                      placeholder="Buscar contas…"
                      className="h-9 w-full rounded-lg border border-[#E5E7EB] bg-[#F8FAFC] pl-8 pr-2 text-[12px] text-[#111827] outline-none placeholder:text-[#98A2B3] focus:border-[#2563EB]"
                      aria-label="Buscar contas"
                    />
                  </div>
                </div>
                <div className="p-1.5">
                  <button
                    type="button"
                    role="option"
                    aria-selected
                    className="flex w-full items-center gap-2.5 rounded-lg bg-[#F8FAFC] px-2.5 py-2 text-left"
                    onClick={() => setOrgOpen(false)}
                  >
                    <Building2 className="h-4 w-4 text-[#2563EB]" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12px] font-semibold text-[#111827]">
                        {orgName}
                      </span>
                      <span className="block truncate text-[10px] text-[#667085]">Instituição ativa</span>
                    </span>
                    <span className="text-[11px] font-medium text-[#2563EB]">Atual</span>
                  </button>
                </div>
                <p className="border-t border-[#E5E7EB] px-3 py-2 text-[10px] leading-relaxed text-[#667085]">
                  Alternância entre instituições depende do acesso provisionado na sua conta.
                </p>
              </div>
            )}
          </div>

          {mobileOpen && (
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              aria-label="Fechar menu"
              className="mt-2 grid h-8 w-8 place-items-center rounded-md text-[#667085] hover:bg-white md:hidden"
            >
              <X className="h-4 w-4" />
            </button>
          )}

          {!collapsed && (
            <div className="relative mt-3">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#98A2B3]" />
              <input
                type="search"
                value={navQuery}
                onChange={(e) => setNavQuery(e.target.value)}
                placeholder="Pesquisa rápida…"
                aria-label="Pesquisar na navegação"
                className="h-10 w-full rounded-lg border border-[#E5E7EB] bg-white pl-9 pr-3 text-[13px] text-[#111827] outline-none placeholder:text-[#98A2B3] focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/15"
              />
            </div>
          )}
        </div>

        <nav
          aria-label="Navegação principal"
          className={cn(
            "min-h-0 flex-1 overflow-y-auto overflow-x-hidden",
            collapsed ? "px-2 py-3" : "px-3 py-4"
          )}
        >
          <div className={cn("flex flex-col", collapsed ? "gap-2" : "gap-4")}>
            {filteredGroups.map((group) => {
              const isOpen = collapsed || navQuery ? true : openGroups[group.id] !== false;
              const hasActive = group.links.some((l) => isActive(pathname, l));

              return (
                <div key={group.id}>
                  {!collapsed && (
                    <button
                      type="button"
                      onClick={() => toggleGroup(group.id)}
                      aria-expanded={isOpen}
                      className={cn(
                        "mb-1.5 flex w-full items-center gap-1.5 rounded-lg px-2.5 py-2 text-left",
                        "text-[11px] font-semibold uppercase tracking-[0.08em] text-[#667085]",
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
                    <div
                      className={cn(
                        "relative space-y-1",
                        !collapsed && "ml-2.5 border-l border-[#E5E7EB] pl-2.5"
                      )}
                    >
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
                              "group relative flex items-center rounded-lg transition-colors duration-100",
                              collapsed
                                ? "mx-auto h-11 w-11 justify-center"
                                : "gap-3 px-2.5 py-2.5",
                              active
                                ? "bg-white text-[#111827] shadow-sm ring-1 ring-[#E5E7EB]"
                                : "text-[#344054] hover:bg-white hover:text-[#111827]"
                            )}
                          >
                            <Icon
                              className={cn(
                                "h-[18px] w-[18px] shrink-0",
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
                                  "pointer-events-none absolute left-[calc(100%+10px)] z-50",
                                  "rounded-lg bg-[#111827] px-2.5 py-1.5",
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

            {!collapsed && filteredGroups.length === 0 && (
              <p className="px-2.5 py-4 text-center text-[12px] text-[#667085]">
                Nenhum módulo encontrado para “{navQuery}”.
              </p>
            )}
          </div>
        </nav>

        <div
          className={cn(
            "relative shrink-0 border-t border-[#E5E7EB] bg-[#F8FAFC]",
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
              "flex w-full items-center rounded-lg transition hover:bg-white",
              collapsed ? "h-11 justify-center" : "gap-2.5 px-2 py-2.5"
            )}
          >
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#EFF6FF] text-[11px] font-semibold text-[#2563EB]">
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
                "absolute z-40 overflow-hidden rounded-xl border border-[#E5E7EB] bg-white shadow-[0_12px_40px_rgba(16,24,40,0.12)]",
                collapsed
                  ? "left-[calc(100%+8px)] bottom-0 w-[220px]"
                  : "bottom-[calc(100%+8px)] left-0 right-0"
              )}
            >
              <div className="border-b border-[#E5E7EB] px-3 py-2.5">
                <p className="truncate text-[12px] font-semibold text-[#111827]">{displayName}</p>
                <p className="truncate text-[11px] text-[#667085]">{email || role || ""}</p>
              </div>
              <div className="p-1.5">
                <Link
                  href="/config"
                  role="menuitem"
                  onClick={() => setAccountOpen(false)}
                  className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-[12px] font-medium text-[#344054] hover:bg-[#F8FAFC]"
                >
                  <Settings2 className="h-4 w-4" /> Configurações
                </Link>
                <button
                  type="button"
                  role="menuitem"
                  onClick={logout}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[12px] font-medium text-[#B42318] hover:bg-[#FEF3F2]"
                >
                  <LogOut className="h-4 w-4" /> Sair
                </button>
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
            className={cn(
              "mt-2 hidden w-full items-center justify-center gap-2 rounded-lg border border-[#E5E7EB] bg-white text-[#667085] transition hover:bg-[#F8FAFC] hover:text-[#111827] md:flex",
              collapsed ? "h-10" : "h-9 px-2 text-[11px] font-medium"
            )}
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <>
                <PanelLeftClose className="h-4 w-4" />
                Recolher
              </>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
