import Link from "next/link";
import type { RecordAction } from "./record-types";
import { cn } from "@/lib/utils";

export function RecordActions({ actions }: { actions: RecordAction[] }) {
  if (!actions.length) return null;
  return <nav aria-label="Ações do registro" className="flex flex-wrap gap-2">
    {actions.map(action => {
      const cls=cn("inline-flex min-h-8 items-center justify-center rounded-[var(--radius-md)] border px-3 py-1.5 text-[12px] font-medium transition-colors duration-[var(--motion-standard)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)] motion-reduce:transition-none",
        action.primary ? "border-[var(--color-ink)] bg-[var(--color-ink)] text-white hover:bg-[var(--color-ink-900)]" :
        "border-[var(--color-border)] bg-white text-[var(--color-ink)] hover:bg-[var(--color-panel)]",
        action.disabled && "pointer-events-none opacity-50");
      return action.href && !action.disabled ? <Link key={action.id} href={action.href} className={cls}>{action.label}</Link>
        : <button key={action.id} type="button" disabled={action.disabled || !action.onClick} onClick={action.onClick}
          className={cls}>{action.label}</button>;
    })}
  </nav>;
}
