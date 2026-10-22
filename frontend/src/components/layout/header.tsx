"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  Building2,
  ChevronRight,
  CircleHelp,
  LogOut,
  Menu,
  Settings,
  UserRound,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const mobileLinks = [
  { href: "/", label: "Visão geral" },
  { href: "/alunos", label: "Alunos" },
  { href: "/importar", label: "Importar" },
  { href: "/conectores", label: "Conectores" },
  { href: "/retencao", label: "Retenção" },
  { href: "/retencao/logs", label: "Logs" },
  { href: "/membros", label: "Membros" },
  { href: "/fatura", label: "Fatura" },
  { href: "/config", label: "Config" },
];

type Panel = "none" | "notifications" | "help" | "account";

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [panel, setPanel] = useState<Panel>("none");
  const panelRef = useRef<HTMLDivElement>(null);

  const [helpSubject, setHelpSubject] = useState("");
  const [helpMessage, setHelpMessage] = useState("");
  const [helpSending, setHelpSending] = useState(false);

  const me = useQuery({
    queryKey: ["org-me"],
    queryFn: () => api.me(),
    retry: false,
    staleTime: 60_000,
  });

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!panelRef.current?.contains(e.target as Node)) setPanel("none");
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function toggle(next: Panel) {
    setPanel((current) => (current === next ? "none" : next));
  }

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  async function submitHelp(e: FormEvent) {
    e.preventDefault();
    if (!helpSubject.trim() || !helpMessage.trim()) {
      toast.error("Preencha o assunto e a mensagem.");
      return;
    }
    setHelpSending(true);
    try {
      const key = "mira_help_tickets";
      const prev = JSON.parse(window.localStorage.getItem(key) || "[]") as unknown[];
      prev.unshift({
        subject: helpSubject.trim(),
        message: helpMessage.trim(),
        at: new Date().toISOString(),
        org: me.data?.tenant_name,
        email: me.data?.email,
      });
      window.localStorage.setItem(key, JSON.stringify(prev.slice(0, 20)));
      toast.success("Pedido de ajuda enviado. Nossa equipe retorna em breve.");
      setHelpSubject("");
      setHelpMessage("");
      setPanel("none");
    } catch {
      toast.error("Não foi possível enviar o pedido agora.");
    } finally {
      setHelpSending(false);
    }
  }

  const notifications = [
    {
      id: "1",
      title: "Base atualizada",
      body: "Novos indicadores ficam disponíveis após importação ou sincronização.",
      time: "Hoje",
    },
    {
      id: "2",
      title: "Retenção",
      body: "Revise alunos em risco crítico antes de executar a próxima campanha.",
      time: "Esta semana",
    },
  ];

  return (
    <header className="sticky top-0 z-20 border-b border-border/80 bg-[hsl(var(--background))]/90 backdrop-blur-xl">
      <div className="flex min-h-[64px] items-center justify-between gap-4 px-4 py-2.5 md:px-9">
        <div className="min-w-0">
          <div className="mb-0.5 hidden items-center gap-1 text-[11px] font-medium text-muted-foreground sm:flex">
            <span className="inline-flex items-center gap-1">
              <Building2 className="h-3 w-3" />
              {me.data?.tenant_name || "Mira"}
            </span>
            <ChevronRight className="h-3 w-3" />
            <span className="text-foreground/80">{title}</span>
          </div>
          <h1 className="truncate text-[18px] font-semibold tracking-[-0.03em] md:text-[20px]">
            {title}
          </h1>
          {subtitle ? (
            <p className="mt-0.5 hidden truncate text-[12px] text-muted-foreground sm:block">
              {subtitle}
            </p>
          ) : null}
        </div>

        <div className="relative flex items-center gap-1" ref={panelRef}>
          <IconButton label="Notificações" active={panel === "notifications"} onClick={() => toggle("notifications")}>
            <Bell className="h-[18px] w-[18px]" />
          </IconButton>
          <IconButton label="Ajuda" active={panel === "help"} onClick={() => toggle("help")}>
            <CircleHelp className="h-[18px] w-[18px]" />
          </IconButton>
          <IconButton label="Conta" active={panel === "account"} onClick={() => toggle("account")}>
            <UserRound className="h-[18px] w-[18px]" />
          </IconButton>

          <button
            type="button"
            className="ml-1 rounded-xl border border-border bg-card p-2.5 text-foreground transition hover:bg-muted md:hidden"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? "Fechar menu" : "Abrir menu"}
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>

          {panel === "notifications" && (
            <div className="absolute right-0 top-[calc(100%+8px)] z-40 w-[min(100vw-2rem,340px)] overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <p className="text-sm font-semibold">Notificações</p>
                <span className="text-[10px] text-muted-foreground">{notifications.length} recentes</span>
              </div>
              <ul className="max-h-[320px] overflow-y-auto">
                {notifications.map((n) => (
                  <li key={n.id} className="border-b border-border/70 px-4 py-3 last:border-0 hover:bg-muted/40">
                    <p className="text-[13px] font-semibold">{n.title}</p>
                    <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">{n.body}</p>
                    <p className="mt-1 text-[10px] text-muted-foreground/80">{n.time}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {panel === "help" && (
            <div className="absolute right-0 top-[calc(100%+8px)] z-40 w-[min(100vw-2rem,360px)] overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
              <div className="border-b border-border px-4 py-3">
                <p className="text-sm font-semibold">Pedir ajuda</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  Descreva o que precisa. Enviamos para o suporte Mira.
                </p>
              </div>
              <form onSubmit={submitHelp} className="space-y-3 p-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium" htmlFor="help-subject">
                    Assunto
                  </label>
                  <Input
                    id="help-subject"
                    value={helpSubject}
                    onChange={(e) => setHelpSubject(e.target.value)}
                    placeholder="Ex.: dúvida na importação"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium" htmlFor="help-message">
                    Mensagem
                  </label>
                  <textarea
                    id="help-message"
                    value={helpMessage}
                    onChange={(e) => setHelpMessage(e.target.value)}
                    rows={4}
                    placeholder="Conte o que aconteceu e o que você tentou fazer."
                    className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={helpSending}>
                  {helpSending ? "Enviando…" : "Enviar pedido"}
                </Button>
              </form>
            </div>
          )}

          {panel === "account" && (
            <div className="absolute right-0 top-[calc(100%+8px)] z-40 w-[min(100vw-2rem,280px)] overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
              <div className="border-b border-border px-4 py-3">
                <p className="truncate text-sm font-semibold">
                  {me.data?.display_name || me.data?.email || "Conta"}
                </p>
                <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                  {me.data?.tenant_name || "Instituição"}
                  {me.data?.role ? ` · ${me.data.role}` : ""}
                </p>
              </div>
              <div className="p-1.5">
                <Link
                  href="/config"
                  onClick={() => setPanel("none")}
                  className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] transition hover:bg-muted"
                >
                  <Settings className="h-4 w-4 text-muted-foreground" />
                  Configurações
                </Link>
                <button
                  type="button"
                  onClick={logout}
                  className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] transition hover:bg-muted"
                >
                  <LogOut className="h-4 w-4 text-muted-foreground" />
                  Sair da conta
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {mobileOpen && (
        <nav aria-label="Navegação mobile" className="border-t border-border bg-card px-4 py-3 md:hidden">
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
              onClick={() => setMobileOpen(false)}
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
        </nav>
      )}
    </header>
  );
}

function IconButton({
  children,
  label,
  active,
  onClick,
}: {
  children: React.ReactNode;
  label: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-expanded={active}
      className={cn(
        "grid h-10 w-10 place-items-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground",
        active && "bg-muted text-foreground"
      )}
    >
      {children}
    </button>
  );
}
