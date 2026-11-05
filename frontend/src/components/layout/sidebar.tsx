"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeftRight,
  BarChart3,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  Check,
  ChevronDown,
  ChevronsUpDown,
  CreditCard,
  Database,
  FileClock,
  FileUp,
  House,
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
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { listWorkspaces, switchWorkspace } from "@/lib/workspaces-api";
import type { WorkspaceItem } from "@/lib/workspaces-api";

type NavLink = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  keywords?: string;
  exact?: boolean;
};

type NavGroup = {
  id: string;
  label: string;
  links: NavLink[];
};

const groups: NavGroup[] = [
  {
    id: "workspace",
    label: "Workspace",
    links: [
      { href: "/", label: "Visão geral", icon: House, exact: true, keywords: "início painel dashboard" },
      { href: "/membros", label: "Equipe", icon: Users, keywords: "membros convites pessoas" },
      { href: "/config", label: "Configurações", icon: Settings2, keywords: "preferências instituição acesso" },
      { href: "/membros/cargos", label: "Cargos e permissões", icon: ShieldCheck, keywords: "rbac funções acesso" },
    ],
  },
  {
    id: "permanencia",
    label: "Permanência",
    links: [
      { href: "/alunos", label: "Alunos", icon: Users, keywords: "estudantes base acadêmica", },
      { href: "/alunos/grupos", label: "Grupos", icon: BookOpenCheck, keywords: "segmentos listas alunos" },
      { href: "/monitoramento", label: "Monitoramento", icon: Activity, keywords: "risco acompanhamento sinais" },
      { href: "/resultados", label: "Resultados", icon: BarChart3, keywords: "indicadores evasão rematrícula" },
    ],
  },
  {
    id: "acoes",
    label: "Ações",
    links: [
      { href: "/trabalho", label: "Central de trabalho", icon: BriefcaseBusiness, keywords: "fila tarefas pendências" },
      { href: "/retencao", label: "Intervenções", icon: Workflow, keywords: "jornadas ações retenção" },
      { href: "/campanhas", label: "Campanhas", icon: FileClock, keywords: "comunicação aprovações" },
      { href: "/retencao/logs", label: "Histórico de contatos", icon: Activity, keywords: "execução entregas logs" },
    ],
  },
  {
    id: "dados",
    label: "Dados",
    links: [
      { href: "/importar", label: "Importar dados", icon: FileUp, keywords: "upload csv xlsx base" },
      { href: "/importacoes", label: "Histórico de importações", icon: FileClock, keywords: "arquivos processamento" },
      { href: "/conectores", label: "Integrações", icon: Database, keywords: "sistemas conectores fontes" },
    ],
  },
  {
    id: "plano",
    label: "Plano MIRA",
    links: [
      { href: "/fatura", label: "Plano e cobrança", icon: CreditCard, keywords: "assinatura fatura créditos pagamento" },
    ],
  },
];

