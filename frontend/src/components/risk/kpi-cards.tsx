import { Card, ex Content } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { RiskSummary } from "@/types/api";
import { AlertTriangle, Activity, CheckCircle2, Users } from "lucide-react";

export function KpiCards({ data, loading }: { data?: RiskSummary; loading?: boolean }) {
  const s = data?.summary;
  const items = [
    { label: "Crítico", value: s?.critico ?? 0, icon: AlertTriangle, accent: "text-red-600 bg-red-50", ring: "ring-red-100" },
    { label: "Médio", value: s?.medio ?? 0, icon: Activity, accent: "text-amber-600 bg-amber-50", ring: "ring-amber-100" },
    { label: "Baixo", value: s?.baixo ?? 0, icon: CheckCircle2, accent: "text-emerald-600 bg-emerald-50", ring: "ring-emerald-100" },
    { label: "Total pontuados", value: data?.total_scored ?? (s ? s.baixo + s.medio + s.critico : 0), icon: Users, accent: "text-primary bg-primary/10", ring: "ring-primary/10" },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <Card key={item.label} className={`ring-1 ${item.ring}`}>
          <CardContent className="flex items-center justify-between p-5">
            <div>
              <p className="text-sm text-muted-foreground">{item.label}</p>
              {loading ? (
                <Skeleton className="mt-2 h-8 w-16" />
              ) : (
                <p className="mt-1 text-3xl font-semibold tracking-tight">{item.value}</p>
              )}
            </div>
            <div className={`rounded-xl p-3 ${item.accent}`}>
              <item.icon className="h-5 w-5" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
