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
  Receipt,
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
  { href: "/fatura", label: "Fatura", icon: Receipt },
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
    <aside className="hidden min-h-screen w-[248px] shrink-0 flex-col border-r border-neutral-200 bg-white md:flex">
      <div className="flex h-[64px] items-center px-5">
        <Image
          src="/mira-logo.svg"
          alt="Mira"
          width={112}
          height={26}
          className="h-auto w-[100px] brightness-0"
          priority
        />
      </div>

      <div className="relative px-3 pb-3" ref={orgRef}>
        <button
          type="button"
          onClick={() => setOrgOpen((v) => !v)}
          className="flex w-full items-center gap-2.5 rounded-2xl border border-neutral-200 bg-neutral-50 px-3 py-2.5 text-left transition hover:bg-neutral-100"
          aria-expanded={orgOpen}
          aria-haspopup="listbox"
        >
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-neutral-900 text-white">
            <Building2 className="h-3.5 w-3.5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-semibold leading-tight text-neutral-900">
              {orgName}
            </span>
            <span className="mt-0.5 block truncate text-[10px] text-neutral-500">
              {role ? `Perfil · ${role}` : "Organização ativa"}
            </span>
          </span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 text-neutral-400" />
        </button>

        {orgOpen && (
          <div
            role="listbox"
            className="absolute left-3 right-3 top-[calc(100%-4px)] z-30 overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-xl"
          >
            <p className="px-3 pt-2.5 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-neutral-400">
              Suas organizações
            </p>
            <button
              type="button"
              role="option"
              aria-selected
              className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-neutral-50"
              onClick={() => setOrgOpen(false)}
            >
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-neutral-900 text-white">
                <Building2 className="h-3.5 w-3.5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-neutral-900">{orgName}</span>
                <span className="block text-[10px] text-neutral-500">Ativa agora</span>
              </span>
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </button>
            <div className="border-t border-neutral-100 px-3 py-2.5 text-[11px] leading-relaxed text-neutral-500">
              Quando você fizer parte de mais instituições, elas aparecerão aqui.
            </div>
          </div>
        )}
      </div>

      <nav
        aria-label="Navegação principal"
        className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 pb-4"
      >
        <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-neutral-400">
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
                  ? "bg-neutral-900 font-semibold text-white"
                  : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900"
              )}
              aria-current={active ? "page" : undefined}
            >
              <link.icon
                className={cn(
                  "h-[17px] w-[17px]",
                  active ? "text-white" : "text-neutral-400 group-hover:text-neutral-700"
                )}
              />
              {link.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-neutral-100 p-3">
        <div className="mb-2 rounded-2xl bg-neutral-50 px-3 py-2.5">
          <p className="truncate text-[12px] font-semibold text-neutral-900">{displayName}</p>
          <p className="mt-0.5 truncate text-[10px] text-neutral-500">
            {me.data?.email || "Sessão da instituição"}
          </p>
        </div>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] text-neutral-600 transition hover:bg-neutral-100 hover:text-neutral-900"
        >
          <LogOut className="h-4 w-4 text-neutral-400" />
          Sair da conta
        </button>
      </div>
    </aside>
  );
}
