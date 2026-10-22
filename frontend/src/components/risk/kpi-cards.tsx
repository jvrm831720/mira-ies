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
      accent: "text-[#e76e61] bg-[#fff0ed]",
      bar: "bg-[var(--brand-coral)]",
    },
    {
      label: "Risco médio",
      note: "Acompanhar de perto",
      value: s?.medio ?? 0,
      icon: Activity,
      accent: "text-neutral-700 bg-neutral-100",
      bar: "bg-neutral-900",
    },
    {
      label: "Risco baixo",
      note: "Evolução estável",
      value: s?.baixo ?? 0,
      icon: CheckCircle2,
      accent: "text-emerald-700 bg-emerald-50",
      bar: "bg-emerald-500",
    },
    {
      label: "Total pontuados",
      note: "Alunos analisados",
      value: data?.total_scored ?? (s ? s.baixo + s.medio + s.critico : 0),
      icon: Users,
      accent: "text-neutral-700 bg-neutral-100",
      bar: "bg-neutral-400",
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <Card
          key={item.label}
          className="group relative overflow-hidden transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_12px_30px_rgba(0,0,0,0.06)]"
        >
          <span className={`absolute inset-x-0 top-0 h-[3px] ${item.bar}`} />
          <CardContent className="flex items-center justify-between p-5">
            <div className="min-w-0">
              <p className="text-[12px] font-medium text-neutral-500">{item.label}</p>
              {loading ? (
                <Skeleton className="mt-2 h-8 w-16" />
              ) : (
                <p className="mt-2 text-[30px] font-semibold leading-none tracking-[-0.05em] tabular-nums text-neutral-900">
                  {item.value?.toLocaleString("pt-BR")}
                </p>
              )}
              <p className="mt-2 text-[11px] text-neutral-400">{item.note}</p>
            </div>
            <div className={`rounded-2xl p-3.5 ${item.accent}`}>
              <item.icon className="h-[19px] w-[19px]" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
