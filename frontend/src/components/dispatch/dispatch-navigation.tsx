"use client";
import Link from "next/link";
import { Activity, BarChart3, ClipboardList, FileClock, MessageCircle, Settings2, Workflow } from "@/components/ui/icons";
import type { DispatchSection } from "./dispatch-types";

type Option = { id: DispatchSection; label: string; icon: typeof Activity };
const sections: Option[] = [
  { id: "overview", label: "Visão geral", icon: Activity },
  { id: "campaigns", label: "Campanhas operacionais", icon: ClipboardList },
  { id: "monitor", label: "Fila e entregas", icon: MessageCircle },
  { id: "results", label: "Resultados", icon: BarChart3 },
];
export function DispatchNavigation({
  section, onSectionChange, canManageProviders,
}: {
  section: DispatchSection;
  onSectionChange: (section: DispatchSection) => void;
  canManageProviders: boolean;
}) {
  return <nav aria-label="Áreas da operação" className="flex min-w-0 gap-1 overflow-x-auto border-b border-[var(--color-border)] bg-white px-4 md:px-7">
    {sections.map(item => {
      const Icon = item.icon;
      return <button type="button" key={item.id}
        aria-current={section === item.id ? "page" : undefined}
        onClick={() => onSectionChange(item.id)}
        className={`inline-flex h-11 shrink-0 items-center gap-1.5 border-b-2 px-3 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-[var(--color-blue)] ${section === item.id
          ? "border-[var(--color-ink)] text-[var(--color-ink)]"
          : "border-transparent text-[var(--color-slate-600)] hover:text-[var(--color-ink)]"}`}>
        <Icon className="h-3.5 w-3.5" aria-hidden="true" /> {item.label}
      </button>;
    })}
    <div aria-hidden="true" className="shrink-0 flex-1" />
    <Link href="/disparos/modelos" className="inline-flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 text-xs text-[var(--color-slate-600)] hover:text-[var(--color-ink)]"><FileClock className="h-3.5 w-3.5" /> Modelos</Link>
    {canManageProviders && <Link href="/disparos/provedores" className="inline-flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 text-xs text-[var(--color-slate-600)] hover:text-[var(--color-ink)]"><Settings2 className="h-3.5 w-3.5" /> Provedores</Link>}
    <Link href="/workflows" className="inline-flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 text-xs text-[var(--color-slate-600)] hover:text-[var(--color-ink)]"><Workflow className="h-3.5 w-3.5" /> Workflows</Link>
  </nav>;
}
