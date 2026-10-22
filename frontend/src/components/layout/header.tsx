"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Building2, ChevronRight, LogOut, Menu, X } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/lib/auth";
import { api } from "@/lib/api";

const mobileLinks = [
  { href: "/", label: "Visão geral" },
  { href: "/alunos", label: "Alunos" },
  { href: "/importar", label: "Importar" },
  { href: "/conectores", label: "Conectores" },
  { href: "/retencao", label: "Retenção" },
  { href: "/retencao/logs", label: "Logs" },
  { href: "/membros", label: "Membros" },
  { href: "/config", label: "Config" },
];

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const me = useQuery({
    queryKey: ["org-me"],
    queryFn: () => api.me(),
    retry: false,
    staleTime: 60_000,
  });

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
      <div className="flex min-h-[76px] items-center justify-between gap-4 px-4 py-3 md:px-9">
        <div className="min-w-0">
          <div className="mb-1 hidden items-center gap-1 text-[11px] font-medium text-muted-foreground sm:flex">
            <span className="inline-flex items-center gap-1">
              <Building2 className="h-3 w-3" />
              {me.data?.tenant_name || "Mira"}
            </span>
            <ChevronRight className="h-3 w-3" />
            <span className="text-foreground/70">{title}</span>
          </div>
          <h1 className="truncate text-[19px] font-semibold tracking-[-0.03em] md:text-[21px]">
            {title}
          </h1>
          {subtitle ? (
            <p className="mt-0.5 hidden truncate text-[13px] text-muted-foreground sm:block">
              {subtitle}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          className="rounded-xl border border-border bg-white p-2.5 text-foreground transition hover:bg-muted md:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Fechar menu" : "Abrir menu"}
          aria-expanded={open}
        >
          {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      </div>
      {open && (
        <nav aria-label="Navegação mobile" className="border-t border-border bg-white px-4 py-3 md:hidden">
          <div className="mb-2 flex items-center gap-2 rounded-lg bg-muted/50 px-2 py-2 text-xs text-muted-foreground">
            <Building2 className="h-3.5 w-3.5" />
            <span className="truncate font-medium text-foreground">
              {me.data?.tenant_name || "Instituição"}
            </span>
          </div>
          {mobileLinks.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className={cn(
                "block rounded-md px-2 py-2 text-sm",
                pathname === l.href
                  ? "bg-secondary font-semibold text-primary"
                  : "text-muted-foreground hover:bg-muted"
              )}
            >
              {l.label}
            </Link>
          ))}
          <button
            type="button"
            onClick={logout}
            className="mt-2 flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-muted"
          >
            <LogOut className="h-4 w-4" />
            Sair da conta
          </button>
        </nav>
      )}
    </header>
  );
}
