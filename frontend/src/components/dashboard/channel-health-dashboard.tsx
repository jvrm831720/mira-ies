"use client";

import { Activity, AlertCircle, ArrowDownRight, ArrowUpRight, BarChart3, CheckCircle2, Clock3, Mail, MessageCircle, MousePointerClick, RefreshCw, Smartphone, Users, Wallet } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { RetentionAnalytics } from "@/types/api";

const channelMeta = [
  { key: "whatsapp", label: "WhatsApp", Icon: MessageCircle },
  { key: "email", label: "E-mail", Icon: Mail },
  { key: "sms", label: "SMS", Icon: Smartphone },
] as const;

const fmtNumber = (value: number | null | undefined) =>
  value == null ? "—" : value.toLocaleString("pt-BR");
const fmtPct = (value: number | null | undefined) =>
  value == null ? "—" : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
const fmtMoney = (value: number | null | undefined) =>
  value == null ? "Não configurado" : value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const fmtLatency = (value: number | null | undefined) =>
  value == null ? "—" : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ms`;

function StatCard({ title, value, detail, Icon }: { title: string; value: string; detail: string; Icon: typeof Activity }) {
  return (
    <div className="rounded-2xl border border-black/[0.06] bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-semibold text-neutral-500">{title}</p>
        <span className="grid h-8 w-8 place-items-center rounded-xl bg-[rgba(64,80,205,0.08)] text-[var(--brand-indigo)]"><Icon className="h-4 w-4" /></span>
      </div>
      <p className="mt-3 text-[25px] font-semibold tracking-[-0.04em] text-neutral-950 tabular-nums">{value}</p>
      <p className="mt-1 text-[10px] leading-relaxed text-neutral-500">{detail}</p>
    </div>
  );
}

export function ChannelHealthDashboard({ data, loading, error, onRetry }: {
  data?: RetentionAnalytics;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-start justify-between gap-3 border-b border-black/[0.06] pb-4">
        <div>
          <CardTitle className="text-[17px] tracking-[-0.03em]">Analytics de retenção</CardTitle>
          <CardDescription className="mt-1">Entrega, engajamento, retorno acadêmico e saúde dos provedores nos últimos {data?.period_days ?? 30} dias.</CardDescription>
        </div>
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[rgba(64,80,205,0.09)] text-[var(--brand-indigo)]"><BarChart3 className="h-4 w-4" /></span>
      </CardHeader>
      <CardContent className="space-y-5 pt-5">
        {loading ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}
          </div>
        ) : error || !data ? (
          <div className="flex flex-col items-start justify-between gap-3 rounded-2xl border border-dashed border-neutral-200 p-5 sm:flex-row sm:items-center">
            <div className="flex gap-2.5">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <div><p className="text-sm font-semibold text-neutral-800">Analytics indisponíveis</p><p className="mt-1 text-xs text-neutral-500">Confira a API e tente consultar novamente.</p></div>
            </div>
            <button type="button" onClick={onRetry} className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-200 px-3 py-2 text-xs font-semibold text-neutral-700 hover:bg-neutral-50"><RefreshCw className="h-3.5 w-3.5" /> Tentar novamente</button>
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard title="Mensagens enviadas" value={fmtNumber(data.summary.messages_sent)} detail={`${fmtNumber(data.summary.unique_students_contacted)} alunos únicos contatados`} Icon={Activity} />
              <StatCard title="Alunos retidos" value={fmtNumber(data.summary.retained_students)} detail={`Cobertura de desfecho: ${fmtPct(data.summary.attribution_coverage_pct)}`} Icon={Users} />
              <StatCard title="Taxa de retenção atribuída" value={fmtPct(data.summary.retention_rate_pct)} detail={`${fmtNumber(data.summary.attributed_students)} alunos com desfecho conhecido`} Icon={CheckCircle2} />
              <StatCard title="Custo estimado" value={fmtMoney(data.summary.estimated_cost_brl_total)} detail={`${data.summary.cost_configured_channels}/3 canais com custo configurado`} Icon={Wallet} />
            </div>

            <section>
              <div className="mb-3 flex items-center justify-between gap-3">
                <div><h3 className="text-sm font-semibold text-neutral-900">Saúde por canal</h3><p className="mt-1 text-[11px] text-neutral-500">Taxa de entrega, rejeição, engajamento e latência média.</p></div>
              </div>
              <div className="overflow-x-auto rounded-xl border border-black/[0.06]">
                <table className="w-full min-w-[850px] text-left text-xs">
                  <thead className="bg-neutral-50 text-[10px] uppercase tracking-wide text-neutral-500">
                    <tr>
                      <th className="px-3 py-3 font-semibold">Canal</th>
                      <th className="px-3 py-3 font-semibold">Enviadas</th>
                      <th className="px-3 py-3 font-semibold">Entrega</th>
                      <th className="px-3 py-3 font-semibold">Bounce/rejeição</th>
                      <th className="px-3 py-3 font-semibold">Engajamento</th>
                      <th className="px-3 py-3 font-semibold">Retenção atribuída</th>
                      <th className="px-3 py-3 font-semibold">Latência</th>
                      <th className="px-3 py-3 font-semibold">Custo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {channelMeta.map(({ key, label, Icon }) => {
                      const channel = data.channels[key];
                      return (
                        <tr key={key} className="border-t border-black/[0.05]">
                          <td className="px-3 py-3"><div className="flex items-center gap-2 font-semibold text-neutral-800"><Icon className="h-4 w-4 text-[var(--brand-indigo)]" />{label}</div></td>
                          <td className="px-3 py-3 tabular-nums">{fmtNumber(channel.messages_sent)}</td>
                          <td className="px-3 py-3 tabular-nums">{fmtPct(channel.delivery_rate_pct)}</td>
                          <td className="px-3 py-3 tabular-nums">{fmtPct(channel.bounce_rate_pct)}</td>
                          <td className="px-3 py-3 tabular-nums">{fmtPct(channel.engagement_rate_pct)}</td>
                          <td className="px-3 py-3 tabular-nums"><span className="font-semibold">{fmtPct(channel.attribution.retention_rate_pct)}</span><span className="mt-0.5 block text-[10px] text-neutral-500">{fmtNumber(channel.attribution.retained_students)} retidos</span></td>
                          <td className="px-3 py-3 tabular-nums">{fmtLatency(channel.average_latency_ms)}</td>
                          <td className="px-3 py-3 tabular-nums">{fmtMoney(channel.estimated_cost_brl_total)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <div className="mb-3"><h3 className="text-sm font-semibold text-neutral-900">Saúde dos provedores</h3><p className="mt-1 text-[11px] text-neutral-500">Tentativas individuais, incluindo failover, com latência medida no envio.</p></div>
              {data.providers.length === 0 ? <p className="rounded-xl bg-neutral-50 px-4 py-5 text-xs text-neutral-500">Ainda não há tentativas reais de provedores registradas no período.</p> : (
                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {data.providers.map((provider) => (
                    <div key={`${provider.channel}-${provider.provider}`} className="rounded-xl border border-black/[0.06] p-3.5">
                      <div className="flex items-start justify-between gap-2"><div><p className="text-xs font-semibold capitalize text-neutral-900">{provider.provider.replaceAll("_", " ")}</p><p className="mt-1 text-[10px] capitalize text-neutral-500">{provider.channel}</p></div><span className="rounded-full bg-neutral-100 px-2 py-1 text-[10px] font-semibold text-neutral-700">{fmtPct(provider.success_rate_pct)} sucesso</span></div>
                      <div className="mt-3 grid grid-cols-3 gap-2">
                        <div><p className="text-[10px] text-neutral-500">Tentativas</p><p className="mt-1 text-sm font-semibold tabular-nums">{fmtNumber(provider.attempts)}</p></div>
                        <div><p className="text-[10px] text-neutral-500">Falhas</p><p className="mt-1 text-sm font-semibold tabular-nums">{fmtNumber(provider.failures)}</p></div>
                        <div><p className="text-[10px] text-neutral-500">Latência média</p><p className="mt-1 text-sm font-semibold tabular-nums">{fmtLatency(provider.average_latency_ms)}</p></div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
            <div className="flex items-start gap-2 rounded-xl border border-[rgba(64,80,205,0.12)] bg-[rgba(64,80,205,0.04)] px-3 py-2.5"><MousePointerClick className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand-indigo)]" /><p className="text-[10px] leading-relaxed text-neutral-600">Engajamento considera leitura, clique e resposta recebida por webhook. {data.attribution_note} {data.cost_note}</p></div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
