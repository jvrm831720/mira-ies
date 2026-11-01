"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CircleHelp,
  Layers,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { StudentGroupSummaryItem } from "@/types/api";

const GROUP_ICONS: Record<string, LucideIcon> = {
  risk_critical: ShieldAlert,
  risk_medium: ShieldCheck,
  financial_delay: Wallet,
  days_without_login_elevated: Activity,
  risk_increase: TrendingUp,
  multiple_active_signals: Layers,
  missing_score: CircleHelp,
};

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

function GroupCard({
  group,
  summary,
  summaryLoading,
  summaryError,
}: {
  group: {
    id: string;
    name: string;
    description: string;
    inclusion_rule: string;
    limitations: string[];
    coverage_semantics: string;
  };
  summary?: StudentGroupSummaryItem;
  summaryLoading: boolean;
  summaryError: boolean;
}) {
  const Icon = GROUP_ICONS[group.id] || Layers;
  const count = summary
    ? summary.matched_count.toLocaleString("pt-BR")
    : summaryLoading
      ? "Carregando"
      : summaryError
        ? "Indisponível"
        : "Não retornado";

  return (
    <Link
      href={"/alunos/grupos/" + encodeURIComponent(group.id)}
      className="group flex h-full flex-col rounded-xl border border-[#E5E7EB] bg-white p-5 transition hover:-translate-y-0.5 hover:border-[#CBD5E1] hover:shadow-[0_8px_24px_rgba(16,24,40,0.06)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
    >
      <div className="flex items-start justify-between gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#EFF6FF] text-[#2563EB]">
          <Icon className="h-5 w-5" />
        </span>
        <ArrowRight className="mt-1 h-4 w-4 text-[#98A2B3] transition group-hover:translate-x-0.5 group-hover:text-[#2563EB]" />
      </div>

      <div className="mt-4">
        <h2 className="text-[16px] font-semibold tracking-[-0.02em] text-[#111827]">
          {group.name}
        </h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-[#667085]">
          {group.description}
        </p>
      </div>

      <div className="mt-5 rounded-lg bg-[#F8FAFC] p-3.5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
          Alunos no grupo
        </p>
        <p className="mt-1 text-[26px] font-semibold tracking-[-0.04em] tabular-nums text-[#111827]">
          {count}
        </p>
        <p className="mt-0.5 text-[11px] text-[#667085]">
          {summary
            ? summary.indeterminate_count.toLocaleString("pt-BR") +
              " com dados insuficientes para confirmar"
            : summaryError
              ? "A contagem não foi carregada"
              : "Aguardando avaliação"}
        </p>
      </div>

      <div className="mt-4 flex-1 space-y-2.5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">
            Critério de inclusão
          </p>
          <p className="mt-1 text-[12px] leading-relaxed text-[#344054]">
            {group.inclusion_rule}
          </p>
        </div>
        {summary ? (
          <div className="border-t border-[#F2F4F7] pt-3">
            <div className="flex items-center justify-between gap-2 text-[11px]">
              <span className="text-[#667085]">Cobertura avaliada</span>
              <span className="font-semibold tabular-nums text-[#344054]">
                {summary.coverage.percentage == null
                  ? "Não calculável"
                  : summary.coverage.percentage.toLocaleString("pt-BR") + "%"}
              </span>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-[#98A2B3]">
              {summary.coverage.evaluated.toLocaleString("pt-BR")} de{" "}
              {summary.coverage.eligible.toLocaleString("pt-BR")} alunos elegíveis
              {" · "}
              {summary.false_count.toLocaleString("pt-BR")} não confirmados
            </p>
          </div>
        ) : null}
        {group.id === "missing_score" ? (
          <p className="rounded-lg border border-[#FEDF89] bg-[#FFFAEB] px-3 py-2 text-[11px] leading-relaxed text-[#B54708]">
            Lacuna de cobertura de score. Não representa baixo risco.
          </p>
        ) : null}
        {group.limitations.length > 0 ? (
          <p className="text-[11px] leading-relaxed text-[#98A2B3]">
            {group.limitations[0]}
          </p>
        ) : null}
      </div>

      <span className="mt-4 inline-flex items-center gap-1.5 text-[12px] font-semibold text-[#2563EB]">
        Ver integrantes e explicações
        <ArrowRight className="h-3.5 w-3.5" />
      </span>
    </Link>
  );
}

export default function StudentGroupsPage() {
  const catalog = useQuery({
    queryKey: ["student-groups", "catalog"],
    queryFn: () => api.studentGroupsCatalog(),
    retry: false,
    staleTime: 60_000,
  });
  const summary = useQuery({
    queryKey: ["student-groups", "summary"],
    queryFn: () => api.studentGroupsSummary(),
    retry: false,
    staleTime: 30_000,
  });

  const summaryById = new Map(
    (summary.data?.groups || []).map((item) => [item.id, item])
  );

  async function refresh() {
    await Promise.all([catalog.refetch(), summary.refetch()]);
  }

  return (
    <>
      <Header title="Grupos de alunos" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <section className="flex flex-col gap-3 border-b border-[#E5E7EB] pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[22px] font-semibold tracking-[-0.03em] text-[#111827] sm:text-[24px]">
                Grupos de alunos
              </h1>
              {catalog.data ? (
                <span className="rounded-full bg-[#F2F4F7] px-2 py-1 text-[10px] font-semibold text-[#667085]">
                  {catalog.data.count} grupos
                </span>
              ) : null}
            </div>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[#667085]">
              Explore segmentos calculados a partir dos sinais disponíveis e entenda os
              critérios usados em cada avaliação.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/alunos"
              className="inline-flex h-10 items-center rounded-lg border border-[#E5E7EB] bg-white px-3.5 text-[13px] font-medium text-[#344054] transition hover:bg-[#F8FAFC] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            >
              Voltar para alunos
            </Link>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={catalog.isFetching || summary.isFetching}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#2563EB] px-3.5 text-[13px] font-semibold text-white transition hover:bg-[#1D4ED8] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            >
              <RefreshCw
                className={
                  "h-3.5 w-3.5" +
                  (catalog.isFetching || summary.isFetching ? " animate-spin" : "")
                }
              />
              Atualizar
            </button>
          </div>
        </section>

        {summary.isError && !summary.data ? (
          <div
            role="alert"
            className="flex flex-col gap-2 rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="text-[13px] font-semibold text-[#B42318]">
                As contagens não estão disponíveis.
              </p>
              <p className="mt-1 text-[12px] text-[#667085]">
                A consulta falhou. Os grupos continuam sem números até que a API responda.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void summary.refetch()}
              className="self-start text-[12px] font-semibold text-[#B42318] underline underline-offset-4 sm:self-auto"
            >
              Tentar novamente
            </button>
          </div>
        ) : null}

        {summary.data?.truncated ? (
          <div className="flex items-start gap-2.5 rounded-xl border border-[#FEDF89] bg-[#FFFAEB] p-4 text-[#B54708]">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="text-[12px] font-semibold">Avaliação parcial da base</p>
              <p className="mt-1 text-[12px] leading-relaxed">
                A API sinalizou truncagem. As contagens refletem somente os alunos
                efetivamente avaliados nesta resposta.
              </p>
            </div>
          </div>
        ) : null}

        <section aria-label="Catálogo de grupos de alunos">
          {catalog.isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 7 }).map((_, index) => (
                <Skeleton key={index} className="h-[330px] rounded-xl" />
              ))}
            </div>
          ) : null}

          {catalog.isError && !catalog.data ? (
            <div
              role="alert"
              className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-6"
            >
              <p className="text-[14px] font-semibold text-[#B42318]">
                Não foi possível carregar os grupos.
              </p>
              <p className="mt-1 text-[12px] text-[#667085]">
                {catalog.error instanceof Error
                  ? catalog.error.message
                  : "Verifique sua sessão e tente novamente."}
              </p>
              <button
                type="button"
                onClick={() => void catalog.refetch()}
                className="mt-3 text-[12px] font-semibold text-[#B42318] underline underline-offset-4"
              >
                Tentar novamente
              </button>
            </div>
          ) : null}

          {!catalog.isLoading && catalog.data?.groups.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[#D0D5DD] bg-white px-5 py-12 text-center">
              <CircleHelp className="mx-auto h-7 w-7 text-[#98A2B3]" />
              <p className="mt-3 text-[14px] font-semibold text-[#111827]">
                Nenhum grupo disponível
              </p>
              <p className="mt-1 text-[12px] text-[#667085]">
                O catálogo não retornou grupos nesta consulta.
              </p>
            </div>
          ) : null}

          {catalog.data && catalog.data.groups.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {catalog.data.groups.map((group) => (
                <GroupCard
                  key={group.id}
                  group={group}
                  summary={summaryById.get(group.id)}
                  summaryLoading={summary.isLoading}
                  summaryError={summary.isError && !summary.data}
                />
              ))}
            </div>
          ) : null}
        </section>

        <section className="rounded-xl border border-[#E5E7EB] bg-white p-4 sm:p-5">
          <div className="flex items-start gap-2.5">
            <CircleHelp className="mt-0.5 h-4 w-4 shrink-0 text-[#667085]" />
            <div>
              <h2 className="text-[13px] font-semibold text-[#111827]">
                Como interpretar os grupos
              </h2>
              <p className="mt-1 text-[12px] leading-relaxed text-[#667085]">
                Um aluno pode pertencer a mais de um grupo. Portanto, as contagens não
                devem ser somadas para estimar alunos únicos. Resultados indeterminados
                representam dados insuficientes e não são tratados como ausência de risco.
              </p>
              {summary.data?.evaluated_at ? (
                <p className="mt-2 text-[11px] text-[#98A2B3]">
                  Avaliação do resumo: {formatDateTime(summary.data.evaluated_at)}
                </p>
              ) : null}
            </div>
          </div>
        </section>
      </main>
    </>
  );
}
