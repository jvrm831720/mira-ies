"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CircleHelp,
  History,
  Layers,
  MessageSquareText,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { RiskBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn, formatScore } from "@/lib/utils";
import type { RiskHistoryAssessment, StudentSignalEvaluation } from "@/types/api";

const SIGNAL_ICONS: Record<string, LucideIcon> = {
  risk_critical: AlertTriangle,
  risk_medium: Activity,
  missing_score: CircleHelp,
  financial_delay: Wallet,
  days_without_login_elevated: Activity,
  risk_increase: TrendingUp,
};

const SIGNAL_LABELS: Record<string, string> = {
  risk_critical: "Risco crítico",
  risk_medium: "Risco médio",
  missing_score: "Ausência de score",
  financial_delay: "Atraso financeiro",
  days_without_login_elevated: "Dias sem login elevados",
  risk_increase: "Aumento relevante de risco",
};

/** Grupos 1:1 com sinal operacional (exceto multiple_active_signals). */
const SIGNAL_TO_GROUP: Record<string, string> = {
  risk_critical: "risk_critical",
  risk_medium: "risk_medium",
  missing_score: "missing_score",
  financial_delay: "financial_delay",
  days_without_login_elevated: "days_without_login_elevated",
  risk_increase: "risk_increase",
};

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function comparableDelta(
  current: RiskHistoryAssessment,
  previous: RiskHistoryAssessment | undefined
): { delta: number | null; label: string } {
  if (!previous) {
    return { delta: null, label: "Sem histórico comparável" };
  }
  const sameSemantics =
    current.score_semantics_version === previous.score_semantics_version &&
    current.model_scope === previous.model_scope &&
    (current.model_version || "") === (previous.model_version || "");
  if (!sameSemantics) {
    return { delta: null, label: "Mudança de modelo" };
  }
  const delta = current.score - previous.score;
  if (delta === 0) return { delta: 0, label: "Sem mudança relevante" };
  if (delta > 0) return { delta, label: `+${delta.toLocaleString("pt-BR")} pts` };
  return { delta, label: `${delta.toLocaleString("pt-BR")} pts` };
}

