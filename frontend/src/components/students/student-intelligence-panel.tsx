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
} from "@/components/ui/icons";
import type { LucideIcon } from "@/components/ui/icons";
import { RiskBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { signalsApi } from "@/lib/api-signals";
import { cn, formatScore } from "@/lib/utils";
import type { RiskHistoryAssessment } from "@/types/api";
import type { StudentSignalEvaluation } from "@/types/signals";

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

function comparableDelta(
  current: RiskHistoryAssessment,
  previous: RiskHistoryAssessment | undefined
): { delta: number | null; label: string } {
  if (!previous) return { delta: null, label: "Sem histórico comparável" };
  const sameSemantics =
    current.score_semantics_version === previous.score_semantics_version &&
    current.model_scope === previous.model_scope &&
    (current.model_version || "") === (previous.model_version || "");
  if (!sameSemantics) return { delta: null, label: "Mudança de modelo" };
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
        stroke="var(--color-blue)"
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
    queryFn: () => signalsApi.evaluate(studentId),
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
  const newestFirst = useMemo(() => [...assessments].reverse(), [assessments]);

  const activeSignals = useMemo(() => {
    const signals = signalsQuery.data?.signals || [];
    return signals.filter((s) => s.active === true || s.status === "TRUE");
  }, [signalsQuery.data]);

  const indeterminateSignals = useMemo(() => {
    const signals = signalsQuery.data?.signals || [];
    return signals.filter(
      (s) => s.insufficient_data === true || s.status === "INDETERMINATE"
    );
  }, [signalsQuery.data]);

  const membershipGroups = useMemo(() => {
    const groups = catalogQuery.data?.groups || [];
    const activeIds = new Set(
      (signalsQuery.data?.active_signal_ids || activeSignals.map((s) => s.signal_id)).filter(
        Boolean
      )
    );
    return groups.filter((g) => {
      if (g.id === "multiple_active_signals") {
        const operational = [
          "risk_critical",
          "risk_medium",
          "financial_delay",
          "days_without_login_elevated",
          "risk_increase",
        ];
        return operational.filter((id) => activeIds.has(id)).length >= 2;
      }
      const mapped = SIGNAL_TO_GROUP[g.id];
      return mapped ? activeIds.has(mapped) : false;
    });
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
      <section className="rounded-xl border border-[var(--color-border)] bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-[var(--color-blue)]" />
              <h2 className="text-[length:var(--type-body-comfort)] font-semibold text-[var(--color-ink)]">Histórico de risco</h2>
            </div>
            <p className="mt-1 text-xs text-[var(--color-slate-600)]">
              Evolução das avaliações persistidas. Delta só é calculado entre avaliações com a
              mesma semântica e versão de modelo.
            </p>
          </div>
          {chronologicalScores.length >= 2 ? <Sparkline scores={chronologicalScores} /> : null}
        </div>

        {historyQuery.isLoading ? (
          <div className="mt-4 space-y-2">
            <Skeleton className="h-12 w-full rounded-lg" />
            <Skeleton className="h-12 w-full rounded-lg" />
          </div>
        ) : null}

        {historyQuery.isError ? (
          <div className="mt-4 rounded-lg border border-[var(--color-red-tint-border)] bg-[var(--color-red-tint)] px-3 py-3 text-[length:var(--type-body-compact)] text-[var(--color-red)]">
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
          <p className="mt-4 rounded-lg bg-[var(--color-panel)] px-3 py-3 text-[length:var(--type-body-compact)] text-[var(--color-slate-600)]">
            Ainda não há avaliações históricas para este aluno.
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
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--color-border)] px-3.5 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold tabular-nums text-[var(--color-ink)]">
                        {formatScore(item.score)}
                      </span>
                      <RiskBadge level={item.risk_level} />
                      <span className="text-[length:var(--type-caption)] text-[var(--color-muted)]">
                        {formatDateTime(item.evaluated_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-slate-600)]">
                      Modelo {item.model_version || "—"} · semântica {item.score_semantics_version}
                      {item.score_basis === "legacy_adjusted" ? " · legado" : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs font-medium">
                    {delta != null && delta > 0 ? (
                      <TrendingUp className="h-3.5 w-3.5 text-[var(--color-red)]" />
                    ) : null}
                    {delta != null && delta < 0 ? (
                      <TrendingDown className="h-3.5 w-3.5 text-[var(--color-green)]" />
                    ) : null}
                    <span
                      className={cn(
                        delta != null && delta > 0 && "text-[var(--color-red)]",
                        delta != null && delta < 0 && "text-[var(--color-green)]",
                        (delta === null || delta === 0) && "text-[var(--color-slate-600)]"
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
          <p className="mt-3 text-[length:var(--type-caption)] leading-relaxed text-[var(--color-muted)]">
            {historyQuery.data.explanation_note}
          </p>
        ) : null}
      </section>

      <section className="rounded-xl border border-[var(--color-border)] bg-white p-5">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[var(--color-blue)]" />
          <h2 className="text-[length:var(--type-body-comfort)] font-semibold text-[var(--color-ink)]">Sinais ativos</h2>
        </div>
        <p className="mt-1 text-xs text-[var(--color-slate-600)]">
          Avaliação sob demanda. Ausência de score não significa baixo risco.
        </p>

        {signalsQuery.isLoading ? (
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <Skeleton className="h-16 rounded-lg" />
            <Skeleton className="h-16 rounded-lg" />
          </div>
        ) : null}

        {signalsQuery.isError ? (
          <div className="mt-4 rounded-lg border border-[var(--color-red-tint-border)] bg-[var(--color-red-tint)] px-3 py-3 text-[length:var(--type-body-compact)] text-[var(--color-red)]">
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
          <p className="mt-4 rounded-lg bg-[var(--color-panel)] px-3 py-3 text-[length:var(--type-body-compact)] text-[var(--color-slate-600)]">
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
            <p className="mb-2 text-[length:var(--type-caption)] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">
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
          <p className="mt-3 text-[length:var(--type-caption)] text-[var(--color-muted)]">
            Avaliado em {formatDateTime(signalsQuery.data.evaluated_at)}
          </p>
        ) : null}
      </section>

      <section className="rounded-xl border border-[var(--color-border)] bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-[var(--color-blue)]" />
              <h2 className="text-[length:var(--type-body-comfort)] font-semibold text-[var(--color-ink)]">Grupos do estudante</h2>
            </div>
            <p className="mt-1 text-xs text-[var(--color-slate-600)]">
              Pertencimento derivado dos sinais definitivamente ativos.
            </p>
          </div>
          <Link
            href="/alunos/grupos"
            className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--color-blue)] hover:underline"
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
          <p className="mt-4 rounded-lg bg-[var(--color-panel)] px-3 py-3 text-[length:var(--type-body-compact)] text-[var(--color-slate-600)]">
            Este aluno não pertence a nenhum grupo com sinal definitivamente ativo.
          </p>
        ) : null}

        {membershipGroups.length > 0 ? (
          <ul className="mt-4 flex flex-wrap gap-2">
            {membershipGroups.map((group) => (
              <li key={group.id}>
                <Link
                  href={`/alunos/grupos/${encodeURIComponent(group.id)}`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-source-bfdbfe)] bg-[var(--color-source-eff6ff)] px-3 py-1.5 text-xs font-semibold text-[var(--color-blue)] transition hover:bg-[var(--color-source-dbeafe)]"
                >
                  {group.name}
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="rounded-xl border border-[var(--color-source-bfdbfe)] bg-[var(--color-panel)] p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <MessageSquareText className="h-4 w-4 text-[var(--color-blue)]" />
              <h2 className="text-[length:var(--type-body-comfort)] font-semibold text-[var(--color-ink)]">Próxima ação</h2>
            </div>
            <p className="mt-1 max-w-xl text-xs leading-relaxed text-[var(--color-slate-600)]">
              Enfileire uma intervenção simulada (dry-run) para este aluno ou abra a área de
              retenção.
            </p>
            {optOut ? (
              <p className="mt-2 text-xs font-medium text-[var(--color-source-b54708)]">
                Comunicação desabilitada por preferência do aluno.
              </p>
            ) : null}
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Link
              href="/retencao"
              className="inline-flex h-10 items-center rounded-lg border border-[var(--color-border)] bg-white px-3.5 text-[length:var(--type-body-compact)] font-medium text-[var(--color-slate-600)] transition hover:bg-white"
            >
              Ir para retenção
            </Link>
            <button
              type="button"
              disabled={enqueueing || Boolean(optOut)}
              onClick={handleEnqueue}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[var(--color-blue)] px-4 text-[length:var(--type-body-compact)] font-semibold text-white transition hover:bg-[var(--color-blue)] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]"
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
  const name = signal.name || SIGNAL_LABELS[signal.signal_id] || signal.signal_id;
  const groupId = SIGNAL_TO_GROUP[signal.signal_id];

  return (
    <li
      className={cn(
        "rounded-lg border px-3.5 py-3",
        tone === "active" ? "border-[var(--color-source-fedf89)] bg-[var(--color-source-fffaeb)]" : "border-[var(--color-border)] bg-[var(--color-panel)]"
      )}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={cn(
            "grid h-8 w-8 shrink-0 place-items-center rounded-lg",
            tone === "active" ? "bg-white text-[var(--color-source-b54708)]" : "bg-white text-[var(--color-slate-600)]"
          )}
        >
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[length:var(--type-body-compact)] font-semibold text-[var(--color-ink)]">{name}</p>
          {signal.limitations?.[0] ? (
            <p className="mt-0.5 text-[length:var(--type-caption)] leading-relaxed text-[var(--color-slate-600)]">
              {signal.limitations[0]}
            </p>
          ) : null}
          {groupId ? (
            <Link
              href={`/alunos/grupos/${encodeURIComponent(groupId)}`}
              className="mt-1.5 inline-flex items-center gap-1 text-[length:var(--type-caption)] font-semibold text-[var(--color-blue)] hover:underline"
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
