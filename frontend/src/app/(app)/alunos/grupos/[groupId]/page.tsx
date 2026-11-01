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
} from "lucide-react";
import { Header } from "@/components/layout/header";
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
    <article className="rounded-xl border border-[#E5E7EB] bg-white p-4">
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
        {label}
      </p>
      <p className="mt-2 text-[25px] font-semibold tracking-[-0.04em] tabular-nums text-[#111827]">
        {typeof value === "number" ? value.toLocaleString("pt-BR") : value}
      </p>
      {hint ? <p className="mt-1 text-[11px] leading-relaxed text-[#667085]">{hint}</p> : null}
    </article>
  );
}

function SignalStatus({ status }: { status: StudentGroupState }) {
  const presentation = signalStatusPresentation(status);
  const toneClass =
    presentation.tone === "success"
      ? "border-[#ABEFC6] bg-[#ECFDF3] text-[#067647]"
      : presentation.tone === "warning"
        ? "border-[#FEDF89] bg-[#FFFAEB] text-[#B54708]"
        : "border-[#E5E7EB] bg-[#F8FAFC] text-[#667085]";

  return (
    <span
      className={"inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-semibold " + toneClass}
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
    <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-5">
      <div className="flex items-start gap-2.5">
        <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#B42318]" />
        <div>
          <p className="text-[13px] font-semibold text-[#B42318]">{title}</p>
          <p className="mt-1 text-[12px] leading-relaxed text-[#667085]">{message}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 text-[12px] font-semibold text-[#B42318] underline underline-offset-4"
          >
            Tentar novamente
          </button>
        </div>
      </div>
    </div>
  );
}

function SignalEvidence({
  signal,
  signalName,
}: {
  signal: StudentGroupSignalEvaluation;
  signalName: string;
}) {
  const entries = Object.entries(signal.evidence || {});
  const presentation = signalStatusPresentation(signal.status);
  return (
    <article className="rounded-lg border border-[#E5E7EB] bg-white p-3.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-[12px] font-semibold text-[#111827]">{signalName}</h4>
          <p className="mt-0.5 text-[10px] text-[#98A2B3]">
            Avaliado em {formatDateTime(signal.evaluated_at)}
          </p>
        </div>
        <SignalStatus status={signal.status} />
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-[#667085]">
        {presentation.explanation}
      </p>
      {entries.length > 0 ? (
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          {entries.map(([key, value]) => (
            <div key={key} className="min-w-0 rounded-md bg-[#F8FAFC] px-2.5 py-2">
              <dt className="text-[10px] font-medium text-[#98A2B3]">{humanizeKey(key)}</dt>
              <dd className="mt-0.5 break-words text-[11px] text-[#344054]">
                {formatEvidenceValue(value)}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-3 text-[11px] text-[#98A2B3]">
          A API não retornou evidências adicionais para este sinal.
        </p>
      )}
      {signal.limitations.length > 0 ? (
        <ul className="mt-3 space-y-1 border-t border-[#F2F4F7] pt-2">
          {signal.limitations.map((limitation, index) => (
            <li key={index} className="text-[10px] leading-relaxed text-[#98A2B3]">
              {limitation}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

export default function StudentGroupDetailPage() {
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
      api.studentGroupMembers(
        groupId,
        pageParam ? { cursor: pageParam } : undefined
      ),
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
    queryClient.removeQueries({
      queryKey: ["student-groups", "members", groupId],
    });
    setPaginationRun((current) => current + 1);
  }

  return (
    <>
      <Header title="Grupos de alunos" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link
            href="/alunos/grupos"
            className="inline-flex items-center gap-2 text-[13px] font-semibold text-[#667085] transition hover:text-[#2563EB] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar para grupos
          </Link>
          {detail.data ? (
            <button
              type="button"
              onClick={() => void detail.refetch()}
              disabled={detail.isFetching}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3 text-[12px] font-medium text-[#111827] transition hover:bg-[#F8FAFC] disabled:opacity-60"
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

        {detail.isError && detail.data ? (
          <div
            role="status"
            className="rounded-xl border border-[#FEDF89] bg-[#FFFAEB] p-3 text-[11px] leading-relaxed text-[#B54708]"
          >
            Não foi possível atualizar a avaliação. Os detalhes exibidos são da última
            avaliação carregada em {formatDateTime(detail.data.evaluated_at)}.
          </div>
        ) : null}

        {detail.data ? (
          <>
            <section className="rounded-xl border border-[#E5E7EB] bg-white p-5 sm:p-6">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#2563EB]">
                Grupo virtual · Catálogo {detail.data.catalog_version}
              </p>
              <h1 className="mt-2 text-[24px] font-semibold tracking-[-0.04em] text-[#111827]">
                {detail.data.name}
              </h1>
              <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-[#667085]">
                {detail.data.description}
              </p>
              <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.8fr)]">
                <div className="rounded-lg bg-[#F8FAFC] p-4">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
                    Critério de inclusão
                  </p>
                  <p className="mt-2 text-[13px] leading-relaxed text-[#344054]">
                    {detail.data.inclusion_rule}
                  </p>
                </div>
                <div className="rounded-lg border border-[#E5E7EB] p-4">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
                    Cobertura da avaliação
                  </p>
                  <p className="mt-2 text-[20px] font-semibold tabular-nums text-[#111827]">
                    {detail.data.coverage.percentage == null
                      ? "Não calculável"
                      : detail.data.coverage.percentage.toLocaleString("pt-BR") + "%"}
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-[#667085]">
                    {detail.data.coverage.evaluated.toLocaleString("pt-BR")} de{" "}
                    {detail.data.coverage.eligible.toLocaleString("pt-BR")} alunos elegíveis
                  </p>
                  <p className="mt-1 text-[10px] text-[#98A2B3]">
                    {detail.data.coverage.has_indeterminate
                      ? "Existem avaliações indeterminadas."
                      : "A API não sinalizou avaliações indeterminadas."}
                  </p>
                </div>
              </div>
              <p className="mt-4 text-[11px] text-[#98A2B3]">
                Avaliação dos detalhes: {formatDateTime(detail.data.evaluated_at)}
              </p>
            </section>

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
              <div className="flex items-start gap-2.5 rounded-xl border border-[#FEDF89] bg-[#FFFAEB] p-4">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#B54708]" />
                <p className="text-[12px] leading-relaxed text-[#B54708]">
                  A avaliação do grupo foi truncada. As métricas representam apenas os alunos
                  avaliados nesta resposta.
                </p>
              </div>
            ) : null}

            <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
              <h2 className="text-[15px] font-semibold text-[#111827]">Sinais utilizados</h2>
              <p className="mt-1 text-[12px] text-[#667085]">
                As regras abaixo são as definições retornadas pelo catálogo do backend.
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {detail.data.signals_used.map((signal) => (
                  <article key={signal.id} className="rounded-lg border border-[#E5E7EB] p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-[13px] font-semibold text-[#111827]">{signal.name}</h3>
                      <span className="rounded-full bg-[#F2F4F7] px-2 py-1 text-[10px] font-medium text-[#667085]">
                        {signal.category}
                      </span>
                    </div>
                    <p className="mt-2 text-[12px] leading-relaxed text-[#667085]">
                      {signal.description}
                    </p>
                    <div className="mt-3 space-y-2 border-t border-[#F2F4F7] pt-3">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
                          Regra de ativação
                        </p>
                        <p className="mt-1 break-words font-mono text-[11px] leading-relaxed text-[#344054]">
                          {signal.activation_rule}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
                          Fonte
                        </p>
                        <p className="mt-1 break-words text-[11px] text-[#344054]">
                          {signal.data_source}
                        </p>
                      </div>
                      <p className="text-[10px] text-[#98A2B3]">
                        Confiabilidade: {signal.reliability} · Versão {signal.version}
                      </p>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            {detail.data.limitations.length > 0 ? (
              <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
                <div className="flex items-start gap-2.5">
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-[#667085]" />
                  <div>
                    <h2 className="text-[13px] font-semibold text-[#111827]">
                      Limitações da avaliação
                    </h2>
                    <ul className="mt-2 space-y-1.5">
                      {detail.data.limitations.map((limitation, index) => (
                        <li key={index} className="text-[12px] leading-relaxed text-[#667085]">
                          {limitation}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </section>
            ) : null}

            {detail.data.notes.length > 0 ? (
              <section className="rounded-xl bg-[#F8FAFC] p-4">
                <h2 className="text-[11px] font-semibold text-[#344054]">
                  Observações da API
                </h2>
                <ul className="mt-2 space-y-1">
                  {detail.data.notes.map((note, index) => (
                    <li key={index} className="text-[11px] leading-relaxed text-[#667085]">
                      {note}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section className="space-y-4">
              <div className="flex flex-col gap-2 border-b border-[#E5E7EB] pb-3 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h2 className="text-[17px] font-semibold tracking-[-0.02em] text-[#111827]">
                    Alunos integrantes
                  </h2>
                  <p className="mt-1 text-[12px] leading-relaxed text-[#667085]">
                    A API lista somente alunos cujo resultado para este grupo é TRUE.
                  </p>
                </div>
                {latestPage ? (
                  <p className="text-[10px] text-[#98A2B3]">
                    Página avaliada: {formatDateTime(latestPage.evaluated_at)}
                  </p>
                ) : null}
              </div>

              {members.isLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <Skeleton key={index} className="h-32 rounded-xl" />
                  ))}
                </div>
              ) : null}

              {members.isError && !members.data ? (
                <ErrorPanel
                  title="Não foi possível carregar os integrantes."
                  message={
                    members.error instanceof Error
                      ? members.error.message
                      : "Verifique sua sessão e tente novamente."
                  }
                  onRetry={() => void members.refetch()}
                />
              ) : null}

              {members.isError && members.data && !members.isFetchNextPageError ? (
                <div
                  role="status"
                  className="rounded-xl border border-[#FEDF89] bg-[#FFFAEB] p-3 text-[11px] leading-relaxed text-[#B54708]"
                >
                  Não foi possível atualizar os integrantes. As páginas exibidas são da
                  última consulta carregada em {latestPage ? formatDateTime(latestPage.evaluated_at) : "data não informada"}.
                </div>
              ) : null}

              {members.data ? (
                <>
                  {listedMembers.length === 0 && !canContinue ? (
                    <div className="rounded-xl border border-dashed border-[#D0D5DD] bg-white px-5 py-10 text-center">
                      <Users className="mx-auto h-6 w-6 text-[#98A2B3]" />
                      <p className="mt-3 text-[13px] font-semibold text-[#111827]">
                        Nenhum aluno pertence a este grupo nesta avaliação.
                      </p>
                      <p className="mt-1 text-[11px] text-[#667085]">
                        A API não retornou integrantes com estado TRUE.
                      </p>
                    </div>
                  ) : null}

                  {listedMembers.length === 0 && canContinue ? (
                    <div className="rounded-xl border border-[#FEDF89] bg-[#FFFAEB] p-4 text-[12px] leading-relaxed text-[#B54708]">
                      Nenhum integrante foi encontrado neste trecho avaliado. A API retornou
                      um cursor para continuar a busca.
                    </div>
                  ) : null}

                  <div className="space-y-3">
                    {listedMembers.map((member) => (
                      <article
                        key={member.student_id}
                        className="rounded-xl border border-[#E5E7EB] bg-white p-4 sm:p-5"
                      >
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                          <div className="min-w-0">
                            <h3 className="truncate text-[14px] font-semibold text-[#111827]">
                              {member.name || "Nome não informado pela API"}
                            </h3>
                            <p className="mt-1 break-all text-[10px] text-[#98A2B3]">
                              ID {member.student_id}
                            </p>
                            <p className="mt-1 text-[11px] text-[#667085]">
                              {member.matched_signals.length.toLocaleString("pt-BR")} sinais confirmados
                              {" · "}Associação TRUE
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => setSelectedStudentId(member.student_id)}
                            className="inline-flex h-9 shrink-0 items-center justify-center rounded-lg border border-[#E5E7EB] bg-white px-3 text-[12px] font-semibold text-[#344054] transition hover:bg-[#F8FAFC] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
                          >
                            Abrir ficha do aluno
                          </button>
                        </div>

                        <div className="mt-4 grid gap-2 md:grid-cols-2">
                          {member.signals.map((signal, index) => (
                            <SignalEvidence
                              key={signal.signal_id + "-" + index}
                              signal={signal}
                              signalName={signalNames.get(signal.signal_id) || signal.signal_id}
                            />
                          ))}
                        </div>
                        {member.signals.length === 0 ? (
                          <p className="mt-3 text-[11px] text-[#98A2B3]">
                            A API não retornou sinais adicionais para esta associação.
                          </p>
                        ) : null}
                        {member.limitations.length > 0 ? (
                          <p className="mt-3 text-[10px] leading-relaxed text-[#98A2B3]">
                            {member.limitations.join(" · ")}
                          </p>
                        ) : null}
                      </article>
                    ))}
                  </div>

                  {latestPage?.truncated ? (
                    <div className="flex items-start gap-2.5 rounded-xl border border-[#FEDF89] bg-[#FFFAEB] p-4">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#B54708]" />
                      <div>
                        <p className="text-[12px] font-semibold text-[#B54708]">
                          Busca truncada pelo limite de avaliação
                        </p>
                        <p className="mt-1 text-[11px] leading-relaxed text-[#B54708]">
                          A resposta informa que a varredura desta página atingiu o limite
                          configurado. Continue usando o cursor retornado pela API.
                        </p>
                      </div>
                    </div>
                  ) : null}

                  {members.isFetchNextPageError && cursorIssue ? (
                    <div
                      role="alert"
                      className="rounded-xl border border-[#FEDF89] bg-[#FFFAEB] p-4"
                    >
                      <p className="text-[12px] font-semibold text-[#B54708]">
                        {cursorIssue === "expired" ? "Cursor expirado" : "Cursor inválido"}
                      </p>
                      <p className="mt-1 text-[12px] leading-relaxed text-[#667085]">
                        {cursorIssue === "expired"
                          ? "O backend informou que o cursor expirou. Reinicie a consulta para buscar desde o início."
                          : "O backend rejeitou o cursor para esta consulta. Reinicie a navegação sem alterar o grupo."}
                      </p>
                      <button
                        type="button"
                        onClick={restartMembersQuery}
                        className="mt-3 inline-flex h-9 items-center gap-2 rounded-lg bg-[#B54708] px-3 text-[12px] font-semibold text-white"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        Reiniciar consulta
                      </button>
                    </div>
                  ) : null}

                  {members.isFetchNextPageError && !cursorIssue ? (
                    <div className="flex items-center justify-between gap-3 rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4">
                      <p className="text-[12px] text-[#B42318]">
                        Não foi possível carregar a próxima página.
                      </p>
                      <button
                        type="button"
                        onClick={() => void members.fetchNextPage()}
                        className="text-[12px] font-semibold text-[#B42318] underline underline-offset-4"
                      >
                        Tentar novamente
                      </button>
                    </div>
                  ) : null}

                  {canContinue && !members.isFetchNextPageError ? (
                    <div className="flex flex-col items-center gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => void members.fetchNextPage()}
                        disabled={members.isFetchingNextPage}
                        className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#2563EB] px-4 text-[12px] font-semibold text-white transition hover:bg-[#1D4ED8] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
                      >
                        {members.isFetchingNextPage ? (
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Users className="h-3.5 w-3.5" />
                        )}
                        {members.isFetchingNextPage
                          ? "Carregando"
                          : latestPage?.truncated
                            ? "Continuar avaliação"
                            : "Carregar mais alunos"}
                      </button>
                      <p className="text-[10px] text-[#98A2B3]">
                        A navegação continua pelo cursor opaco retornado pela API.
                      </p>
                    </div>
                  ) : null}

                  {latestPage?.notes.length ? (
                    <ul className="space-y-1 rounded-lg bg-[#F8FAFC] p-3">
                      {latestPage.notes.map((note, index) => (
                        <li key={index} className="text-[10px] leading-relaxed text-[#98A2B3]">
                          {note}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </>
              ) : null}
            </section>

            <section className="rounded-xl border border-[#E5E7EB] bg-white p-4">
              <div className="flex items-start gap-2.5">
                <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-[#667085]" />
                <p className="text-[11px] leading-relaxed text-[#667085]">
                  Não há snapshot transacional entre páginas. Cada requisição avalia os dados
                  disponíveis naquele momento; alterações na base podem mudar os integrantes
                  durante a navegação.
                </p>
              </div>
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
