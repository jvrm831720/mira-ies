"use client";

import { useQuery } from "@tanstack/react-query";
import { MessageSquare, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type ChannelKey = "whatsapp" | "email" | "sms";

const CHANNEL_LABEL: Record<ChannelKey, string> = {
  whatsapp: "WhatsApp",
  email: "E-mail",
  sms: "SMS",
};

function pctLabel(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function numLabel(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("pt-BR");
}

function moneyLabel(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/**
 * Painel alinhado ao contrato *efetivo* de GET /api/v1/agents/retention/analytics
 * (backend/app/api/agents_analytics.py), não ao tipo TypeScript expandido.
 *
 * Campos reais do backend:
 * - period_days, generated_at
 * - summary: messages_sent, unique_students_contacted, retained_students,
 *   retention_rate_pct, estimated_cost_brl_total
 * - channels[ch]: messages_sent, delivery_rate_pct, engagement_rate_pct,
 *   bounce_rate_pct, estimated_cost_brl, unique_students_contacted,
 *   attribution.retained_students, average_latency_ms
 * - providers: channel, provider, average_latency_ms, attempts
 *
 * Limitações documentadas na UI:
 * - messages_sent inclui status sent e dry_run.
 * - retention_rate_pct = alunos com outcome "stayed" / alunos contactados — NÃO é causalidade.
 * - Sem série temporal no endpoint; apenas agregado do recorte `days`.
 */
export function RetentionAnalyticsPanel({ days }: { days: number }) {
  const query = useQuery({
    queryKey: ["retention-analytics", days],
    queryFn: () => api.retentionAnalytics(days),
    retry: false,
  });

  const data = query.data as
    | {
        period_days?: number;
        generated_at?: string;
        summary?: {
          messages_sent?: number;
          unique_students_contacted?: number;
          retained_students?: number;
          retention_rate_pct?: number | null;
          estimated_cost_brl_total?: number | null;
        };
        channels?: Record<
          string,
          {
            messages_sent?: number;
            delivery_rate_pct?: number | null;
            engagement_rate_pct?: number | null;
            bounce_rate_pct?: number | null;
            estimated_cost_brl?: number | null;
            unique_students_contacted?: number;
            attribution?: { retained_students?: number };
            average_latency_ms?: number | null;
          }
        >;
        providers?: Array<{
          channel?: string;
          provider?: string;
          average_latency_ms?: number | null;
          attempts?: number;
          successes?: number;
          failures?: number;
          success_rate_pct?: number | null;
        }>;
        attribution_note?: string;
        cost_note?: string;
      }
    | undefined;

  const summary = data?.summary;
  const channels = data?.channels;
  const channelKeys = (["whatsapp", "email", "sms"] as ChannelKey[]).filter(
    (k) => channels && channels[k] != null
  );
  const totalSent = summary?.messages_sent ?? 0;
  const hasVolume = totalSent > 0 || (summary?.unique_students_contacted ?? 0) > 0;

  return (
    <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[14px] font-semibold text-[#101828]">Analytics de retenção</h2>
          <p className="mt-1 text-[11px] text-[#667085]">
            Agregados de InterventionLog no tenant autenticado · últimos {" "}
            {data?.period_days ?? days} dias
            {data?.generated_at
              ? ` · gerado em ${new Date(data.generated_at).toLocaleString("pt-BR")}`
              : ""}
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[#EFF8FF] px-2.5 py-1 text-[10px] font-medium text-[#175CD3]">
          <MessageSquare className="h-3 w-3" />
          GET /agents/retention/analytics
        </span>
      </div>

      {query.isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[1, 2, 3, 4].map((n) => (
            <Skeleton key={n} className="h-24 rounded-lg" />
          ))}
        </div>
      )}

      {query.isError && (
        <div
          role="alert"
          className="rounded-lg border border-[#FECDCA] bg-[#FEF3F2] p-4 text-[12px] text-[#B42318]"
        >
          Não foi possível carregar o analytics de retenção. Verifique permissões e disponibilidade da
          API.
        </div>
      )}

      {!query.isLoading && !query.isError && data && !hasVolume && (
        <div className="rounded-lg bg-[#F8FAFC] p-6 text-center">
          <p className="text-[13px] font-semibold text-[#344054]">Sem intervenções no período</p>
          <p className="mt-1 text-[12px] text-[#667085]">
            Não há registros de InterventionLog com status sent/dry_run nos últimos{" "}
            {data.period_days ?? days} dias para este tenant. Isso não indica estabilidade do risco.
          </p>
        </div>
      )}

      {!query.isLoading && !query.isError && data && hasVolume && (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="Mensagens registradas"
              value={numLabel(summary?.messages_sent)}
              hint="Contagem de logs com status sent ou dry_run"
            />
            <Stat
              label="Alunos contactados"
              value={numLabel(summary?.unique_students_contacted)}
              hint="Estudantes distintos com ao menos um envio no período"
            />
            <Stat
              label="Outcome 'stayed'"
              value={numLabel(summary?.retained_students)}
              hint="Alunos contactados com desfecho registrado como stayed"
            />
            <Stat
              label="Taxa stayed / contactados"
              value={pctLabel(summary?.retention_rate_pct)}
              hint="Proporção descritiva — não prova causalidade da intervenção"
              caution
            />
          </div>

          {(summary?.estimated_cost_brl_total != null || data.cost_note) && (
            <p className="text-[11px] text-[#667085]">
              Custo estimado no período:{" "}
              <strong className="text-[#344054]">
                {moneyLabel(summary?.estimated_cost_brl_total)}
              </strong>
              {data.cost_note ? ` · ${data.cost_note}` : " · baseado na configuração de custo por canal"}
            </p>
          )}

          <div className="rounded-lg border border-[#FEDF89] bg-[#FFFAEB] p-3">
            <div className="flex items-start gap-2">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#B54708]" />
              <div className="text-[11px] leading-relaxed text-[#93370D]">
                <p className="font-semibold">Leitura correta dos indicadores</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-4">
                  <li>
                    Envio de mensagem ≠ retenção comprovada. dry_run entra no volume de mensagens
                    registradas.
                  </li>
                  <li>
                    Ausência de desfecho (outcome nulo) não é contada como falha nem como permanência.
                  </li>
                  <li>
                    A taxa stayed/contactados descreve coocorrência de outcome registrado; não afirma
                    que a mensagem causou a permanência.
                  </li>
                  <li>
                    Este endpoint não expõe série temporal diária — apenas o agregado do recorte de{" "}
                    {data.period_days ?? days} dias.
                  </li>
                </ul>
                {data.attribution_note && (
                  <p className="mt-2 text-[#B54708]">{data.attribution_note}</p>
                )}
              </div>
            </div>
          </div>

          {channelKeys.length > 0 && (
            <div>
              <h3 className="mb-3 text-[12px] font-semibold text-[#344054]">Por canal</h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-[12px]">
                  <thead className="bg-[#F9FAFB] text-[10px] font-semibold uppercase tracking-[0.05em] text-[#667085]">
                    <tr>
                      <th className="px-3 py-2">Canal</th>
                      <th className="px-3 py-2">Mensagens</th>
                      <th className="px-3 py-2">Alunos</th>
                      <th className="px-3 py-2">Entrega %</th>
                      <th className="px-3 py-2">Engajamento %</th>
                      <th className="px-3 py-2">Bounce %</th>
                      <th className="px-3 py-2">Stayed</th>
                      <th className="px-3 py-2">Custo est.</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#EAECF0]">
                    {channelKeys.map((key) => {
                      const ch = channels![key];
                      return (
                        <tr key={key}>
                          <td className="px-3 py-2.5 font-medium text-[#101828]">
                            {CHANNEL_LABEL[key]}
                          </td>
                          <td className="px-3 py-2.5 tabular-nums">{numLabel(ch.messages_sent)}</td>
                          <td className="px-3 py-2.5 tabular-nums">
                            {numLabel(ch.unique_students_contacted)}
                          </td>
                          <td className="px-3 py-2.5 tabular-nums">
                            {pctLabel(ch.delivery_rate_pct)}
                          </td>
                          <td className="px-3 py-2.5 tabular-nums">
                            {pctLabel(ch.engagement_rate_pct)}
                          </td>
                          <td className="px-3 py-2.5 tabular-nums">{pctLabel(ch.bounce_rate_pct)}</td>
                          <td className="px-3 py-2.5 tabular-nums">
                            {numLabel(ch.attribution?.retained_students)}
                          </td>
                          <td className="px-3 py-2.5 tabular-nums">
                            {moneyLabel(ch.estimated_cost_brl)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[10px] text-[#667085]">
                Taxas de entrega/engajamento/bounce usam o denominador de mensagens do canal no
                período (backend). Latência média, quando disponível, vem de ProviderCallMetric.
              </p>

              {/* Barras simples de volume por canal — SVG mínimo */}
              <div className="mt-4 space-y-2">
                {channelKeys.map((key) => {
                  const sent = channels![key].messages_sent ?? 0;
                  const max = Math.max(...channelKeys.map((k) => channels![k].messages_sent ?? 0), 1);
                  const width = Math.round((sent / max) * 100);
                  return (
                    <div key={key} className="flex items-center gap-3 text-[11px]">
                      <span className="w-16 shrink-0 text-[#475467]">{CHANNEL_LABEL[key]}</span>
                      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-[#F2F4F7]">
                        <div
                          className="h-full rounded-full bg-[#2563EB]"
                          style={{ width: `${width}%` }}
                          title={`${sent} mensagens`}
                        />
                      </div>
                      <span className="w-10 shrink-0 text-right tabular-nums text-[#344054]">
                        {sent}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {Array.isArray(data.providers) && data.providers.length > 0 && (
            <div>
              <h3 className="mb-2 text-[12px] font-semibold text-[#344054]">Provedores (latência)</h3>
              <ul className="space-y-1.5 text-[12px] text-[#475467]">
                {data.providers.map((p, idx) => (
                  <li
                    key={`${p.channel}-${p.provider}-${idx}`}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#EAECF0] px-3 py-2"
                  >
                    <span>
                      <strong className="text-[#101828]">{p.provider || "—"}</strong>
                      <span className="text-[#667085]"> · {p.channel || "canal n/d"}</span>
                    </span>
                    <span className="tabular-nums text-[11px]">
                      {p.attempts != null ? `${numLabel(p.attempts)} tentativas` : ""}
                      {p.average_latency_ms != null
                        ? ` · ${Math.round(p.average_latency_ms)} ms méd.`
                        : ""}
                      {p.success_rate_pct != null ? ` · sucesso ${pctLabel(p.success_rate_pct)}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Stat({
  label,
  value,
  hint,
  caution,
}: {
  label: string;
  value: string;
  hint: string;
  caution?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-white p-4",
        caution ? "border-[#FEDF89] bg-[#FFFAEB]/ : "border-[#E5E7EB]"
      )}
    >
      <p className="text-[11px] font-medium text-[#667085]">{label}</p>
      <p className="mt-2 text-[22px] font-semibold tracking-[-0.03em] text-[#101828]">{value}</p>
      <p className="mt-1 text-[10px] leading-relaxed text-[#667085]">{hint}</p>
    </div>
  );
}
