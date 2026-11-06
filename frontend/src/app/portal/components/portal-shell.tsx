"use client";

import type { ReactNode } from "react";
import {
  BookOpen, CalendarDays, ClipboardList, FileText, GraduationCap,
  House, LogOut, ShieldCheck, UserRound, Wallet,
} from "@/components/ui/icons";

export type PortalSection =
  | "home" | "journey" | "disciplines" | "calendar"
  | "requests" | "documents" | "financial" | "account";

export const PORTAL_NAVIGATION = [
  { id: "home", title: "Início", icon: House },
  { id: "journey", title: "Minha jornada", icon: GraduationCap },
  { id: "disciplines", title: "Disciplinas", icon: BookOpen },
  { id: "calendar", title: "Calendário", icon: CalendarDays },
  { id: "requests", title: "Solicitações", icon: ClipboardList },
  { id: "documents", title: "Documentos", icon: FileText },
  { id: "financial", title: "Financeiro", icon: Wallet },
  { id: "account", title: "Minha conta", icon: UserRound },
] as const;

type PortalShellProps = {
  section: PortalSection;
  onNavigate: (section: PortalSection) => void;
  institution: string;
  studentName: string;
  busy: boolean;
  onLogout: () => void;
  children: ReactNode;
};

/** Student-facing shell only. The institutional navigation remains untouched. */
export function PortalShell({
  section, onNavigate, institution, studentName, busy, onLogout, children,
}: PortalShellProps) {
  const navigation = PORTAL_NAVIGATION.map(({ id, title, icon: Icon }) => (
    <button key={id} type="button" onClick={() => onNavigate(id)}
      aria-current={section === id ? "page" : undefined}
      className={`group flex shrink-0 items-center gap-2.5 rounded-[10px] px-3 py-2.5 text-left text-[12px] font-medium outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-[#266DF0] motion-reduce:transition-none
        ${section === id
          ? "bg-[#EFF4FF] text-[#1E58C7]"
          : "text-[#505967] hover:bg-[#F8F9FA] hover:text-[#101112]"}`}>
      <Icon className="h-[17px] w-[17px] shrink-0" aria-hidden="true" />
      <span>{title}</span>
    </button>
  ));

  const activeTitle = PORTAL_NAVIGATION.find(item => item.id === section)?.title ?? "Portal do Aluno";

  return (
    <div className="min-h-dvh bg-white text-[#101112]">
      <a href="#portal-content"
        className="sr-only fixed left-4 top-3 z-50 rounded-md bg-[#101112] px-4 py-2 text-white focus:not-sr-only">
        Ir para o conteúdo
      </a>
      <div className="md:grid md:min-h-dvh md:grid-cols-[224px_minmax(0,1fr)]">
        <aside aria-label="Menu do Portal do Aluno"
          className="hidden min-h-dvh border-r border-[#E6E7EA] bg-[#FBFBFB] md:flex md:flex-col">
          <div className="flex h-[66px] items-center gap-3 border-b border-[#E6E7EA] px-5">
            <span className="text-[23px] font-bold tracking-[-0.085em]">mira<span className="text-[#266DF0]">.</span></span>
            <span className="h-5 w-px bg-[#E6E7EA]" />
            <span className="text-[12px] font-medium text-[#505967]">Aluno</span>
          </div>
          <p className="truncate px-5 pb-3 pt-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#75777C]">
            Seu espaço
          </p>
          <nav aria-label="Navegação principal" className="flex flex-col gap-0.5 px-3">
            {navigation}
          </nav>
          <div className="mt-auto border-t border-[#E6E7EA] p-4">
            <p className="truncate text-[12px] font-semibold" title={studentName}>{studentName}</p>
            <p className="mt-1 line-clamp-2 text-[11px] text-[#75777C]">{institution}</p>
            <button type="button" onClick={onLogout} disabled={busy}
              className="mt-4 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[12px] text-[#505967] hover:bg-[#F0F1F3] focus-visible:ring-2 focus-visible:ring-[#266DF0] disabled:opacity-50">
              <LogOut className="h-4 w-4" /> Sair com segurança
            </button>
          </div>
        </aside>
        <div className="min-w-0">
          <header className="sticky top-0 z-20 flex h-[60px] items-center justify-between gap-3 border-b border-[#E6E7EA] bg-white/95 px-4 backdrop-blur sm:px-7 md:h-[66px]">
            <div className="flex min-w-0 items-center gap-2">
              <span className="text-[21px] font-bold tracking-[-0.085em] md:hidden">
                mira<span className="text-[#266DF0]">.</span>
              </span>
              <span className="hidden text-[#9FA1A7] md:block">Portal /</span>
              <span className="truncate text-[13px] font-semibold">{activeTitle}</span>
            </div>
            <div className="inline-flex items-center gap-1.5 text-[11px] text-[#505967]">
              <ShieldCheck className="h-4 w-4 text-[#266DF0]" />
              <span className="hidden sm:inline">Acesso individual protegido</span>
              <span className="sm:hidden">Sessão segura</span>
            </div>
          </header>
          <main id="portal-content" tabIndex={-1}
            className="mx-auto w-full max-w-[1180px] px-4 pb-28 pt-7 outline-none sm:px-7 md:pb-16 md:pt-10 lg:px-10">
            {children}
          </main>
        </div>
      </div>
      <nav aria-label="Navegação móvel do Portal"
        className="fixed inset-x-0 bottom-0 z-30 flex gap-1 overflow-x-auto border-t border-[#E6E7EA] bg-white/95 px-3 py-2 shadow-[0_-6px_18px_rgba(0,22,62,0.04)] backdrop-blur md:hidden">
        {navigation}
      </nav>
    </div>
  );
}
