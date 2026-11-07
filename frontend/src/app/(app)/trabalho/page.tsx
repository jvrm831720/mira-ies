"use client";

import { Suspense, useMemo, useState } from "react";
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
} from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { RiskBadge } from "@/components/ui/badge";
import { CriticalList } from "@/components/risk/critical-list";
import { StudentDrawer } from "@/components/students/student-drawer";
import { api } from "@/lib/api";
import type { InterventionLog } from "@/types/api";
import type { CreateFromLogDraft } from "@/types/work";
import { cn } from "@/lib/utils";
import { WorkActivitiesPanel } from "@/components/work/work-activities-panel";
import { WorkInbox } from "@/components/work/work-inbox";

type WorkTab = "planned" | "sending" | "failed" | "critical";

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
  return Date.now() - timestamp > policyHours * 60 * 60 * 1000;
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
  const [createDraft, setCreateDraft] = useState<CreateFromLogDraft | null>(null);
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
    let rows: InterventionLog[] = [...(activeLogQuery?.data?.logs ?? [])];
    if (activeTab === "planned") {
      rows.sort((a, b) => {
        const ao = isOverdueByAge(a.created_at, policyHours) ? 1 : 0;
        const bo = isOverdueByAge(b.created_at, policyHours) ? 1 : 0;
        if (ao !== bo) return bo - ao;
        return String(b.created_at ?? "").localeCompare(String(a.created_at ?? ""));
      });
    }
    if (channelFilter) rows = rows.filter((r) => r.channel === channelFilter);
    if (riskFilter) rows = rows.filter((r) => r.risk_level === riskFilter);
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
    summary.isFetching || work.isFetching || planned.isFetching || sending.isFetching || failed.isFetching || critical.isFetching;

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
  const criticalLabel = formatCount(summary.isLoading, summary.isError, summary.data?.summary?.critico);
  const sendingCount = sending.isError ? null : (sending.data?.count ?? sending.data?.logs?.length);
  const sendingLabel = formatCount(sending.isLoading, sending.isError, sendingCount ?? null);

  const startCreateFromLog = (item: InterventionLog) => {
    const channelLabel =
      item.channel === "whatsapp"
        ? "WhatsApp"
        : item.channel === "email"
          ? "E-mail"
          : item.channel === "sms"
            ? "SMS"
            : item.channel || "canal";
    const reason = (item.decision_reason || "").trim();
    const suggested = reason
      ? `Follow-up ${channelLabel}: ${reason.slice(0, 80)}`
      : `Follow-up ${channelLabel}${item.matricula ? ` · ${item.matricula}` : ""}`;
    setCreateDraft({
      student_id: item.student_id ?? null,
      intervention_log_id: item.id,
      matricula: item.matricula ?? null,
      channel: item.channel ?? null,
      decision_reason: item.decision_reason ?? null,
      status: item.status ?? null,
      suggested_title: suggested.slice(0, 200),
    });
    window.setTimeout(() => {
      document.querySelector("[data-work-activities]")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  };

  return (
    <>
      <Header
        title="Meu Trabalho"
        subtitle="Entrada operacional central · atividades humanas com prioridade explicada e execução auditável."
      />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-6 px-4 pb-10 pt-5 md:px-8 md:pt-7 xl:px-10">
        <Suspense fallback={<p role="status" className="p-5 text-xs">Carregando Meu Trabalho…</p>}><WorkInbox /></Suspense>
        <details className="rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white p-3">
          <summary className="cursor-pointer px-2 py-2 text-xs font-semibold text-[var(--color-slate-600)]">
            Explorar diagnósticos legados: envios, intervenções e ferramentas avançadas
          </summary>
          <div className="mt-4 space-y-5">
        <section className="flex flex-col justify-between gap-4 border-b border-[var(--color-border)] pb-5 sm:flex-row sm:items-center">
          <div className="max-w-2xl">
            <p className="mb-1 flex items-center gap-2 text-[length:var(--type-caption)] font-semibold uppercase tracking-[0.12em] text-[var(--color-blue)]">
              <ClipboardList className="h-3.5 w-3.5" /> Operação diária
            </p>
            <h2 className="text-xl font-semibold tracking-[-0.035em] text-[var(--color-ink)] sm:text-2xl">
              O que precisa de atenção agora
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-[var(--color-slate-600)]">
              Decisões planejadas, envios em andamento, falhas e alunos críticos. Atividades operacionais
              com responsável, prazo e histórico ficam na seção abaixo (persistidas no tenant).
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={refreshAll}
              disabled={refreshing}
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-[var(--color-blue-tint-border)] bg-white px-4 text-sm font-semibold text-[var(--color-blue)] transition hover:bg-[var(--color-blue-tint)] disabled:opacity-50"
            >
              <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} /> Atualizar
            </button>
            <Link
              href="/retencao"
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-[var(--color-blue)] px-4 text-sm font-semibold text-white transition hover:bg-[var(--color-blue)]"
            >
              Intervenções <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </section>

        <section aria-label="Indicadores operacionais" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Metric label="Pendentes" value={pendingLabel} description="status = planned" icon={<ClipboardList className="h-5 w-5" />} />
          <Metric label={`Atrasadas (>${policyHours}h)`} value={overdueLabel} description="Planejadas além da política" icon={<Clock3 className="h-5 w-5" />} tone="warning" />
          <Metric label="Em envio" value={sendingLabel} description="status = sending" icon={<Activity className="h-5 w-5" />} />
          <Metric label="Falhas" value={failedLabel} description="status = failed" icon={<XCircle className="h-5 w-5" />} tone="danger" />
          <Metric label="Risco crítico" value={criticalLabel} description="risk/summary" icon={<AlertCircle className="h-5 w-5" />} tone="critical" />
        </section>

        <div data-work-activities>
          <WorkActivitiesPanel createDraft={createDraft} onDraftConsumed={() => setCreateDraft(null)} />
        </div>

        <section className="overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-sm">
          <div className="space-y-4 border-b border-[var(--color-border)] px-4 py-4 sm:px-5">
            <h2 className="text-base font-semibold tracking-[-0.02em] text-[var(--color-ink)]">Fila operacional</h2>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div role="tablist" className="flex flex-wrap gap-1 rounded-xl bg-[var(--color-blue-tint)] p-1">
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
                      activeTab === tab.id ? "bg-white text-[var(--color-ink)] shadow-sm" : "text-[var(--color-slate-600)] hover:text-[var(--color-blue)]"
                    )}
                  >
                    {tab.label}
                    <span className="rounded-md bg-[var(--color-blue-tint)] px-1.5 py-0.5 text-xs tabular-nums">{tab.count}</span>
                  </button>
                ))}
              </div>
              {activeTab !== "critical" && (
                <div className="flex flex-wrap items-center gap-2">
                  <select value={channelFilter} onChange={(e) => setChannelFilter(e.target.value)} className="h-10 rounded-xl border border-[var(--color-blue-tint-border)] bg-white px-3 text-sm">
                    <option value="">Todos os canais</option>
                    <option value="whatsapp">WhatsApp</option>
                    <option value="email">E-mail</option>
                    <option value="sms">SMS</option>
                  </select>
                  <select value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)} className="h-10 rounded-xl border border-[var(--color-blue-tint-border)] bg-white px-3 text-sm">
                    <option value="">Todos os riscos</option>
                    <option value="critico">Crítico</option>
                    <option value="medio">Moderado</option>
                    <option value="baixo">Baixo</option>
                  </select>
                  <label className="relative block min-w-[200px] flex-1 sm:max-w-xs">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-muted)]" />
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Matrícula, canal, motivo…"
                      className="h-10 w-full rounded-xl border border-[var(--color-blue-tint-border)] bg-white pl-9 pr-3 text-sm outline-none focus:border-[var(--color-blue-tint-border)] focus:ring-4 focus:ring-[var(--color-blue-tint)]"
                    />
                  </label>
                </div>
              )}
            </div>
          </div>

          {activeTab === "critical" ? (
            <div role="tabpanel" className="p-4 sm:p-5">
              {critical.isError ? (
                <div role="alert" className="rounded-xl border border-[var(--color-red-tint)] bg-[var(--color-red-tint)] p-4 text-sm text-[var(--color-red)]">
                  Não foi possível carregar alunos críticos.
                </div>
              ) : (
                <CriticalList students={students} loading={critical.isLoading} onSelect={setSelectedId} />
              )}
            </div>
          ) : (
            <div role="tabpanel" className="p-4 sm:p-5">
              {activeLogQuery?.isError ? (
                <div role="alert" className="rounded-xl border border-[var(--color-red-tint)] bg-[var(--color-red-tint)] p-4 text-sm text-[var(--color-red)]">
                  Não foi possível carregar a fila.
                  <button type="button" onClick={() => void activeLogQuery.refetch()} className="mt-2 block font-semibold underline">
                    Tentar novamente
                  </button>
                </div>
              ) : activeLogQuery?.isLoading ? (
                <div className="space-y-3">{[1, 2, 3].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-[var(--color-blue-tint)]" />)}</div>
              ) : filteredLogs.length === 0 ? (
                <div className="rounded-xl border border-dashed border-[var(--color-blue-tint-border)] bg-[var(--color-blue-tint)] px-5 py-10 text-center text-sm text-[var(--color-slate-600)]">
                  Nenhum registro na fila com os filtros atuais.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[920px] text-left text-sm">
                    <thead>
                      <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-slate-600)]">
                        <th className="px-3 py-3 font-medium">Aluno</th>
                        <th className="px-3 py-3 font-medium">Risco</th>
                        <th className="px-3 py-3 font-medium">Canal</th>
                        <th className="px-3 py-3 font-medium">Status</th>
                        <th className="px-3 py-3 font-medium">Criado</th>
                        <th className="px-3 py-3 font-medium">Motivo</th>
                        <th className="px-3 py-3 font-medium">Ações</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredLogs.map((item) => (
                        <tr key={item.id} className="border-b border-[var(--color-blue-tint)]">
                          <td className="px-3 py-3.5">
                            {item.student_id ? (
                              <button type="button" onClick={() => setSelectedId(item.student_id!)} className="text-left">
                                <span className="block font-semibold text-[var(--color-ink)] hover:text-[var(--color-blue)]">
                                  {item.matricula || "Abrir ficha"}
                                </span>
                                <span className="mt-0.5 block max-w-[160px] truncate text-xs text-[var(--color-slate-600)]">{item.student_id}</span>
                              </button>
                            ) : (
                              <span className="font-medium text-[var(--color-blue)]">{item.matricula || "Sem aluno"}</span>
                            )}
                          </td>
                          <td className="px-3 py-3.5">
                            {item.risk_level ? (
                              <RiskBadge level={item.risk_level as "baixo" | "medio" | "critico"} />
                            ) : (
                              <span className="text-xs text-[var(--color-muted)]">Sem score</span>
                            )}
                            <span className="mt-1 block text-[length:var(--type-caption)] tabular-nums text-[var(--color-slate-600)]">{scoreLabel(item.risk_score)}</span>
                          </td>
                          <td className="px-3 py-3.5 text-[var(--color-blue)]">{item.channel || "—"}</td>
                          <td className="px-3 py-3.5 text-[var(--color-blue)]">{item.status}</td>
                          <td className="px-3 py-3.5 text-xs text-[var(--color-blue)]">{formatDate(item.created_at)}</td>
                          <td className="max-w-[240px] truncate px-3 py-3.5 text-xs text-[var(--color-blue)]">
                            {item.decision_reason || item.skip_reason || item.error || "—"}
                          </td>
                          <td className="px-3 py-3.5">
                            <button
                              type="button"
                              onClick={() => startCreateFromLog(item)}
                              className="inline-flex h-8 items-center rounded-lg border border-[var(--color-blue-tint-border)] bg-[var(--color-blue-tint)] px-2.5 text-xs font-semibold text-[var(--color-blue)] hover:bg-[var(--color-blue-tint)]"
                            >
                              Criar atividade
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>
          </div>
        </details>
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
    neutral: "bg-[var(--color-blue-tint)] text-[var(--color-blue)]",
    warning: "bg-[var(--color-peach-tint)] text-[var(--color-peach-tint-border)]",
    danger: "bg-[var(--color-red-tint)] text-[var(--color-red)]",
    critical: "bg-[var(--color-red-tint)] text-[var(--color-red)]",
  };
  return (
    <article className="rounded-2xl border border-[var(--color-border)] bg-white p-4 shadow-sm sm:p-5">
      <div className="flex items-center gap-3">
        <span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl", tones[tone])}>{icon}</span>
        <p className="text-sm font-medium text-[var(--color-blue)]">{label}</p>
      </div>
      <p className="mt-4 text-3xl font-semibold tracking-tight tabular-nums text-[var(--color-ink)]">{value}</p>
      <p className="mt-1 text-xs leading-relaxed text-[var(--color-slate-600)]">{description}</p>
    </article>
  );
}
