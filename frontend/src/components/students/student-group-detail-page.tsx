"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CircleAlert,
  CircleHelp,
  Info,
  RefreshCw,
  RotateCcw,
  Users,
} from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { GroupRetentionCta } from "@/components/students/group-retention-cta";
import { StudentDrawer } from "@/components/students/student-drawer";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import {
  cursorErrorKind,
  hasCursorContinuation,
  signalStatusPresentation,
} from "@/lib/student-groups.mjs";
import type {
  StudentGroupSignalEvaluation,
  StudentGroupState,
} from "@/types/api";

function formatDateTime(value?: string | null) {
  if (!value) return "Data não disponível";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data não disponível";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function humanizeKey(value: string) {
  const text = value.replaceAll("_", " ");
  return text.charAt(0).toLocaleUpperCase("pt-BR") + text.slice(1);
}

function formatEvidenceValue(value: unknown): string {
  if (value == null) return "Não informado";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) {
    return value.map((item) => formatEvidenceValue(item)).join(", ");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => humanizeKey(key) + ": " + formatEvidenceValue(item))
      .join(" · ");
  }
  return "Não informado";
}

function MetricCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <article className="rounded-xl border border-[var(--color-legacy-e5e7eb)] bg-white p-4">
      <p className="text-[length:var(--type-overline)] font-semibold uppercase tracking-[0.08em] text-[var(--color-legacy-98a2b3)]">
        {label}
      </p>
      <p className="mt-2 text-[length:var(--type-size-25)] font-semibold tracking-[-0.04em] tabular-nums text-[var(--color-legacy-111827)]">
        {typeof value === "number" ? value.toLocaleString("pt-BR") : value}
      </p>
      {hint ? <p className="mt-1 text-[length:var(--type-caption)] leading-relaxed text-[var(--color-legacy-667085)]">{hint}</p> : null}
    </article>
  );
}

function SignalStatus({ status }: { status: StudentGroupState }) {
  const presentation = signalStatusPresentation(status);
  const toneClass =
    presentation.tone === "success"
      ? "border-[var(--color-source-abefc6)] bg-[var(--color-source-ecfdf3)] text-[var(--color-legacy-067647)]"
      : presentation.tone === "warning"
        ? "border-[var(--color-source-fedf89)] bg-[var(--color-source-fffaeb)] text-[var(--color-source-b54708)]"
        : "border-[var(--color-legacy-e5e7eb)] bg-[var(--color-legacy-f8fafc)] text-[var(--color-legacy-667085)]";

  return (
    <span
      className={
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[length:var(--type-overline)] font-semibold " +
        toneClass
      }
      title={presentation.explanation}
    >
      {presentation.label}
    </span>
  );
}

function ErrorPanel({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry: () => void;
}) {
  return (
    <div role="alert" className="rounded-xl border border-[var(--color-legacy-fecdca)] bg-[var(--color-red-tint)] p-5">
      <div className="flex items-start gap-2.5">
        <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-legacy-b42318)]" />
        <div>
          <p className="text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-b42318)]">{title}</p>
          <p className="mt-1 text-xs leading-relaxed text-[var(--color-legacy-667085)]">{message}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 text-xs font-semibold text-[var(--color-legacy-b42318)] underline underline-offset-4"
          >
            Tentar novamente
          </button>
        </div>
      </div>
    </div>
  );
}

