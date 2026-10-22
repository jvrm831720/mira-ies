"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Building2, ChevronsUpDown, LayoutDashboard, LogOut, MessageSquareHeart, Plug, Receipt, ScrollText, Settings, Upload, UserCog, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/lib/auth";
import { api } from "@/lib/api";

const links = [
  { href: "/", label: "Visão geral", icon: LayoutDashboard },
  { href: "/alunos", label: "Alunos", icon: Users },
  { href: "/importar", label: "Importar", icon: Upload },
  { href: "/conectores", label: "Conectores", icon: Plug },
  { href: "/retencao", label: "Retenção", icon: MessageSquareHeart },
  { href: "/retencao/logs", label: "Logs de contato", icon: ScrollText },
  { href: "/membros", label: "Membros", icon: UserCog },
  { href: "/fatura", label: "Fatura", icon: Receipt },
  { href: "/config", label: "Configurações", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
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
    <aside className="hidden min-h-screen w-[264px] shrink-0 flex-col bg-[var(--brand-midnight)] text-white md:flex">
      <div className="flex h-[78px] items-center px-7">
        <Image src="/mira-logo.svg" alt="Mira" width={112} height={26} className="h-auto w-[104px] invert" priority />
      </div>

      <div className="relative px-4 pb-5" ref={orgRef}>
        <button type="button" onClick={() => setOrgOpen((v) => !v)} className="flex w-full items-center gap-2.5 rounded-2xl border border-white/10 bg-white/[0.06] px-3 py-3 text-left transition hover:bg-white/[0.1]" aria-expanded={orgOpen} aria-haspopup="listbox">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-[var(--brand-indigo)] text-white"><Building2 className="h-3.5 w-3.5" /></span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-semibold leading-tight text-white">{orgName}</span>
            <span className="mt-0.5 block truncate text-[10px] text-white/45">{role ? `Perfil · ${role}` : "Organização ativa"}</span>
          </span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 text-white/45" />
        </button>
        {orgOpen && (
          <div role="listbox" className="absolute left-4 right-4 top-[calc(100%-4px)] z-30 overflow-hidden rounded-2xl border border-white/10 bg-[#24262c] shadow-2xl">
            <p className="px-3 pb-1 pt-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/40">Suas organizações</p>
            <button type="button" role="option" aria-selected className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-white/[0.06]" onClick={() => setOrgOpen(false)}>
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--brand-indigo)] text-white"><Building2 className="h-3.5 w-3.5" /></span>
              <span className="min-w-0 flex-1"><span className="block truncate font-medium text-white">{orgName}</span><span className="block text-[10px] text-white/45">Ativa agora</span></span>
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </button>
            <div className="border-t border-white/10 px-3 py-2.5 text-[11px] leading-relaxed text-white/45">Quando você fizer parte de mais instituições, elas aparecerão aqui.</div>
          </div>
        )}
      </div>

      <nav aria-label="Navegação principal" className="flex flex-1 flex-col gap-1 overflow-y-auto px-4 pb-4">
        <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/35">Workspace</p>
        {links.map((link) => {
          const active = link.href === "/" ? pathname === "/" : pathname === link.href || (link.href !== "/retencao" && pathname.startsWith(link.href + "/"));
          return <Link key={link.href} href={link.href} className={cn("group relative flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] transition duration-200", active ? "bg-white font-semibold text-[var(--brand-midnight)] shadow-[0_8px_24px_rgba(0,0,0,0.18)]" : "text-white/58 hover:bg-white/[0.08] hover:text-white")} aria-current={active ? "page" : undefined}>
            <link.icon className={cn("h-[17px] w-[17px]", active ? "text-[var(--brand-indigo)]" : "text-white/35 group-hover:text-white/75")} />
            {link.label}
          </Link>;
        })}
      </nav>

      <div className="border-t border-white/10 p-4">
        <div className="mb-2 rounded-2xl bg-white/[0.06] px-3 py-3"><p className="truncate text-[12px] font-semibold text-white">{displayName}</p><p className="mt-0.5 truncate text-[10px] text-white/45">{me.data?.email || "Sessão da instituição"}</p></div>
        <button type="button" onClick={logout} className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] text-white/55 transition hover:bg-white/[0.08] hover:text-white"><LogOut className="h-4 w-4 text-white/35" />Sair da conta</button>
      </div>
    </aside>
  );
}
