"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  ClipboardList,
  Clock3,
  RefreshCw,
  Search,
  XCircle,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { RiskBadge } from "@/components/ui/badge";
import { CriticalList } from "@/components/risk/critical-list";
import { StudentDrawer } from "@/components/students/student-drawer";
import { api } from "@/lib/api";
import type { InterventionLog } from "@/types/api";
import { cn } from "@/lib/utils";

type WorkTab = "planned" | "sending" | "failed" | "critical";

const STATUS_LABEL: Record<string, string> = {
  planned: "Planejada",
  sending: "Em envio",
  sent: "Enviada",
  dry_run: "Dry-run",
  unknown: "Desconhecido",
  failed: "Falha",
  skipped: "Ignorada",
};

const CHANNEL_LABEL: Record<string, string> = {
  whatsapp: "WhatsApp",
  email: "E-mail",
  sms: "SMS",
};

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

function isOverdueByAge(value?: string | null, policyHours = 48) {
  if (!value) return false;
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return false;
  const ageMs = Date.now() - timestamp;
  return ageMs >= 0 && ageMs > policyHours * 60 * 60 * 1000;
}

function formatCount(isLoading: boolean, isError: boolean, value: number | undefined | null) {
  if (isLoading || isError || value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("pt-BR");
}

function scoreLabel(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

export default function WorkCenterPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<WorkTab>("planned");
  const [search, setSearch] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const [riskFilter, setRiskFilter] = useState("");

  const summary = useQuery({
    queryKey: ["risk-summary", "work-center"],
    queryFn: () => api.riskSummary(),
    retry: false,
  });
  const work = useQuery({
    queryKey: ["retention-work-summary", "work-center"],
    queryFn: () => api.retentionWorkSummary(),
    retry: false,
  });
  const planned = useQuery({
    queryKey: ["retention-logs", "planned", "work-center"],
    queryFn: () => api.retentionLogs({ limit: 100, status: "planned" }),
    retry: false,
  });
  const sending = useQuery({
    queryKey: ["retention-logs", "sending", "work-center"],
    queryFn: () => api.retentionLogs({ limit: 100, status: "sending" }),
    retry: false,
  });
  const failed = useQuery({
    queryKey: ["retention-logs", "failed", "work-center"],
    queryFn: () => api.retentionLogs({ limit: 100, status: "failed" }),
    retry: false,
  });
  const critical = useQuery({
    queryKey: ["risk-critical", "work-center"],
    queryFn: () => api.riskCritical(50),
    retry: false,
  });

  const policyHours = work.data?.overdue_policy_hours ?? 48;
  const students = critical.data?.students ?? [];

  const activeLogQuery =
    activeTab === "planned" ? planned : activeTab === "sending" ? sending : activeTab === "failed" ? failed : null;

  const filteredLogs = useMemo(() => {
    const source: InterventionLog[] = activeLogQuery?.data?.logs ?? [];
    let rows = [...source];
    if (activeTab === "planned") {
      rows.sort((a, b) => {
        const ao = isOverdueByAge(a.created_at, policyHours) ? 1 : 0;
        const bo = isOverdueByAge(b.created_at, policyHours) ? 1 : 0;
        if (ao !== bo) return bo - ao;
        return String(b.created_at ?? "").localeCompare(String(a.created_at ?? ""));
      });
    }
    if (channelFilter) {
      rows = rows.filter((r) => r.channel === channelFilter);
    }
    if (riskFilter) {
      rows = rows.filter((r) => r.risk_level === riskFilter);
    }
    const term = search.trim().toLocaleLowerCase("pt-BR");
    if (term) {
      rows = rows.filter((item) =>
        [item.matricula, item.student_id, item.channel, item.status, item.risk_level, item.decision_reason]
          .filter(Boolean)
          .some((value) => String(value).toLocaleLowerCase("pt-BR").includes(term))
      );
    }
    return rows;
  }, [activeLogQuery?.data?.logs, activeTab, channelFilter, riskFilter, search, policyHours]);

  const refreshing =
    summary.isFetching ||
    work.isFetching ||
    planned.isFetching ||
    sending.isFetching ||
    failed.isFetching ||
    critical.isFetching;

  const refreshAll = () => {
    void summary.refetch();
    void work.refetch();
    void planned.refetch();
    void sending.refetch();
    void failed.refetch();
    void critical.refetch();
  };

  const pendingLabel = formatCount(work.isLoading, work.isError, work.data?.pending);
  const overdueLabel = formatCount(work.isLoading, work.isError, work.data?.overdue_48h);
  const failedLabel = formatCount(work.isLoading, work.isError, work.data?.failed);
  const criticalLabel = formatCount(
    summary.isLoading,
    summary.isError,
    summary.data?.summary?.critico
  );
  const sendingCount = sending.isError ? null : (sending.data?.count ?? sending.data?.logs?.length);
  const sendingLabel = formatCount(sending.isLoading, sending.isError, sendingCount ?? null);

  return (
    <>
      <Header
        title="Central de trabalho"
        subtitle="Fila operacional de decisões e intervenções — dados reais do tenant."
      />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-6 px-4 pb-10 pt-5 md:px-8 md:pt-7 xl:px-10">
        <section className="flex flex-col justify-between gap-4 border-b border-[#E5E7EB] pb-5 sm:flex-row sm:items-center">
          <div className="max-w-2xl">
            <p className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#2563EB]">
              <ClipboardList className="h-3.5 w-3.5" /> Operação diária
            </p>
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-[#111827] sm:text-2xl">
              O que precisa de atenção agora
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-[#667085]">
              Decisões planejadas, envios em andamento, falhas e alunos críticos. Atividade operacional ≠
              atribuição de responsável — o backend ainda não persiste dono de tarefa.
            </p>
            {work.data?.generated_at && (
              <p className="mt-2 text-[11px] text-[#98A2B3]">
                Resumo operacional gerado em {formatDate(work.data.generated_at)}
                {work.data.definition ? ` · ${work.data.definition}` : ""}
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={refreshAll}
              disabled={refreshing}
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-[#D0D5DD] bg-white px-4 text-sm font-semibold text-[#344054] transition hover:bg-[#F9FAFB] disabled:opacity-50"
            >
              <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} /> Atualizar
            </button>
            <Link
              href="/retencao"
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#2563EB] px-4 text-sm font-semibold text-white transition hover:bg-[#1D4ED8]"
            >
              Intervenções <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/monitoramento"
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-[#D0D5DD] bg-white px-4 text-sm font-semibold text-[#344054] hover:bg-[#F9FAFB]"
            >
              Monitoramento
            </Link>
          </div>
        </section>

        <section aria-label="Indicadores operacionais" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Metric
            label="Pendentes"
            value={pendingLabel}
            description="status = planned (work-summary)"
            icon={<ClipboardList className="h-5 w-5" />}
          />
          <Metric
            label={`Atrasadas (>${policyHours}h)`}
            value={overdueLabel}
            description="Planejadas além da política provisória"
            icon={<Clock3 className="h-5 w-5" />}
            tone="warning"
          />
          <Metric
            label="Em envio"
            value={sendingLabel}
            description="status = sending (logs)"
            icon={<Activity className="h-5 w-5" />}
          />
          <Metric
            label="Falhas"
            value={failedLabel}
            description="status = failed (work-summary)"
            icon={<XCircle className="h-5 w-5" />}
            tone="danger"
          />
          <Metric
            label="Risco crítico"
            value={criticalLabel}
            description="Classificação atual (risk/summary)"
            icon={<AlertCircle className="h-5 w-5" />}
            tone="critical"
          />
        </section>

        {work.isError && (
          <div
            role="alert"
            className="flex flex-col gap-2 rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 text-sm text-[#B42318] sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="font-semibold">Indicadores operacionais indisponíveis.</p>
              <p className="mt-1 text-xs">Valores não foram substituídos por zero.</p>
            </div>
            <button type="button" onClick={() => void work.refetch()} className="shrink-0 font-semibold underline">
              Tentar novamente
            </button>
          </div>
        )}

        <section className="overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-sm">
          <div className="space-y-4 border-b border-[#EAECF0] px-4 py-4 sm:px-5">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
              <div>
                <h2 className="text-base font-semibold tracking-[-0.02em] text-[#101828]">Fila operacional</h2>
                <p className="mt-1 text-sm text-[#667085]">
                  Fonte: GET /agents/retention/logs e /risk/critical · tenant autenticado
                </p>
              </div>
            </div>

            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div role="tablist" aria-label="Filas de trabalho" className="flex flex-wrap gap-1 rounded-xl bg-[#F2F4F7] p-1">
                {(
                  [
                    { id: "planned" as const, label: "Planejadas", count: pendingLabel },
                    { id: "sending" as const, label: "Em envio", count: sendingLabel },
                    { id: "failed" as const, label: "Falhas", count: failedLabel },
                    { id: "critical" as const, label: "Críticos", count: criticalLabel },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={cn(
                      "inline-flex min-h-9 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium",
                      activeTab === tab.id
                        ? "bg-white text-[#101828] shadow-sm"
                        : "text-[#667085] hover:text-[#344054]"
                    )}
                  >
                    {tab.label}
                    <span className="rounded-md bg-[#F2F4F7] px-1.5 py-0.5 text-xs tabular-nums">{tab.count}</span>
                  </button>
                ))}
              </div>

              {activeTab !== "critical" && (
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={channelFilter}
                    onChange={(e) => setChannelFilter(e.target.value)}
                    aria-label="Filtrar canal"
                    className="h-10 rounded-xl border border-[#D0D5DD] bg-white px-3 text-sm text-[#344054]"
                  >
                    <option value="">Todos os canais</option>
                    <option value="whatsapp">WhatsApp</option>
                    <option value="email">E-mail</option>
                    <option value="sms">SMS</option>
                  </select>
                  <select
                    value={riskFilter}
                    onChange={(e) => setRiskFilter(e.target.value)}
                    aria-label="Filtrar risco"
                    className="h-10 rounded-xl border border-[#D0D5DD] bg-white px-3 text-sm text-[#344054]"
                  >
                    <option value="">Todos os riscos</option>
                    <option value="critico">Crítico</option>
                    <option value="medio">Moderado</option>
                    <option value="baixo">Baixo</option>
                  </select>
                  <label className="relative block min-w-[200px] flex-1 sm:max-w-xs">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#98A2B3]" />
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Matrícula, canal, motivo…"
                      aria-label="Buscar na fila"
                      className="h-10 w-full rounded-xl border border-[#D0D5DD] bg-white pl-9 pr-3 text-sm text-[#101828] outline-none placeholder:text-[#98A2B3] focus:border-[#84ADFF] focus:ring-4 focus:ring-[#EFF4FF]"
                    />
                  </label>
                </div>
              )}
            </div>
          </div>

          {activeTab === "critical" ? (
            <div role="tabpanel" className="p-4 sm:p-5">
              {critical.isError ? (
                <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 text-sm text-[#B42318]">
                  <p className="font-semibold">Não foi possível carregar alunos críticos.</p>
                  <button type="button" onClick={() => void critical.refetch()} className="mt-2 font-semibold underline">
                    Tentar novamente
                  </button>
                </div>
              ) : (
                <>
                  <CriticalList students={students} loading={critical.isLoading} onSelect={setSelectedId} />
                  <p className="mt-3 text-xs text-[#667085]">
                    Classificação crítica não implica, por si, ausência de contato recente. Abra a ficha para
                    contexto e histórico.
                  </p>
                </>
              )}
            </div>
          ) : (
            <div role="tabpanel" className="p-4 sm:p-5">
              {activeLogQuery?.isError ? (
                <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 text-sm text-[#B42318]">
                  <p className="font-semibold">Não foi possível carregar a fila.</p>
                  <p className="mt-1 text-xs">
                    {(activeLogQuery.error as Error)?.message ||
                      "API de logs indisponível. Dados não foram substituídos por exemplos."}
                  </p>
                  <button
                    type="button"
                    onClick={() => void activeLogQuery.refetch()}
                    className="mt-2 font-semibold underline"
                  >
                    Tentar novamente
                  </button>
                </div>
              ) : activeLogQuery?.isLoading ? (
                <div className="space-y-3" aria-label="Carregando fila">
                  {[1, 2, 3, 4].map((item) => (
                    <div key={item} className="h-14 animate-pulse rounded-xl bg-[#F2F4F7]" />
                  ))}
                </div>
              ) : filteredLogs.length === 0 ? (
                <div className="rounded-xl border border-dashed border-[#D0D5DD] bg-[#F9FAFB] px-5 py-10 text-center">
                  <div className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-white text-[#667085] ring-1 ring-[#EAECF0]">
                    <ClipboardList className="h-5 w-5" />
                  </div>
                  <p className="mt-3 text-sm font-semibold text-[#101828]">
                    {search.trim() || channelFilter || riskFilter
                      ? "Nenhum registro com os filtros atuais"
                      : activeTab === "planned"
                        ? "Nenhuma decisão planejada"
                        : activeTab === "sending"
                          ? "Nenhum envio em andamento"
                          : "Nenhuma falha registrada"}
                  </p>
                  <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-[#667085]">
                    A fila reflete apenas InterventionLog do tenant. Ausência de registros não indica
                    estabilidade de risco.
                  </p>
                </div>
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[920px] text-left text-sm">
                      <thead>
                        <tr className="border-b border-[#EAECF0] text-xs text-[#667085]">
                          <th scope="col" className="px-3 py-3 font-medium">
                            Aluno
                          </th>
                          <th scope="col" className="px-3 py-3 font-medium">
                            Risco
                          </th>
                          <th scope="col" className="px-3 py-3 font-medium">
                            Canal
                          </th>
                          <th scope="col" className="px-3 py-3 font-medium">
                            Status
                          </th>
                          <th scope="col" className="px-3 py-3 font-medium">
                            Motivo / decisão
                          </th>
                          <th scope="col" className="px-3 py-3 font-medium">
                            Criada em
                          </th>
                          <th scope="col" className="px-3 py-3 font-medium">
                            Ação
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredLogs.map((item) => {
                          const overdue =
                            item.status === "planned" && isOverdueByAge(item.created_at, policyHours);
                          return (
                            <tr
                              key={item.id}
                              className="border-b border-[#F2F4F7] last:border-0 hover:bg-[#F9FAFB]"
                            >
                              <td className="px-3 py-3.5">
                                {item.student_id ? (
                                  <button
                                    type="button"
                                    onClick={() => setSelectedId(item.student_id!)}
                                    className="text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
                                  >
                                    <span className="block font-semibold text-[#101828] hover:text-[#2563EB]">
                                      {item.matricula || "Abrir ficha"}
                                    </span>
                                    <span className="mt-0.5 block max-w-[160px] truncate text-xs text-[#667085]">
                                      {item.student_id}
                                    </span>
                                  </button>
                                ) : (
                                  <span className="font-medium text-[#344054]">
                                    {item.matricula || "Sem aluno"}
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-3.5">
                                <div className="flex flex-col gap-1">
                                  {item.risk_level ? (
                                    <RiskBadge level={item.risk_level as "baixo" | "medio" | "critico"} />
                                  ) : (
                                    <span className="text-xs text-[#98A2B3]">Sem score</span>
                                  )}
                                  <span className="text-[11px] tabular-nums text-[#667085]">
                                    {scoreLabel(item.risk_score)}
                                  </span>
                                </div>
                              </td>
                              <td className="px-3 py-3.5 text-[#475467]">
                                {item.channel ? CHANNEL_LABEL[item.channel] ?? item.channel : "—"}
                              </td>
                              <td className="px-3 py-3.5">
                                <span
                                  className={cn(
                                    "inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-medium",
                                    overdue
                                      ? "bg-[#FEF3F2] text-[#B42318]"
                                      : item.status === "failed"
                                        ? "bg-[#FEF3F2] text-[#B42318]"
                                        : item.status === "sending"
                                          ? "bg-[#EFF8FF] text-[#175CD3]"
                                          : "bg-[#FFFAEB] text-[#B54708]"
                                  )}
                                >
                                  {overdue
                                    ? `> ${policyHours}h`
                                    : STATUS_LABEL[item.status] ?? item.status}
                                </span>
                                {item.delivery_status && (
                                  <span className="mt-1 block text-[10px] text-[#98A2B3]">
                                    entrega: {item.delivery_status}
                                  </span>
                                )}
                              </td>
                              <td className="max-w-[220px] px-3 py-3.5 text-[12px] text-[#475467]">
                                <span className="line-clamp-2">
                                  {item.decision_reason ||
                                    item.skip_reason ||
                                    item.error ||
                                    item.message_preview ||
                                    "—"}
                                </span>
                              </td>
                              <td className="whitespace-nowrap px-3 py-3.5 text-[#475467]">
                                {formatDate(item.created_at)}
                              </td>
                              <td className="px-3 py-3.5">
                                <div className="flex flex-col gap-1">
                                  {item.student_id && (
                                    <Link
                                      href={`/alunos/${item.student_id}`}
                                      className="inline-flex items-center gap-1 text-xs font-semibold text-[#2563EB] hover:text-[#1D4ED8]"
                                    >
                                      Ficha <ArrowRight className="h-3.5 w-3.5" />
                                    </Link>
                                  )}
                                  <Link
                                    href="/retencao"
                                    className="inline-flex items-center gap-1 text-xs font-medium text-[#667085] hover:text-[#344054]"
                                  >
                                    Intervenções
                                  </Link>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-3 text-xs leading-relaxed text-[#667085]">
                    Até 100 registros por status. Contagens oficiais de pendentes/atrasados/falhas vêm de
                    work-summary. Status e delivery_status são campos distintos: envio ≠ entrega ≠ leitura.
                    Sem responsável atribuído no modelo atual.
                  </p>
                </>
              )}
            </div>
          )}
        </section>

        <div className="flex flex-col justify-between gap-3 rounded-xl border border-[#D1E0FF] bg-[#EFF4FF] p-4 sm:flex-row sm:items-center">
          <div>
            <p className="text-sm font-semibold text-[#194185]">Executar ou registrar intervenções</p>
            <p className="mt-1 text-xs leading-relaxed text-[#3538CD]">
              Campanhas e logs detalhados ficam em Intervenções. Evolução de risco e analytics em
              Monitoramento.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/retencao"
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#B2CCFF] bg-white px-3 text-xs font-semibold text-[#1849A9]"
            >
              Intervenções <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <Link
              href="/monitoramento"
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#B2CCFF] bg-white px-3 text-xs font-semibold text-[#1849A9]"
            >
              Monitoramento
            </Link>
          </div>
        </div>
      </main>
      <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    </>
  );
}

function Metric({
  label,
  value,
  description,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: string;
  description: string;
  icon: React.ReactNode;
  tone?: "neutral" | "warning" | "danger" | "critical";
}) {
  const tones = {
    neutral: "bg-[#F2F4F7] text-[#475467]",
    warning: "bg-[#FFFAEB] text-[#B54708]",
    danger: "bg-[#FEF3F2] text-[#B42318]",
    critical: "bg-[#FFF1F3] text-[#C01048]",
  };
  return (
    <article className="rounded-2xl border border-[#E5E7EB] bg-white p-4 shadow-sm sm:p-5">
      <div className="flex items-center gap-3">
        <span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl", tones[tone])}>
          {icon}
        </span>
        <p className="text-sm font-medium text-[#475467]">{label}</p>
      </div>
      <p className="mt-4 text-3xl font-semibold tracking-tight tabular-nums text-[#101828]">{value}</p>
      <p className="mt-1 text-xs leading-relaxed text-[#667085]">{description}</p>
    </article>
  );
}
