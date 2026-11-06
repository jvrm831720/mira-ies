import type { ReactNode } from "react";
import type { InterventionLog } from "@/types/api";
import { CHANNEL_LABEL, formatDate } from "./work-activity-labels";

export function InfoBlock({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-white px-3 py-2">
      <p className="text-[length:var(--type-caption)] font-medium uppercase tracking-wide text-[var(--color-muted)]">{label}</p>
      <div className="mt-0.5 text-xs text-[var(--color-slate-600)]">{children}</div>
    </div>
  );
}

export function InterventionContext({ log }: { log: InterventionLog }) {
  return (
    <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
      <div>
        <span className="text-[var(--color-muted)]">Canal</span>
        <p className="font-medium text-[var(--color-ink)]">
          {log.channel ? CHANNEL_LABEL[log.channel] ?? log.channel : "—"}
        </p>
      </div>
      <div>
        <span className="text-[var(--color-muted)]">Data</span>
        <p className="font-medium text-[var(--color-ink)]">{formatDate(log.created_at)}</p>
      </div>
      <div>
        <span className="text-[var(--color-muted)]">Decision reason</span>
        <p className="font-medium text-[var(--color-ink)]">{log.decision_reason || "—"}</p>
      </div>
      <div>
        <span className="text-[var(--color-muted)]">Status de execução</span>
        <p className="font-medium text-[var(--color-ink)]">{log.status || "—"}</p>
      </div>
      <div>
        <span className="text-[var(--color-muted)]">Delivery status</span>
        <p className="font-medium text-[var(--color-ink)]">{log.delivery_status || "—"}</p>
      </div>
      <div>
        <span className="text-[var(--color-muted)]">Outcome</span>
        <p className="font-medium text-[var(--color-ink)]">
          {log.outcome
            ? `${log.outcome}${log.outcome_at ? ` · ${formatDate(log.outcome_at)}` : ""}`
            : "—"}
        </p>
      </div>
    </div>
  );
}
