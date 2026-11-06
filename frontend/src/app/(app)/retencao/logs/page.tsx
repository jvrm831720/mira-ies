"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, CheckCircle2, Clock3, Filter, RefreshCw, SearchX, TriangleAlert } from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { InterventionLog } from "@/types/api";

const statusLabel: Record<string, string> = { dry_run: "Simulado", sent: "Enviado", sending: "Enviando", unknown: "Verificar", skipped: "Ignorado", failed: "Falhou", planned: "Planejado" };

function dateLabel(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function statusStyle(status?: string | null) {
  if (["sent", "delivered", "read"].includes(status || "")) return "bg-[var(--color-green-tint)] text-[var(--color-green)]";
  if (["failed", "unknown", "bounced", "rejected"].includes(status || "")) return "bg-[var(--color-red-tint)] text-[var(--color-red)]";
  if (status === "dry_run") return "bg-[var(--color-blue-tint)] text-[var(--color-blue)]";
  return "bg-muted text-muted-foreground";
}

function LogRow({ log }: { log: InterventionLog }) {
  return (
    <tr className="border-b border-border/70 transition hover:bg-secondary/30">
      <td className="whitespace-nowrap px-4 py-3.5 text-xs text-muted-foreground">{dateLabel(log.created_at)}</td>
      <td className="px-4 py-3.5"><span className="block text-xs font-semibold">{log.matricula || "—"}</span><span className="mt-0.5 block text-[10px] text-muted-foreground">{log.risk_level || ""}</span></td>
      <td className="px-4 py-3.5 text-xs capitalize">{log.channel || "Sem canal"}</td>
      <td className="px-4 py-3.5"><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusStyle(log.status)}`}>{statusLabel[log.status] || log.status}</span></td>
      <td className="px-4 py-3.5"><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusStyle(log.delivery_status)}`}>{log.delivery_status || "—"}</span></td>
      <td className="max-w-[260px] truncate px-4 py-3.5 text-xs text-muted-foreground" title={log.error || log.message_preview || log.skip_reason || "—"}>{log.error || log.message_preview || log.skip_reason || "—"}</td>
    </tr>
  );
}

function LogCard({ log }: { log: InterventionLog }) {
  return (
    <article className="space-y-3 p-4">
      <div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold">Matrícula {log.matricula || "—"}</p><p className="mt-1 text-[11px] text-muted-foreground">{dateLabel(log.created_at)}{log.channel ? ` · ${log.channel}` : ""}</p></div><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusStyle(log.status)}`}>{statusLabel[log.status] || log.status}</span></div>
      <div className="flex flex-wrap gap-2"><span className="rounded-full bg-muted px-2.5 py-1 text-[10px] text-muted-foreground">Entrega: {log.delivery_status || "—"}</span>{log.risk_level && <span className="rounded-full bg-muted px-2.5 py-1 text-[10px] capitalize text-muted-foreground">Risco {log.risk_level}</span>}</div>
      <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{log.error || log.message_preview || log.skip_reason || "Sem detalhes adicionais."}</p>
    </article>
  );
}

