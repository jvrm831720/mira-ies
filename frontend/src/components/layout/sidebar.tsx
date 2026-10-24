"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Building2, ChevronsUpDown, LayoutDashboard, LogOut, MessageSquareHeart,
  PanelLeftClose, PanelLeftOpen, Plug, Receipt, Settings, Upload, UserCog, Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/lib/auth";
import { api } from "@/lib/api";

const groups = [
  { label: "Acompanhar", links: [
    { href: "/", label: "Visão geral", icon: LayoutDashboard },
    { href: "/alunos", label: "Alunos", icon: Users },
    { href: "/retencao", label: "Retenção", icon: MessageSquareHeart },
  ]},
  { label: "Operar", links: [
    { href: "/importar", label: "Importar dados", icon: Upload },
    { href: "/conectores", label: "Conectores", icon: Plug },
  ]},
  { label: "Administrar", links: [
    { href: "/membros", label: "Membros", icon: UserCog },
    { href: "/fatura", label: "Fatura", icon: Receipt },
    { href: "/config", label: "Configurações", icon: Settings },
  ]},
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [orgOpen, setOrgOpen] = useState(false);
  const orgRef = useRef<HTMLDivElement>(null);
  const me = useQuery({ queryKey: ["org-me"], queryFn: () => api.me(), retry: false, staleTime: 60_000 });
  const orgName = me.data?.tenant_name || "Sua instituição";
  const displayName = me.data?.display_name || me.data?.email || "Conta";
  const role = me.data?.role;

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!orgRef.current?.contains(e.target as Node)) setOrgOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <aside className={cn(
      "hidden min-h-screen shrink-0 flex-col bg-[#1a1a1a] text-white transition-[width] duration-200 ease-out md:flex",
      collapsed ? "w-[76px]" : "w-[236px]"
    )}>
      <div className={cn("flex h-[72px] shrink-0 items-center", collapsed ? "justify-center px-2" : "justify-between px-6")}>
        <div className={cn("overflow-hidden", collapsed ? "w-[39px]" : "w-[100px]")}>
          <Image src="/mira-logo.svg" alt="Mira" width={100} height={26} className="h-auto w-[100px] max-w-none" priority />
        </div>
        {!collapsed && (
          <button type="button" onClick={() => setCollapsed(true)} aria-label="Recolher menu lateral" title="Recolher menu"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-white/55 transition hover:bg-white/10 hover:text-white">
            <PanelLeftClose className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className={cn("relative pb-5", collapsed ? "px-2" : "px-3")} ref={orgRef}>
        <button type="button" onClick={() => setOrgOpen((v) => !v)} title={collapsed ? orgName : undefined}
          className={cn("flex w-full items-center rounded-[16px] border border-white/10 bg-white/[0.06] text-left transition hover:bg-white/[0.1]",
            collapsed ? "justify-center p-2" : "gap-2.5 px-3 py-2.5")}
          aria-expanded={orgOpen} aria-haspopup="listbox" aria-label={"Instituição: " + orgName}>
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[11px] bg-[var(--brand-indigo)] text-white"><Building2 className="h-3.5 w-3.5" /></span>
          {!collapsed && <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[12px] font-semibold leading-tight text-white">{orgName}</span>
              <span className="mt-0.5 block truncate text-[10px] text-white/50">{role ? "Perfil · " + role : "Instituição ativa"}</span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-white/45" />
          </>}
        </button>
        {orgOpen && <div role="listbox" className={cn("absolute top-[calc(100%-4px)] z-30 overflow-hidden rounded-[16px] border border-white/10 bg-[#242424] shadow-2xl",
          collapsed ? "left-[68px] w-[205px]" : "left-3 right-3")}>
          <p className="px-3 pb-1 pt-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/45">Instituição</p>
          <button type="button" role="option" aria-selected className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-white/[0.06]" onClick={() => setOrgOpen(false)}>
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--brand-indigo)] text-white"><Building2 className="h-3.5 w-3.5" /></span>
            <span className="min-w-0 flex-1"><span className="block truncate font-medium text-white">{orgName}</span><span className="block text-[10px] text-white/50">Ativa agora</span></span>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          </button>
        </div>}
      </div>

      <nav aria-label="Navegação principal" className={cn("flex flex-1 flex-col overflow-y-auto pb-4", collapsed ? "gap-3 px-2" : "gap-5 px-3")}>
        {groups.map((group) => <div key={group.label}>
          {!collapsed && <p className="mb-1.5 px-3 text-[9px] font-semibold uppercase tracking-[0.2em] text-white/45">{group.label}</p>}
          <div className="space-y-1">
            {group.links.map((link) => {
              const active = link.href === "/" ? pathname === "/" : pathname === link.href || (link.href === "/retencao" ? pathname.startsWith("/retencao") : pathname.startsWith(link.href + "/"));
              return <Link key={link.href} href={link.href} title={collapsed ? link.label : undefined} aria-label={link.label}
                className={cn("group relative flex shrink-0 items-center rounded-[11px] transition duration-200",
                  collapsed ? "h-11 justify-center px-0" : "gap-3 px-3 py-2.5 text-[12px]",
                  active ? "bg-white font-semibold text-[#1a1a1a] shadow-[0_8px_24px_rgba(0,0,0,0.18)]" : "text-white/70 hover:bg-white/[0.08] hover:text-white")}
                aria-current={active ? "page" : undefined}>
                <link.icon className={cn("h-[17px] w-[17px] shrink-0", active ? "text-[var(--brand-indigo)]" : "text-white/50 group-hover:text-white/80")} />
                {!collapsed && <span className="truncate">{link.label}</span>}
              </Link>;
            })}
          </div>
        </div>)}
      </nav>

      <div className={cn("shrink-0 border-t border-white/10", collapsed ? "p-2" : "p-3")}>
        {!collapsed && <div className="mb-1.5 rounded-[15px] bg-white/[0.06] px-3 py-2.5">
          <p className="truncate text-[12px] font-semibold text-white">{displayName}</p>
          <p className="mt-0.5 truncate text-[10px] text-white/50">{me.data?.email || "Sessão da instituição"}</p>
        </div>}
        <button type="button" onClick={logout} title={collapsed ? "Sair da conta" : undefined} aria-label="Sair da conta"
          className={cn("flex w-full items-center rounded-[11px] text-[12px] text-white/60 transition hover:bg-white/[0.08] hover:text-white",
            collapsed ? "h-11 justify-center" : "gap-2.5 px-3 py-2")}>
          <LogOut className="h-3.5 w-3.5 text-white/45" />{!collapsed && "Sair da conta"}
        </button>
        {collapsed && <button type="button" onClick={() => setCollapsed(false)} title="Expandir menu" aria-label="Expandir menu lateral"
          className="mt-1 flex h-9 w-full items-center justify-center rounded-[11px] text-white/55 transition hover:bg-white/[0.08] hover:text-white">
          <PanelLeftOpen className="h-4 w-4" />
        </button>}
      </div>
    </aside>
  );
}