function isActive(pathname: string, link: NavLink): boolean {
  if (link.exact || link.href === "/") return pathname === "/";
  if (link.href === "/alunos") {
    return pathname === "/alunos" || (pathname.startsWith("/alunos/") && !pathname.startsWith("/alunos/grupos"));
  }
  if (link.href === "/retencao") {
    return pathname === "/retencao" || (pathname.startsWith("/retencao/") && !pathname.startsWith("/retencao/logs"));
  }
  return pathname === link.href || pathname.startsWith(link.href + "/");
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [navQuery, setNavQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const accountRef = useRef<HTMLDivElement>(null);

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
    onSuccess: (result) => {
      toast.success(`Workspace alterado para ${result.tenant_name}.`);
      queryClient.clear();
      window.location.assign("/");
    },
    onError: (error: Error) => toast.error(error.message || "Não foi possível trocar de workspace."),
  });

  const orgName = me.data?.tenant_name || "Seu workspace";
  const displayName = me.data?.display_name || me.data?.email || "Conta";
  const role = me.data?.role;
  const email = me.data?.email;

  const filteredGroups = useMemo(() => {
    const q = navQuery.trim().toLocaleLowerCase("pt-BR");
    if (!q) return groups;
    return groups.map((group) => ({
      ...group,
      links: group.links.filter((link) =>
        [link.label, link.keywords || "", group.label].some((value) => value.toLocaleLowerCase("pt-BR").includes(q))
      ),
    })).filter((group) => group.links.length > 0);
  }, [navQuery]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCollapsed(false);
        setMobileOpen(true);
        window.setTimeout(() => searchRef.current?.focus(), 0);
      }
      if (event.key === "Escape") {
        setWorkspaceOpen(false);
        setAccountOpen(false);
        setMobileOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    const onDocumentClick = (event: MouseEvent) => {
      if (!workspaceRef.current?.contains(event.target as Node)) setWorkspaceOpen(false);
      if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false);
    };
    document.addEventListener("mousedown", onDocumentClick);
    return () => document.removeEventListener("mousedown", onDocumentClick);
  }, []);

  useEffect(() => setMobileOpen(false), [pathname]);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  const workspaceItems = workspaces.data?.workspaces || [];

  return (
    <>
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Abrir navegação"
        className="fixed left-3 top-3 z-40 grid h-9 w-9 place-items-center rounded-lg border border-[#E5E7EB] bg-white text-[#344054] shadow-sm md:hidden"
      >
        <Menu className="h-4 w-4" />
      </button>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Fechar navegação"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-40 bg-[#101828]/35 md:hidden"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-dvh min-h-0 shrink-0 flex-col border-r border-[#E7E7E9] bg-white text-[#202124]",
          "transition-[width,transform] duration-200 ease-out md:sticky md:top-0 md:z-20 md:h-screen md:translate-x-0",
          collapsed ? "w-[64px]" : "w-[248px]",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className={cn("shrink-0 px-3 pt-3", collapsed && "px-2")}>
          <div className="relative" ref={workspaceRef}>
            <button
              type="button"
              onClick={() => setWorkspaceOpen((value) => !value)}
              aria-expanded={workspaceOpen}
              aria-haspopup="listbox"
              className={cn(
                "flex w-full items-center rounded-lg px-2 py-2 text-left transition hover:bg-[#F7F7F8]",
                collapsed ? "justify-center" : "gap-2.5"
              )}
            >
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#171717] text-white">
                <Image src="/mira-mark.svg" alt="MIRA" width={21} height={14} className="h-[14px] w-auto brightness-0 invert" priority />
              </span>
              {!collapsed && (
                <>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-[#202124]">{orgName}</span>
                    <span className="mt-0.5 block text-[11px] text-[#85858B]">Workspace MIRA</span>
                  </span>
                  <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-[#85858B]" />
                </>
              )}
            </button>

            {workspaceOpen && (
              <div className={cn(
                "absolute z-50 overflow-hidden rounded-xl border border-[#E7E7E9] bg-white shadow-[0_12px_40px_rgba(16,24,40,0.14)]",
                collapsed ? "left-[calc(100%+8px)] top-0 w-[260px]" : "left-0 right-0 top-[calc(100%+6px)]"
              )}>
                <div className="border-b border-[#EEEEF0] px-3 py-2.5">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#85858B]">Seus workspaces</p>
                </div>
                <div className="max-h-[280px] overflow-y-auto p-1.5">
                  {workspaces.isLoading ? (
                    <p className="px-2.5 py-3 text-[12px] text-[#85858B]">Carregando workspaces…</p>
                  ) : workspaceItems.length ? workspaceItems.map((item) => (
                    <button
                      key={item.membership_id || item.tenant_id}
                      type="button"
                      disabled={item.is_current || switcher.isPending}
                      onClick={() => switcher.mutate(item)}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition",
                        item.is_current ? "bg-[#F5F5F6]" : "hover:bg-[#F7F7F8]"
                      )}
                    >
                      <Building2 className="h-4 w-4 shrink-0 text-[#77777D]" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12px] font-medium text-[#29292D]">{item.tenant_name}</span>
                        <span className="block truncate text-[10px] text-[#85858B]">{item.role}</span>
                      </span>
                      {item.is_current ? <Check className="h-4 w-4 text-[#266DF0]" /> : <ArrowLeftRight className="h-3.5 w-3.5 text-[#A0A0A5]" />}
                    </button>
                  )) : (
                    <p className="px-2.5 py-3 text-[12px] leading-relaxed text-[#85858B]">
                      {workspaces.isError ? "Não foi possível carregar outros workspaces." : "Este usuário ainda tem acesso a um único workspace."}
                    </p>
                  )}
                </div>
                <div className="border-t border-[#EEEEF0] px-3 py-2">
                  <p className="text-[10px] text-[#85858B]">O acesso depende das permissões da sua conta.</p>
                </div>
              </div>
            )}
          </div>

          {!collapsed ? (
            <div className="relative mt-3 pb-3">
              <Search className="pointer-events-none absolute left-3 top-[13px] h-3.5 w-3.5 text-[#929299]" />
              <input
                ref={searchRef}
                type="search"
                value={navQuery}
                onChange={(event) => setNavQuery(event.target.value)}
                placeholder="Buscar"
                aria-label="Buscar na navegação"
                className="h-9 w-full rounded-lg border border-[#E7E7E9] bg-[#FAFAFA] pl-9 pr-14 text-[12px] text-[#29292D] outline-none placeholder:text-[#929299] focus:border-[#B8B8BE] focus:bg-white"
              />
              <kbd className="absolute right-2.5 top-[9px] rounded border border-[#E7E7E9] bg-white px-1.5 py-0.5 text-[9px] text-[#929299]">⌘ K</kbd>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => { setCollapsed(false); setMobileOpen(true); window.setTimeout(() => searchRef.current?.focus(), 0); }}
              aria-label="Buscar"
              className="mx-auto mt-3 mb-3 grid h-9 w-9 place-items-center rounded-lg text-[#77777D] hover:bg-[#F5F5F6]"
            >
              <Search className="h-4 w-4" />
            </button>
          )}
        </div>

        <nav aria-label="Navegação principal" className={cn("min-h-0 flex-1 overflow-y-auto overflow-x-hidden pb-3", collapsed ? "px-2" : "px-3")}>
          <div className="flex flex-col gap-4">
            {filteredGroups.map((group) => (
              <section key={group.id}>
                {!collapsed && (
                  <h2 className="mb-1 px-2.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.11em] text-[#929299]">
                    {group.label}
                  </h2>
                )}
                <div className="space-y-0.5">
                  {group.links.map((link) => {
                    const active = isActive(pathname, link);
                    const Icon = link.icon;
                    return (
                      <Link
                        key={link.href}
                        href={link.href}
                        aria-label={link.label}
                        aria-current={active ? "page" : undefined}
                        onClick={() => setMobileOpen(false)}
                        title={collapsed ? link.label : undefined}
                        className={cn(
                          "group flex h-9 items-center rounded-lg text-[12px] transition-colors",
                          collapsed ? "justify-center px-0" : "gap-2.5 px-2.5",
                          active ? "bg-[#F0F0F1] font-semibold text-[#202124]" : "font-medium text-[#55555C] hover:bg-[#F7F7F8] hover:text-[#202124]"
                        )}
                      >
                        <Icon className={cn("h-[16px] w-[16px] shrink-0", active ? "text-[#202124]" : "text-[#85858B] group-hover:text-[#55555C]")} />
                        {!collapsed && <span className="min-w-0 flex-1 truncate">{link.label}</span>}
                      </Link>
                    );
                  })}
                </div>
              </section>
            ))}
            {!collapsed && filteredGroups.length === 0 && (
              <p className="px-2.5 py-4 text-center text-[12px] text-[#85858B]">Nenhum item encontrado.</p>
            )}
          </div>
        </nav>

        <div className={cn("shrink-0 border-t border-[#EEEEF0] bg-white", collapsed ? "p-2" : "p-2.5")} ref={accountRef}>
          <div className="relative">
            <button
              type="button"
              onClick={() => setAccountOpen((value) => !value)}
              aria-expanded={accountOpen}
              aria-haspopup="menu"
              className={cn("flex w-full items-center rounded-lg py-2 transition hover:bg-[#F7F7F8]", collapsed ? "justify-center" : "gap-2.5 px-2")}
            >
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#EDEDF0] text-[10px] font-semibold text-[#55555C]">{displayName.slice(0, 1).toUpperCase()}</span>
              {!collapsed && (
                <>
                  <span className="min-w-0 flex-1 text-left">
                    <span className="block truncate text-[11px] font-semibold text-[#29292D]">{displayName}</span>
                    <span className="block truncate text-[10px] text-[#929299]">{role || email || "Conta"}</span>
                  </span>
                  <ChevronsUpDown className="h-3.5 w-3.5 text-[#929299]" />
                </>
              )}
            </button>
            {accountOpen && (
              <div role="menu" className={cn("absolute z-50 overflow-hidden rounded-xl border border-[#E7E7E9] bg-white shadow-[0_12px_40px_rgba(16,24,40,0.14)]", collapsed ? "bottom-0 left-[calc(100%+8px)] w-[220px]" : "bottom-[calc(100%+8px)] left-0 right-0")}>
                <div className="border-b border-[#EEEEF0] px-3 py-2.5">
                  <p className="truncate text-[12px] font-semibold text-[#29292D]">{displayName}</p>
                  <p className="truncate text-[10px] text-[#85858B]">{email || role || ""}</p>
                </div>
                <button type="button" role="menuitem" onClick={logout} className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[12px] text-[#55555C] hover:bg-[#F7F7F8]">
                  <LogOut className="h-4 w-4" /> Sair da conta
                </button>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? "Expandir navegação" : "Recolher navegação"}
            className={cn("mt-1 hidden h-8 w-full items-center justify-center gap-2 rounded-lg text-[#85858B] transition hover:bg-[#F7F7F8] hover:text-[#29292D] md:flex", !collapsed && "text-[11px] font-medium")}
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <><PanelLeftClose className="h-4 w-4" /> Recolher menu</>}
          </button>
        </div>
      </aside>
    </>
  );
}
