"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  ChevronsUpDown,
  LayoutDashboard,
  LogOut,
  MessageSquareHeart,
  Plug,
  ScrollText,
  Settings,
  Upload,
  UserCog,
  Users,
} from "lucide-react";
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
  { href: "/config", label: "Configurações", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [orgOpen, setOrgOpen] = useState(false);
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
    <aside className="hidden min-h-screen w-[260px] shrink-0 flex-col bg-[var(--brand-midnight)] text-white md:flex">
      {/* Brand */}
      <div className="flex h-[64px] items-center border-b border-white/10 px-5">
        <Image
          src="/mira-logo.svg"
          alt="Mira"
          width={120}
          height={28}
          className="h-auto w-[108px]"
          priority
        />
      </div>

      {/* Organization switcher */}
      <div className="relative border-b border-white/10 px-3 py-3" ref={orgRef}>
        <button
          type="button"
          onClick={() => setOrgOpen((v) => !v)}
          className="flex w-full items-center gap-2.5 rounded-xl border border-white/10 bg-white/[0.05] px-3 py-2.5 text-left transition hover:bg-white/[0.09]"
          aria-expanded={orgOpen}
          aria-haspopup="listbox"
        >
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[var(--brand-coral)]/20 text-[var(--brand-coral)]">
            <Building2 className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-semibold leading-tight">{orgName}</span>
            <span className="mt-0.5 block truncate text-[10px] text-white/45">
              {role ? `Perfil · ${role}` : "Organização ativa"}
            </span>
          </span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 text-white/40" />
        </button>

        {orgOpen && (
          <div
            role="listbox"
            className="absolute left-3 right-3 top-[calc(100%-4px)] z-30 overflow-hidden rounded-xl border border-white/10 bg-[#16143a] shadow-2xl"
          >
            <p className="px-3 pt-2.5 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/40">
              Suas organizações
            </p>
            <button
              type="button"
              role="option"
              aria-selected
              className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-white/[0.06]"
              onClick={() => setOrgOpen(false)}
            >
              <span className="grid h-7 w-7 place-items-center rounded-md bg-[var(--brand-coral)]/20 text-[var(--brand-coral)]">
                <Building2 className="h-3.5 w-3.5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{orgName}</span>
                <span className="block text-[10px] text-white/45">Ativa agora</span>
              </span>
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--brand-coral)]" />
            </button>
            <div className="border-t border-white/10 px-3 py-2.5 text-[11px] leading-relaxed text-white/45">
              Quando você fizer parte de mais instituições, elas aparecerão aqui para troca rápida.
            </div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav aria-label="Navegação principal" className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 py-4">
        <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/40">
          Workspace
        </p>
        {links.map((link) => {
          const active =
            link.href === "/"
              ? pathname === "/"
              : pathname === link.href ||
                (link.href !== "/retencao" && pathname.startsWith(link.href + "/"));
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "group relative flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] transition duration-200",
                active
                  ? "bg-white/10 font-semibold text-white shadow-inner"
                  : "text-white/65 hover:bg-white/[0.07] hover:text-white"
              )}
              aria-current={active ? "page" : undefined}
            >
              {active && (
                <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-[var(--brand-coral)]" />
              )}
              <link.icon
                className={cn(
                  "h-[17px] w-[17px]",
                  active ? "text-[var(--brand-coral)]" : "text-white/50 group-hover:text-white"
                )}
              />
              {link.label}
            </Link>
          );
        })}
      </nav>

      {/* Account / logout */}
      <div className="border-t border-white/10 p-3">
        <div className="mb-2 rounded-xl bg-white/[0.04] px-3 py-2.5">
          <p className="truncate text-[12px] font-semibold text-white/90">{displayName}</p>
          <p className="mt-0.5 truncate text-[10px] text-white/45">
            {me.data?.email || "Sessão da instituição"}
          </p>
        </div>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] text-white/65 transition hover:bg-white/[0.07] hover:text-white"
        >
          <LogOut className="h-4 w-4 text-white/50" />
          Sair da conta
        </button>
      </div>
    </aside>
  );
}
