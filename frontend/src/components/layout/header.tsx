"use client";

import {
  Bell,
  Building2,
  ChevronRight,
  CircleHelp,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Panel = "none" | "notifications" | "help";

export function Header({ title, subtitle, compact = false }: { title: string; subtitle?: string; compact?: boolean }) {
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
    <header className="sticky top-0 z-20 border-b border-black/[0.06] bg-[rgba(247,245,239,0.88)] backdrop-blur-xl">
      <div className={cn("flex w-full items-center gap-4 pl-14 pr-4 md:px-8 xl:px-10", compact ? "min-h-[52px] justify-end py-2" : "min-h-[72px] justify-between py-3")}>
        {!compact && <div className="min-w-0">
          <div className="mb-0.5 hidden items-center gap-1 text-[11px] font-medium text-neutral-400 sm:flex">
            <span className="inline-flex items-center gap-1.5 uppercase tracking-[0.14em]">
              <Building2 className="h-3 w-3" />
              {me.data?.tenant_name || "Mira"}
            </span>
            <ChevronRight className="h-3 w-3 text-[var(--brand-indigo)]" />
            <span className="text-neutral-600">{title}</span>
          </div>
          <h1 className="truncate text-[22px] font-semibold tracking-[-0.055em] text-neutral-950 md:text-[25px]">{title}</h1>
          {subtitle ? <p className="mt-0.5 hidden truncate text-[12px] leading-relaxed text-neutral-500 sm:block">{subtitle}</p> : null}
        </div>}

        <div className="relative flex items-center gap-1" ref={panelRef}>
          <IconButton
            label="Notificações"
            active={panel === "notifications"}
            onClick={() => toggle("notifications")}
          >
            <Bell className="h-[18px] w-[18px]" />
          </IconButton>
          <IconButton label="Ajuda" active={panel === "help"} onClick={() => toggle("help")}>
            <CircleHelp className="h-[18px] w-[18px]" />
          </IconButton>
          {panel === "notifications" && (
            <div className="absolute right-0 top-[calc(100%+8px)] z-40 w-[min(100vw-2rem,340px)] overflow-hidden rounded-[20px] border border-neutral-200 bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-neutral-100 px-4 py-3">
                <p className="text-sm font-semibold text-neutral-900">Notificações</p>
                <span className="text-[10px] text-neutral-400">{notifications.length} recentes</span>
              </div>
              <ul className="max-h-[320px] overflow-y-auto">
                {notifications.map((n) => (
                  <li
                    key={n.id}
                    className="border-b border-neutral-100 px-4 py-3 last:border-0 hover:bg-neutral-50"
                  >
                    <p className="text-[13px] font-semibold text-neutral-900">{n.title}</p>
                    <p className="mt-0.5 text-[12px] leading-relaxed text-neutral-500">{n.body}</p>
                    <p className="mt-1 text-[10px] text-neutral-400">{n.time}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {panel === "help" && (
            <div className="absolute right-0 top-[calc(100%+8px)] z-40 w-[min(100vw-2rem,360px)] overflow-hidden rounded-[20px] border border-neutral-200 bg-white shadow-xl">
              <div className="border-b border-neutral-100 px-4 py-3">
                <p className="text-sm font-semibold text-neutral-900">Pedir ajuda</p>
                <p className="mt-0.5 text-[11px] text-neutral-500">
                  Descreva o que precisa. Enviamos para o suporte Mira.
                </p>
              </div>
              <form onSubmit={submitHelp} className="space-y-3 p-4">
                <div className="space-y-1.5">
                  <label className="text-[13px] font-medium text-neutral-700" htmlFor="help-subject">
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
                  <label className="text-[13px] font-medium text-neutral-700" htmlFor="help-message">
                    Mensagem
                  </label>
                  <textarea
                    id="help-message"
                    value={helpMessage}
                    onChange={(e) => setHelpMessage(e.target.value)}
                    rows={4}
                    placeholder="Conte o que aconteceu e o que você tentou fazer."
                    className="flex w-full rounded-[16px] border border-neutral-200 bg-white px-4 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-neutral-900/15"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={helpSending}>
                  {helpSending ? "Enviando…" : "Enviar pedido"}
                </Button>
              </form>
            </div>
          )}

        </div>
      </div>

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
        "grid h-9 w-9 place-items-center rounded-[11px] text-neutral-500 transition hover:bg-white hover:text-neutral-900",
        active && "bg-white text-neutral-900 shadow-sm"
      )}
    >
      {children}
    </button>
  );
}
