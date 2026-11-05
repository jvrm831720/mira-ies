import { Skeleton } from "@/components/ui/skeleton";
import type { RiskSummary } from "@/types/api";
import { AlertTriangle, Activity, CheckCircle2, Users } from "@/components/ui/icons";
import { cn } from "@/lib/utils";

export function KpiCards({ data, loading }: { data?: RiskSummary; loading?: boolean }) {
  const s = data?.summary;
  const items = [
    {
      label: "Risco crítico",
      value: s?.critico ?? 0,
      icon: AlertTriangle,
      accent: "text-[#F97066]",
    },
    {
      label: "Risco médio",
      value: s?.medio ?? 0,
      icon: Activity,
      accent: "text-[#FDB022]",
    },
    {
      label: "Risco baixo",
      value: s?.baixo ?? 0,
      icon: CheckCircle2,
      accent: "text-[#32D583]",
    },
    {
      label: "Total pontuados",
      value: data?.total_scored ?? (s ? s.baixo + s.medio + s.critico : 0),
      icon: Users,
      accent: "text-[#7C8DB5]",
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <article
          key={item.label}
          data-mira-card="true"
          className="rounded-xl border border-[var(--overview-border,#292d33)] bg-[var(--overview-surface,#121417)] p-4"
        >
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--overview-subtle,#777f8a)]">
              {item.label}
            </p>
            <item.icon className={cn("h-4 w-4", item.accent)} />
          </div>
          {loading ? (
            <Skeleton className="mt-3 h-8 w-16 bg-white/10" />
          ) : (
            <p className="mt-3 text-[28px] font-semibold leading-none tracking-[-0.04em] tabular-nums text-[var(--overview-text,#f8fafc)]">
              {item.value?.toLocaleString("pt-BR")}
            </p>
          )}
        </article>
      ))}
    </div>
  );
}
