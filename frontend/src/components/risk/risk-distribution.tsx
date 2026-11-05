import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { RiskSummary } from "@/types/api";
import { AlertTriangle, CheckCircle2, CircleHelp, Minus } from "@/components/ui/icons";

const segments = [
  { key: "critico", label: "Crítico", color: "var(--brand-coral)", icon: AlertTriangle },
  { key: "medio", label: "Médio", color: "var(--brand-indigo)", icon: Minus },
  { key: "baixo", label: "Baixo", color: "var(--brand-blue)", icon: CheckCircle2 },
] as const;

export function RiskDistribution({ data, loading }: { data?: RiskSummary; loading?: boolean }) {
  const values = segments.map((segment) => ({ ...segment, value: data?.summary[segment.key] ?? 0 }));
  const total = data?.total_scored ?? values.reduce((sum, item) => sum + item.value, 0);
  const unscored = data?.summary.sem_score ?? Math.max((data?.total_students ?? total) - total, 0);
  const denominator = total + unscored;
  let cursor = 0;
  const stops = values.map((item) => {
    const start = denominator ? (cursor / denominator) * 100 : 0;
    cursor += item.value;
    const end = denominator ? (cursor / denominator) * 100 : 0;
    return `${item.color} ${start}% ${end}%`;
  });
  if (unscored > 0 && denominator > 0) stops.push(`#e7e9f1 ${(cursor / denominator) * 100}% 100%`);
  const ring = denominator && stops.length ? `conic-gradient(${stops.join(", ")})` : "conic-gradient(#e7e9f1 0% 100%)";

  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="flex-row items-start justify-between space-y-0 border-b border-black/[0.06] pb-4">
        <div>
          <CardTitle className="text-[17px] tracking-[-0.03em]">Panorama de risco</CardTitle>
          <CardDescription className="mt-1">Distribuição dos alunos por faixa de risco</CardDescription>
        </div>
        <span className="rounded-full bg-[rgba(64,80,205,0.1)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--brand-indigo)]">Agora</span>
      </CardHeader>
      <CardContent className="flex flex-col gap-7 pt-4 sm:flex-row sm:items-center sm:gap-9">
        <div className="relative mx-auto grid h-40 w-40 shrink-0 place-items-center sm:mx-0" role="img" aria-label={`Distribuição de risco: ${values.map((item) => `${item.label} ${item.value}`).join(", ")}${unscored ? `, sem score ${unscored}` : ""}`}>
          <div className="absolute inset-0 rounded-full" style={{ background: ring }} />
          <div className="absolute inset-[14px] rounded-full bg-white shadow-inner" />
          <div className="relative text-center">
            {loading ? (
              <div className="mx-auto h-8 w-14 animate-pulse rounded bg-muted" />
            ) : (
              <p className="text-[30px] font-semibold leading-none tracking-[-0.05em] tabular-nums">{total.toLocaleString("pt-BR")}</p>
            )}
            <p className="mt-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">com score</p>
          </div>
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          {values.map((item) => {
            const Icon = item.icon;
            const percent = denominator ? Math.round((item.value / denominator) * 100) : 0;
            return (
              <div key={item.key} className="flex items-center gap-3">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg" style={{ color: item.color, backgroundColor: `color-mix(in srgb, ${item.color} 11%, white)` }}>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                    <span className="font-medium text-foreground">{item.label}</span>
                    <span className="tabular-nums text-muted-foreground">{loading ? "—" : `${item.value.toLocaleString("pt-BR")} · ${percent}%`}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${loading ? 0 : percent}%`, backgroundColor: item.color }} />
                  </div>
                </div>
              </div>
            );
          })}
          {unscored > 0 && (
            <div className="flex items-center gap-3 pt-1">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground"><CircleHelp className="h-4 w-4" /></span>
              <div className="flex-1 text-xs"><span className="font-medium">Sem score</span><span className="float-right tabular-nums text-muted-foreground">{unscored.toLocaleString("pt-BR")}</span></div>
            </div>
          )}
          {!loading && denominator === 0 && (
            <p className="pt-1 text-xs leading-relaxed text-muted-foreground">Importe uma planilha para visualizar a distribuição da sua base.</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
