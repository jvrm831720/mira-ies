import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { RiskSummary } from "@/types/api";
import { AlertTriangle, Activity, CheckCircle2, Users } from "lucide-react";

export function KpiCards({ data, loading }: { data?: RiskSummary; loading?: boolean }) {
  const s = data?.summary;
  const items = [
    {
      label: "Risco crítico",
      note: "Atenção prioritária",
      value: s?.critico ?? 0,
      icon: AlertTriangle,
      accent: "text-[#f47769] bg-[#f47769]/12",
      bar: "bg-[var(--brand-coral)]",
    },
    {
      label: "Risco médio",
      note: "Acompanhar de perto",
      value: s?.medio ?? 0,
      icon: Activity,
      accent: "text-[var(--brand-indigo)] bg-[var(--brand-indigo)]/12",
      bar: "bg-[var(--brand-indigo)]",
    },
    {
      label: "Risco baixo",
      note: "Evolução estável",
      value: s?.baixo ?? 0,
      icon: CheckCircle2,
      accent: "text-emerald-400 bg-emerald-400/12",
      bar: "bg-emerald-400",
    },
    {
      label: "Total pontuados",
      note: "Alunos analisados",
      value: data?.total_scored ?? (s ? s.baixo + s.medio + s.critico : 0),
      icon: Users,
      accent: "text-primary bg-primary/15",
      bar: "bg-primary",
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <Card
          key={item.label}
          className="group relative overflow-hidden transition duration-200 hover:-translate-y-0.5 hover:border-white/10"
        >
          <span className={`absolute inset-x-0 top-0 h-[3px] ${item.bar}`} />
          <CardContent className="flex items-center justify-between p-5">
            <div className="min-w-0">
              <p className="text-[12px] font-medium text-muted-foreground">{item.label}</p>
              {loading ? (
                <Skeleton className="mt-2 h-8 w-16" />
              ) : (
                <p className="mt-2 text-[30px] font-semibold leading-none tracking-[-0.05em] tabular-nums">
                  {item.value?.toLocaleString("pt-BR")}
                </p>
              )}
              <p className="mt-2 text-[11px] text-muted-foreground/80">{item.note}</p>
            </div>
            <div className={`rounded-xl p-3.5 ${item.accent}`}>
              <item.icon className="h-[19px] w-[19px]" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