export function StudentGroupDetailPage() {
  const params = useParams<{ groupId: string }>();
  const groupId = params.groupId;
  const queryClient = useQueryClient();
  const [paginationRun, setPaginationRun] = useState(0);
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);

  const detail = useQuery({
    queryKey: ["student-groups", "detail", groupId],
    queryFn: () => api.studentGroupDetail(groupId),
    enabled: Boolean(groupId),
    retry: false,
  });

  const members = useInfiniteQuery({
    queryKey: ["student-groups", "members", groupId, paginationRun],
    queryFn: ({ pageParam }) =>
      api.studentGroupMembers(groupId, pageParam ? { cursor: pageParam } : undefined),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      hasCursorContinuation(lastPage) ? lastPage.next_cursor! : undefined,
    enabled: Boolean(groupId),
    retry: (failureCount, error) => {
      const status = error instanceof ApiError ? error.status : 0;
      if ([400, 401, 403, 404, 410, 422].includes(status)) return false;
      return failureCount < 1;
    },
  });

  const pages = members.data?.pages || [];
  const latestPage = pages.length > 0 ? pages[pages.length - 1] : undefined;
  const listedMembers = pages.flatMap((page) => page.members);
  const cursorIssue = members.isFetchNextPageError
    ? cursorErrorKind(members.error instanceof ApiError ? members.error.status : 0)
    : null;
  const canContinue = latestPage ? hasCursorContinuation(latestPage) : false;
  const signalNames = new Map(
    (detail.data?.signals_used || []).map((signal) => [signal.id, signal.name])
  );

  function restartMembersQuery() {
    queryClient.removeQueries({ queryKey: ["student-groups", "members", groupId] });
    setPaginationRun((current) => current + 1);
  }

  return (
    <>
      <Header title="Grupos de alunos" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link
            href="/alunos/grupos"
            className="inline-flex items-center gap-2 text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-667085)] transition hover:text-[var(--color-legacy-2563eb)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-legacy-2563eb)]"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar para grupos
          </Link>
          {detail.data ? (
            <button
              type="button"
              onClick={() => void detail.refetch()}
              disabled={detail.isFetching}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--color-legacy-e5e7eb)] bg-white px-3 text-xs font-medium text-[var(--color-legacy-111827)] transition hover:bg-[var(--color-legacy-f8fafc)] disabled:opacity-60"
            >
              <RefreshCw className={"h-3.5 w-3.5" + (detail.isFetching ? " animate-spin" : "")} />
              Atualizar avaliação
            </button>
          ) : null}
        </div>

        {detail.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-40 rounded-xl" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-24 rounded-xl" />
              ))}
            </div>
            <Skeleton className="h-64 rounded-xl" />
          </div>
        ) : null}

        {detail.isError && !detail.data ? (
          <ErrorPanel
            title="Não foi possível carregar este grupo."
            message={
              detail.error instanceof ApiError && detail.error.status === 404
                ? "O grupo solicitado não existe no catálogo atual."
                : detail.error instanceof Error
                  ? detail.error.message
                  : "Verifique sua sessão e tente novamente."
            }
            onRetry={() => void detail.refetch()}
          />
        ) : null}

        {detail.data ? (
          <>
            <section className="rounded-xl border border-[var(--color-legacy-e5e7eb)] bg-white p-5 sm:p-6">
              <p className="text-[length:var(--type-overline)] font-semibold uppercase tracking-[0.08em] text-[var(--color-legacy-2563eb)]">
                Grupo virtual · Catálogo {detail.data.catalog_version}
              </p>
              <h1 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-[var(--color-legacy-111827)]">
                {detail.data.name}
              </h1>
              <p className="mt-1.5 max-w-3xl text-[length:var(--type-body-compact)] leading-relaxed text-[var(--color-legacy-667085)]">
                {detail.data.description}
              </p>
              <p className="mt-4 text-[length:var(--type-caption)] text-[var(--color-legacy-98a2b3)]">
                Avaliação dos detalhes: {formatDateTime(detail.data.evaluated_at)}
              </p>
            </section>

            <GroupRetentionCta
              groupId={groupId}
              groupName={detail.data.name}
              memberCount={detail.data.metrics.total_belonging}
            />

            <section aria-label="Métricas do grupo" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Alunos no grupo"
                value={detail.data.metrics.total_belonging}
                hint="Resultado TRUE retornado pelo avaliador"
              />
              <MetricCard
                label="Não pertencem"
                value={detail.data.metrics.total_not_belonging}
                hint="Resultado FALSE"
              />
              <MetricCard
                label="Dados insuficientes"
                value={detail.data.metrics.total_indeterminate}
                hint="Resultado INDETERMINATE"
              />
              <MetricCard
                label="Alunos avaliados"
                value={detail.data.metrics.total_evaluated}
                hint={"De " + detail.data.metrics.total_eligible.toLocaleString("pt-BR") + " elegíveis"}
              />
            </section>

            {detail.data.truncated ? (
              <div className="flex items-start gap-2.5 rounded-xl border border-[var(--color-source-fedf89)] bg-[var(--color-source-fffaeb)] p-4">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-source-b54708)]" />
                <p className="text-xs leading-relaxed text-[var(--color-source-b54708)]">
                  A avaliação do grupo foi truncada. As métricas representam apenas os alunos
                  avaliados nesta resposta.
                </p>
              </div>
            ) : null}

            <section className="rounded-xl border border-[var(--color-legacy-e5e7eb)] bg-white p-5">
              <h2 className="text-[length:var(--type-body-comfort)] font-semibold text-[var(--color-legacy-111827)]">Sinais utilizados</h2>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {detail.data.signals_used.map((signal) => (
                  <article key={signal.id} className="rounded-lg border border-[var(--color-legacy-e5e7eb)] p-4">
                    <h3 className="text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-111827)]">{signal.name}</h3>
                    <p className="mt-2 text-xs leading-relaxed text-[var(--color-legacy-667085)]">
                      {signal.description}
                    </p>
                    <p className="mt-2 break-words font-mono text-[length:var(--type-caption)] text-[var(--color-legacy-344054)]">
                      {signal.activation_rule}
                    </p>
                  </article>
                ))}
              </div>
            </section>

            {detail.data.limitations.length > 0 ? (
              <section className="rounded-xl border border-[var(--color-legacy-e5e7eb)] bg-white p-5">
                <div className="flex items-start gap-2.5">
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-legacy-667085)]" />
                  <div>
                    <h2 className="text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-111827)]">Limitações</h2>
                    <ul className="mt-2 space-y-1.5">
                      {detail.data.limitations.map((limitation, index) => (
                        <li key={index} className="text-xs leading-relaxed text-[var(--color-legacy-667085)]">
                          {limitation}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </section>
            ) : null}

            <section className="space-y-4">
              <div className="flex flex-col gap-2 border-b border-[var(--color-legacy-e5e7eb)] pb-3 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h2 className="text-[length:var(--type-heading-compact)] font-semibold tracking-[-0.02em] text-[var(--color-legacy-111827)]">
                    Alunos integrantes
                  </h2>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--color-legacy-667085)]">
                    Somente alunos com resultado TRUE para este grupo.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={restartMembersQuery}
                  className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--color-legacy-e5e7eb)] bg-white px-3 text-xs font-medium text-[var(--color-legacy-111827)]"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Reiniciar lista
                </button>
              </div>

              {members.isLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-16 rounded-xl" />
                  ))}
                </div>
              ) : null}

              {members.isError && listedMembers.length === 0 ? (
                <ErrorPanel
                  title="Não foi possível carregar os integrantes."
                  message={
                    members.error instanceof Error
                      ? members.error.message
                      : "Tente novamente em instantes."
                  }
                  onRetry={() => void members.refetch()}
                />
              ) : null}

              {!members.isLoading && listedMembers.length === 0 && !members.isError ? (
                <div className="rounded-xl border border-dashed border-[var(--color-legacy-d0d5dd)] bg-white px-5 py-10 text-center">
                  <Users className="mx-auto h-7 w-7 text-[var(--color-legacy-98a2b3)]" />
                  <p className="mt-3 text-sm font-semibold text-[var(--color-legacy-111827)]">Nenhum integrante TRUE</p>
                </div>
              ) : null}

              {listedMembers.length > 0 ? (
                <ul className="divide-y divide-[var(--color-legacy-f2f4f7)] overflow-hidden rounded-xl border border-[var(--color-legacy-e5e7eb)] bg-white">
                  {listedMembers.map((member) => (
                    <li key={member.student_id}>
                      <button
                        type="button"
                        onClick={() => setSelectedStudentId(member.student_id)}
                        className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left hover:bg-[var(--color-legacy-f8fafc)]"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-[var(--color-legacy-111827)]">
                            {member.name || member.student_id}
                          </p>
                          <p className="mt-0.5 text-[length:var(--type-caption)] text-[var(--color-legacy-98a2b3)]">{member.student_id}</p>
                        </div>
                        <Link
                          href={"/alunos/" + encodeURIComponent(member.student_id)}
                          className="shrink-0 text-xs font-semibold text-[var(--color-legacy-2563eb)] hover:underline"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Ficha
                        </Link>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}

              {canContinue ? (
                <button
                  type="button"
                  disabled={members.isFetchingNextPage}
                  onClick={() => void members.fetchNextPage()}
                  className="inline-flex h-10 w-full items-center justify-center rounded-lg border border-[var(--color-legacy-e5e7eb)] bg-white text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-344054)] disabled:opacity-60"
                >
                  {members.isFetchingNextPage ? "Carregando…" : "Carregar mais integrantes"}
                </button>
              ) : null}

              {cursorIssue ? (
                <p className="text-xs text-[var(--color-source-b54708)]">
                  Continuação da lista interrompida ({cursorIssue}). Reinicie a lista se necessário.
                </p>
              ) : null}
            </section>
          </>
        ) : null}
      </main>

      <StudentDrawer
        studentId={selectedStudentId}
        onClose={() => setSelectedStudentId(null)}
      />
    </>
  );
}