export default function RetentionLogsPage() {
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const { data, isLoading, isError, refetch, isFetching } = useQuery({ queryKey: ["retention-logs", channel, status], queryFn: () => api.retentionLogs({ limit: 100, channel: channel || undefined, status: status || undefined }) });
  const logs = useMemo(() => data?.logs || [], [data?.logs]);
  const snapshot = useMemo(() => ({
    total: logs.length,
    delivered: logs.filter((log) => ["delivered", "read"].includes(log.delivery_status || "") || log.status === "sent").length,
    pending: logs.filter((log) => ["sending", "unknown"].includes(log.status)).length,
    failed: logs.filter((log) => ["failed", "bounced", "rejected"].includes(log.delivery_status || "") || log.status === "failed").length,
  }), [logs]);
  const emptyFilter = Boolean(channel || status);

  return (
    <>
      <Header title="Histórico de contatos" subtitle="Acompanhe os registros e o status de entrega da régua." />
      <main className="mx-auto w-full max-w-[1600px] space-y-5 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">Rastreabilidade</p><h2 className="mt-1 text-xl font-semibold tracking-tight">Atividade recente</h2><p className="mt-1 text-sm text-muted-foreground">Até 100 registros no recorte selecionado.</p></div><button type="button" onClick={() => void refetch()} className="inline-flex h-9 items-center justify-center gap-2 self-start rounded-xl border border-border bg-white px-3 text-xs font-semibold transition hover:bg-muted sm:self-auto"><RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} /> Atualizar</button></div>

        <section aria-label="Resumo dos registros filtrados" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <LogStat icon={Activity} label="Registros" value={snapshot.total} color="text-primary bg-secondary" />
          <LogStat icon={CheckCircle2} label="Enviados ou entregues" value={snapshot.delivered} color="text-[var(--color-green)] bg-[var(--color-green-tint)]" />
          <LogStat icon={Clock3} label="Em andamento/verificação" value={snapshot.pending} color="text-[var(--color-blue)] bg-[var(--color-blue-tint)]" />
          <LogStat icon={TriangleAlert} label="Falhas" value={snapshot.failed} color="text-[var(--color-red)] bg-[var(--color-red-tint)]" />
        </section>

        <Card><CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-2 text-xs font-semibold"><span className="grid h-8 w-8 place-items-center rounded-xl bg-secondary text-primary"><Filter className="h-4 w-4" /></span>Filtros</div><div className="grid gap-2 sm:grid-cols-2"><label><span className="sr-only">Filtrar por canal</span><select aria-label="Filtrar por canal" className="h-10 min-w-[180px] rounded-xl border border-input bg-white px-3 text-xs outline-none focus:ring-2 focus:ring-primary/25" value={channel} onChange={(event) => setChannel(event.target.value)}><option value="">Todos os canais</option><option value="whatsapp">WhatsApp</option><option value="email">E-mail</option><option value="sms">SMS</option></select></label><label><span className="sr-only">Filtrar por status</span><select aria-label="Filtrar por status" className="h-10 min-w-[180px] rounded-xl border border-input bg-white px-3 text-xs outline-none focus:ring-2 focus:ring-primary/25" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Todos os status</option><option value="dry_run">Simulado</option><option value="sent">Enviado</option><option value="sending">Enviando</option><option value="unknown">Verificar</option><option value="skipped">Ignorado</option><option value="failed">Falhou</option><option value="planned">Planejado</option></select></label></div></CardContent></Card>

        <Card className="overflow-hidden">
          <div className="border-b border-border px-5 py-4"><h3 className="text-sm font-semibold">Registros de intervenção</h3><p className="mt-1 text-xs text-muted-foreground">O status imediato e a entrega do provider podem divergir até a confirmação do webhook.</p></div>
          {isLoading && <div className="space-y-3 p-5">{Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="h-14 w-full rounded-xl" />)}</div>}
          {isError && <div role="alert" className="m-5 rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-900"><p className="font-semibold">Não foi possível carregar o histórico.</p><button type="button" onClick={() => void refetch()} className="mt-2 font-medium underline">Tentar novamente</button></div>}
          {!isLoading && !isError && logs.length === 0 && <div className="flex flex-col items-center px-5 py-14 text-center"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-muted text-muted-foreground"><SearchX className="h-5 w-5" /></span><p className="mt-4 text-sm font-semibold">{emptyFilter ? "Nenhum registro corresponde aos filtros" : "Ainda não há contatos registrados"}</p><p className="mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">{emptyFilter ? "Altere os filtros para consultar outros registros." : "Depois de iniciar uma simulação ou régua, os detalhes aparecem aqui."}</p></div>}
          {!isLoading && !isError && logs.length > 0 && <><div className="hidden overflow-x-auto lg:block"><table className="w-full min-w-[920px] text-left"><thead className="bg-muted/35 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground"><tr><th className="px-4 py-3">Quando</th><th className="px-4 py-3">Aluno</th><th className="px-4 py-3">Canal</th><th className="px-4 py-3">Execução</th><th className="px-4 py-3">Entrega</th><th className="px-4 py-3">Detalhe</th></tr></thead><tbody>{logs.map((log) => <LogRow key={log.id} log={log} />)}</tbody></table></div><div className="divide-y divide-border lg:hidden">{logs.map((log) => <LogCard key={log.id} log={log} />)}</div><div className="border-t border-border bg-muted/20 px-5 py-3 text-[10px] text-muted-foreground">{logs.length.toLocaleString("pt-BR")} registros apresentados</div></>}
        </Card>
      </main>
    </>
  );
}

function LogStat({ icon: Icon, label, value, color }: { icon: typeof Activity; label: string; value: number; color: string }) {
  return <Card><CardContent className="flex items-center gap-3 p-4"><span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${color}`}><Icon className="h-4 w-4" /></span><div className="min-w-0"><p className="truncate text-[10px] font-medium text-muted-foreground">{label}</p><p className="mt-0.5 text-xl font-semibold tabular-nums">{value.toLocaleString("pt-BR")}</p></div></CardContent></Card>;
}