function Sparkline({ scores }: { scores: number[] }) {
  if (scores.length < 2) return null;
  const w = 160;
  const h = 36;
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const range = max - min || 1;
  const points = scores
    .map((s, i) => {
      const x = (i / (scores.length - 1)) * w;
      const y = h - ((s - min) / range) * (h - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible" aria-hidden>
      <polyline
        fill="none"
        stroke="#2563EB"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        points={points}
      />
    </svg>
  );
}

export function StudentIntelligencePanel({
  studentId,
  optOut,
}: {
  studentId: string;
  optOut?: boolean;
}) {
  const [enqueueing, setEnqueueing] = useState(false);

  const historyQuery = useQuery({
    queryKey: ["student-risk-history", studentId],
    queryFn: () => api.studentRiskHistory(studentId, { page: 1, page_size: 12 }),
    enabled: Boolean(studentId),
    retry: false,
  });

  const signalsQuery = useQuery({
    queryKey: ["student-signals", studentId],
    queryFn: () => api.signalsEvaluate(studentId),
    enabled: Boolean(studentId),
    retry: false,
  });

  const catalogQuery = useQuery({
    queryKey: ["student-groups", "catalog"],
    queryFn: () => api.studentGroupsCatalog(),
    staleTime: 60_000,
    retry: false,
  });

  const assessments = useMemo(() => {
    const list = [...(historyQuery.data?.assessments || [])];
    list.sort(
      (a, b) => new Date(a.evaluated_at).getTime() - new Date(b.evaluated_at).getTime()
    );
    return list;
  }, [historyQuery.data?.assessments]);

  const chronologicalScores = assessments.map((a) => a.score);
  const newestFirst = useMemo(
    () => [...assessments].reverse(),
    [assessments]
  );

  const activeSignals = useMemo(() => {
    const signals = signalsQuery.data?.signals || [];
    return signals.filter((s) => s.active === true || s.status === "TRUE");
  }, [signalsQuery.data]);

  const indeterminateSignals = useMemo(() => {
    const signals = signalsQuery.data?.signals || [];
    return signals.filter(
      (s) =>
        s.insufficient_data === true ||
        s.status === "INDETERMINATE" ||
        (s.active !== true && s.status !== "FALSE" && s.status !== "TRUE" && s.insufficient_data)
    );
  }, [signalsQuery.data]);

  const membershipGroups = useMemo(() => {
    const groups = catalogQuery.data?.groups || [];
    const activeIds = new Set(
      (signalsQuery.data?.active_signal_ids || activeSignals.map((s) => s.signal_id)).filter(
        Boolean
      )
    );
    const fromSignals = groups.filter((g) => {
      if (g.id === "multiple_active_signals") {
        const operational = [
          "risk_critical",
          "risk_medium",
          "financial_delay",
          "days_without_login_elevated",
          "risk_increase",
        ];
        const count = operational.filter((id) => activeIds.has(id)).length;
        return count >= 2;
      }
      const mapped = SIGNAL_TO_GROUP[g.id];
      if (mapped) return activeIds.has(mapped);
      return false;
    });
    return fromSignals;
  }, [catalogQuery.data?.groups, signalsQuery.data, activeSignals]);

  const enqueueMutation = useMutation({
    mutationFn: async () => {
      const key =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `ficha-${studentId}-${Date.now()}`;
      return api.enqueueRetention(
        {
          dry_run: true,
          student_ids: [studentId],
          limit: 1,
          campaign_name: "Intervenção a partir da ficha",
        },
        key
      );
    },
    onSuccess: () => {
      toast.success("Intervenção enfileirada em modo simulado (dry-run).");
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Falha ao enfileirar intervenção.");
    },
    onSettled: () => setEnqueueing(false),
  });

  function handleEnqueue() {
    if (optOut) {
      toast.error("Este aluno está com opt-out de comunicação.");
      return;
    }
    setEnqueueing(true);
    enqueueMutation.mutate();
  }

  return (
    <div className="space-y-4">
      {/* Histórico de risco */}
      <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-[#2563EB]" />
              <h2 className="text-[15px] font-semibold text-[#111827]">Histórico de risco</h2>
            </div>
            <p className="mt-1 text-[12px] text-[#667085]">
              Evolução das avaliações persistidas. Delta só é calculado entre avaliações com a
              mesma semântica e versão de modelo.
            </p>
          </div>
          {chronologicalScores.length >= 2 ? (
            <Sparkline scores={chronologicalScores} />
          ) : null}
        </div>

        {historyQuery.isLoading ? (
          <div className="mt-4 space-y-2">
            <Skeleton className="h-12 w-full rounded-lg" />
            <Skeleton className="h-12 w-full rounded-lg" />
          </div>
        ) : null}

        {historyQuery.isError ? (
          <div className="mt-4 rounded-lg border border-[#FECDCA] bg-[#FEF3F2] px-3 py-3 text-[13px] text-[#B42318]">
            Não foi possível carregar o histórico de avaliações.
            <button
              type="button"
              onClick={() => void historyQuery.refetch()}
              className="ml-2 font-semibold underline underline-offset-2"
            >
              Tentar novamente
            </button>
          </div>
        ) : null}

        {!historyQuery.isLoading && !historyQuery.isError && newestFirst.length === 0 ? (
          <p className="mt-4 rounded-lg bg-[#F8FAFC] px-3 py-3 text-[13px] text-[#667085]">
            Ainda não há avaliações históricas para este aluno. O score atual, quando existir, não
            entra automaticamente como trajetória até ser persistido em uma execução de scoring.
          </p>
        ) : null}

        {newestFirst.length > 0 ? (
          <ul className="mt-4 space-y-2">
            {newestFirst.map((item, index) => {
              const previous = newestFirst[index + 1];
              const { delta, label } = comparableDelta(item, previous);
              return (
                <li
                  key={item.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#E5E7EB] px-3.5 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[14px] font-semibold tabular-nums text-[#111827]">
                        {formatScore(item.score)}
                      </span>
                      <RiskBadge level={item.risk_level} />
                      <span className="text-[11px] text-[#98A2B3]">
                        {formatDateTime(item.evaluated_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-[#667085]">
                      Modelo {item.model_version || "—"} · semântica{" "}
                      {item.score_semantics_version}
                      {item.score_basis === "legacy_adjusted" ? " · legado" : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 text-[12px] font-medium">
                    {delta != null && delta > 0 ? (
                      <TrendingUp className="h-3.5 w-3.5 text-[#F04438]" />
                    ) : null}
                    {delta != null && delta < 0 ? (
                      <TrendingDown className="h-3.5 w-3.5 text-[#12B76A]" />
                    ) : null}
                    <span
                      className={cn(
                        delta != null && delta > 0 && "text-[#F04438]",
                        delta != null && delta < 0 && "text-[#12B76A]",
                        (delta === null || delta === 0) && "text-[#667085]"
                      )}
                    >
                      {label}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}

        {historyQuery.data?.explanation_note ? (
          <p className="mt-3 text-[11px] leading-relaxed text-[#98A2B3]">
            {historyQuery.data.explanation_note}
          </p>
        ) : null}
      </section>

      {/* Sinais ativos */}
      <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[#2563EB]" />
          <h2 className="text-[15px] font-semibold text-[#111827]">Sinais ativos</h2>
        </div>
        <p className="mt-1 text-[12px] text-[#667085]">
          Avaliação sob demanda a partir dos dados atuais e do histórico comparável. Ausência de
          score não significa baixo risco.
        </p>

        {signalsQuery.isLoading ? (
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <Skeleton className="h-16 rounded-lg" />
            <Skeleton className="h-16 rounded-lg" />
          </div>
        ) : null}

        {signalsQuery.isError ? (
          <div className="mt-4 rounded-lg border border-[#FECDCA] bg-[#FEF3F2] px-3 py-3 text-[13px] text-[#B42318]">
            Não foi possível avaliar os sinais.
            <button
              type="button"
              onClick={() => void signalsQuery.refetch()}
              className="ml-2 font-semibold underline underline-offset-2"
            >
              Tentar novamente
            </button>
          </div>
        ) : null}

        {!signalsQuery.isLoading &&
        !signalsQuery.isError &&
        activeSignals.length === 0 &&
        indeterminateSignals.length === 0 ? (
          <p className="mt-4 rounded-lg bg-[#F8FAFC] px-3 py-3 text-[13px] text-[#667085]">
            Nenhum sinal operacional ativo neste momento.
          </p>
        ) : null}

        {activeSignals.length > 0 ? (
          <ul className="mt-4 grid gap-2 sm:grid-cols-2">
            {activeSignals.map((signal) => (
              <SignalCard key={signal.signal_id} signal={signal} tone="active" />
            ))}
          </ul>
        ) : null}

        {indeterminateSignals.length > 0 ? (
          <div className="mt-4">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
              Dados insuficientes
            </p>
            <ul className="grid gap-2 sm:grid-cols-2">
              {indeterminateSignals.map((signal) => (
                <SignalCard key={signal.signal_id} signal={signal} tone="indeterminate" />
              ))}
            </ul>
          </div>
        ) : null}

        {signalsQuery.data?.evaluated_at ? (
          <p className="mt-3 text-[11px] text-[#98A2B3]">
            Avaliado em {formatDateTime(signalsQuery.data.evaluated_at)}
          </p>
        ) : null}
      </section>

      {/* Grupos */}
      <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-[#2563EB]" />
              <h2 className="text-[15px] font-semibold text-[#111827]">Grupos do estudante</h2>
            </div>
            <p className="mt-1 text-[12px] text-[#667085]">
              Pertencimento derivado dos sinais definitivamente ativos e do catálogo de grupos.
            </p>
          </div>
          <Link
            href="/alunos/grupos"
            className="inline-flex items-center gap-1 text-[12px] font-semibold text-[#2563EB] hover:underline"
          >
            Ver todos os grupos
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        {catalogQuery.isLoading || signalsQuery.isLoading ? (
          <Skeleton className="mt-4 h-12 w-full rounded-lg" />
        ) : null}

        {!catalogQuery.isLoading &&
        !signalsQuery.isLoading &&
        membershipGroups.length === 0 ? (
          <p className="mt-4 rounded-lg bg-[#F8FAFC] px-3 py-3 text-[13px] text-[#667085]">
            Este aluno não pertence a nenhum grupo com sinal definitivamente ativo.
          </p>
        ) : null}

        {membershipGroups.length > 0 ? (
          <ul className="mt-4 flex flex-wrap gap-2">
            {membershipGroups.map((group) => (
              <li key={group.id}>
                <Link
                  href={`/alunos/grupos/${encodeURIComponent(group.id)}`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[#BFDBFE] bg-[#EFF6FF] px-3 py-1.5 text-[12px] font-semibold text-[#1D4ED8] transition hover:bg-[#DBEAFE]"
                >
                  {group.name}
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      {/* CTA operacional */}
      <section className="rounded-xl border border-[#BFDBFE] bg-[#F8FAFC] p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <MessageSquareText className="h-4 w-4 text-[#2563EB]" />
              <h2 className="text-[15px] font-semibold text-[#111827]">Próxima ação</h2>
            </div>
            <p className="mt-1 max-w-xl text-[12px] leading-relaxed text-[#667085]">
              Enfileire uma intervenção simulada (dry-run) para este aluno ou abra a área de
              retenção. Opt-out bloqueia o envio real e a simulação orientada a contato.
            </p>
            {optOut ? (
              <p className="mt-2 text-[12px] font-medium text-[#B54708]">
                Comunicação desabilitada por preferência do aluno.
              </p>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Link
              href="/retencao"
              className="inline-flex h-10 items-center rounded-lg border border-[#E5E7EB] bg-white px-3.5 text-[13px] font-medium text-[#344054] transition hover:bg-white"
            >
              Ir para retenção
            </Link>
            <button
              type="button"
              disabled={enqueueing || optOut}
              onClick={handleEnqueue}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#2563EB] px-4 text-[13px] font-semibold text-white transition hover:bg-[#1D4ED8] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            >
              {enqueueing ? "Enfileirando…" : "Enfileirar intervenção (dry-run)"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function SignalCard({
  signal,
  tone,
}: {
  signal: StudentSignalEvaluation;
  tone: "active" | "indeterminate";
}) {
  const Icon = SIGNAL_ICONS[signal.signal_id] || Activity;
  const name =
    signal.name || SIGNAL_LABELS[signal.signal_id] || signal.signal_id;
  const groupId = SIGNAL_TO_GROUP[signal.signal_id];

  return (
    <li
      className={cn(
        "rounded-lg border px-3.5 py-3",
        tone === "active"
          ? "border-[#FEDF89] bg-[#FFFAEB]"
          : "border-[#E5E7EB] bg-[#F8FAFC]"
      )}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={cn(
            "grid h-8 w-8 shrink-0 place-items-center rounded-lg",
            tone === "active" ? "bg-white text-[#B54708]" : "bg-white text-[#667085]"
          )}
        >
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold text-[#111827]">{name}</p>
          {signal.limitations?.[0] ? (
            <p className="mt-0.5 text-[11px] leading-relaxed text-[#667085]">
              {signal.limitations[0]}
            </p>
          ) : null}
          {groupId ? (
            <Link
              href={`/alunos/grupos/${encodeURIComponent(groupId)}`}
              className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-[#2563EB] hover:underline"
            >
              Ver grupo
              <ArrowRight className="h-3 w-3" />
            </Link>
          ) : null}
        </div>
      </div>
    </li>
  );
}
