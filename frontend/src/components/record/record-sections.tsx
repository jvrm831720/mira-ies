"use client";
import { useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { RecordSection } from "./record-types";

export function RecordSections({ sections, initialId, className }: {
  sections: RecordSection[]; initialId?: string; className?: string;
}) {
  const [selected, setSelected] = useState(initialId || sections[0]?.id || "");
  const ref = useRef<HTMLDivElement>(null);
  const active = sections.find(section => section.id === selected) || sections[0];
  if (!active) return <p className="p-4 text-xs text-[var(--color-muted)]">Sem seções disponíveis.</p>;
  return <div className={cn("min-w-0",className)}>
    <div ref={ref} role="tablist" aria-label="Seções do registro" className="flex items-center gap-1 overflow-x-auto border-b border-[var(--color-border)]"
      onKeyDown={event => {
        if (!["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) return;
        event.preventDefault();
        const current = sections.findIndex(section=>section.id===active.id);
        const index=event.key==="Home"?0:event.key==="End"?sections.length-1:
          (current + (event.key==="ArrowRight"?1:-1)+sections.length)%sections.length;
        setSelected(sections[index].id);
        ref.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[index]?.focus();
      }}>
      {sections.map(section => <button key={section.id} id={"record-tab-"+section.id} role="tab" type="button"
        aria-controls={"record-panel-"+section.id} aria-selected={section.id===active.id}
        tabIndex={section.id===active.id?0:-1}
        onClick={()=>setSelected(section.id)}
        className={cn("shrink-0 border-b-2 px-3 py-3 text-xs font-medium transition-colors duration-[var(--motion-standard)] focus-visible:outline-offset-[-3px]",
          section.id===active.id?"border-[var(--color-ink)] text-[var(--color-ink)]":"border-transparent text-[var(--color-slate-600)] hover:text-[var(--color-ink)]")}>
        {section.label}
      </button>)}
    </div>
    <div role="tabpanel" id={"record-panel-"+active.id} aria-labelledby={"record-tab-"+active.id} tabIndex={0}
      className="min-w-0 py-4">{active.content}</div>
  </div>;
}
