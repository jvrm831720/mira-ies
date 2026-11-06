"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  BookOpenCheck,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  GraduationCap,
  MessageSquare,
  RefreshCw,
  ShieldAlert,
  Users,
} from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type {
  OperationalPermanenceBreakdown,
  PermanenceAnalytics,
  PermanenceBreakdown,
} from "@/types/api";

const DAYS = [90, 180, 365, 730] as const;
type ResultTab = "educational" | "operational";

function numberLabel(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("pt-BR");
}

function percentLabel(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function dateTimeLabel(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = "neutral",
}: {
  icon: typeof Users;
  label: string;
  value: string;
  detail: string;
  tone?: "neutral" | "positive" | "warning" | "danger";
}) {
  const toneClass = {
    neutral: "bg-[var(--color-legacy-f2f4f7)] text-[var(--color-legacy-475467)]",
    positive: "bg-[var(--color-source-ecfdf3)] text-[var(--color-source-027a48)]",
    warning: "bg-[var(--color-source-fffaeb)] text-[var(--color-source-b54708)]",
    danger: "bg-[var(--color-red-tint)] text-[var(--color-legacy-b42318)]",
  }[tone];

  return (
    <article className="rounded-[10px] border border-[var(--color-line)] bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-667085)]">{label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-[-0.035em] text-[var(--color-legacy-101828)]">{value}</p>
        </div>
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${toneClass}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="mt-2 text-[length:var(--type-overline)] leading-relaxed text-[var(--color-legacy-667085)]">{detail}</p>
    </article>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex min-w-[155px] flex-1 flex-col gap-1.5 text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-475467)]">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-lg border border-[var(--color-legacy-d0d5dd)] bg-white px-3 text-xs text-[var(--color-legacy-344054)] outline-none focus:border-[var(--color-blue)] focus:ring-2 focus:ring-[var(--color-blue)]/15"
      >
        {children}
      </select>
    </label>
  );
}

function EmptyBreakdown({ text }: { text: string }) {
  return <p className="rounded-lg bg-[var(--color-legacy-f8fafc)] px-4 py-6 text-center text-xs text-[var(--color-legacy-667085)]">{text}</p>;
}

function EducationalBreakdown({
  title,
  description,
  rows,
}: {
  title: string;
  description: string;
  rows: PermanenceBreakdown[];
}) {
  return (
    <section className="rounded-[10px] border border-[var(--color-line)] bg-white p-5">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-[var(--color-legacy-101828)]">{title}</h2>
        <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">{description}</p>
      </div>
      {rows.length === 0 ? <EmptyBreakdown text="Sem outcomes acadêmicos confirmados neste recorte." /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead className="bg-[var(--color-panel)] text-[length:var(--type-overline)] font-semibold uppercase tracking-[0.05em] text-[var(--color-legacy-667085)]">
              <tr>
                <th className="px-3 py-2">Grupo</th>
                <th className="px-3 py-2">Desfechos</th>
                <th className="px-3 py-2">Rematrículas</th>
                <th className="px-3 py-2">Evasões</th>
                <th className="px-3 py-2">Permanência obs.</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-legacy-eaecf0)]">
              {rows.map((row) => (
                <tr key={row.key}>
                  <td className="px-3 py-2.5 font-medium text-[var(--color-legacy-101828)]">{row.label}</td>
                  <td className="px-3 py-2.5 tabular-nums">{numberLabel(row.confirmed_outcomes)}</td>
                  <td className="px-3 py-2.5 tabular-nums">{numberLabel(row.rematriculados)}</td>
                  <td className="px-3 py-2.5 tabular-nums">{numberLabel(row.evasion_outcomes)}</td>
                  <td className="px-3 py-2.5 tabular-nums">{percentLabel(row.permanence_rate_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function OperationalBreakdown({
  title,
  description,
  rows,
}: {
  title: string;
  description: string;
  rows: OperationalPermanenceBreakdown[];
}) {
  return (
    <section className="rounded-[10px] border border-[var(--color-line)] bg-white p-5">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-[var(--color-legacy-101828)]">{title}</h2>
        <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">{description}</p>
      </div>
      {rows.length === 0 ? <EmptyBreakdown text="Sem registros operacionais para agrupar neste recorte." /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-xs">
            <thead className="bg-[var(--color-source-f9fafb)] text-[length:var(--type-overline)] font-semibold uppercase tracking-[0.05em] text-[var(--color-legacy-667085)]">
              <tr>
                <th className="px-3 py-2">Grupo</th>
                <th className="px-3 py-2">Mensagens enviadas</th>
                <th className="px-3 py-2">Alunos contactados</th>
                <th className="px-3 py-2">Entregues</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-legacy-eaecf0)]">
              {rows.map((row) => (
                <tr key={row.key}>
                  <td className="px-3 py-2.5 font-medium text-[var(--color-legacy-101828)]">{row.label}</td>
                  <td className="px-3 py-2.5 tabular-nums">{numberLabel(row.messages_sent)}</td>
                  <td className="px-3 py-2.5 tabular-nums">{numberLabel(row.unique_students_contacted)}</td>
                  <td className="px-3 py-2.5 tabular-nums">{numberLabel(row.delivered_messages)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ComparisonCard({ data }: { data: PermanenceAnalytics["comparison"] }) {
  const available = data.status === "available_descriptive";
  return (
    <section className="rounded-xl border border-[var(--color-source-fedf89)] bg-[var(--color-source-fffaeb)] p-5">
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-source-b54708)]" />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-[var(--color-legacy-7a2e0e)]">Comparação observacional entre grupos</h2>
          <p className="mt-1 text-[length:var(--type-caption)] leading-relaxed text-[var(--color-legacy-93370d)]">
            {available
              ? "Diferença padronizada por faixa de risco basal. A comparação não demonstra que a intervenção causou o resultado."
              : data.reason}
          </p>
          {available ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-[var(--color-legacy-fde68a)] bg-white/70 p-3">
                <p className="text-[length:var(--type-overline)] text-[var(--color-legacy-93370d)]">Com intervenção</p>
                <p className="mt-1 text-lg font-semibold text-[var(--color-legacy-7a2e0e)]">{percentLabel(data.permanence_rate_exposed_pct)}</p>
                <p className="text-[length:var(--type-overline)] text-[var(--color-legacy-93370d)]">n = {numberLabel(data.exposed_n)}</p>
              </div>
              <div className="rounded-lg border border-[var(--color-legacy-fde68a)] bg-white/70 p-3">
                <p className="text-[length:var(--type-overline)] text-[var(--color-legacy-93370d)]">Sem intervenção enviada em 90 dias</p>
                <p className="mt-1 text-lg font-semibold text-[var(--color-legacy-7a2e0e)]">{percentLabel(data.permanence_rate_no_intervention_standardized_pct)}</p>
                <p className="text-[length:var(--type-overline)] text-[var(--color-legacy-93370d)]">n = {numberLabel(data.no_intervention_n)}</p>
              </div>
              <div className="rounded-lg border border-[var(--color-legacy-fde68a)] bg-white/70 p-3">
                <p className="text-[length:var(--type-overline)] text-[var(--color-legacy-93370d)]">Diferença descritiva</p>
                <p className="mt-1 text-lg font-semibold text-[var(--color-legacy-7a2e0e)]">
                  {data.difference_percentage_points == null ? "—" : `${data.difference_percentage_points > 0 ? "+" : ""}${data.difference_percentage_points.toLocaleString("pt-BR")} p.p.`}
                </p>
                <p className="text-[length:var(--type-overline)] text-[var(--color-legacy-93370d)]">Faixas de risco: {data.common_risk_bands?.join(", ") || "—"}</p>
              </div>
            </div>
          ) : (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[length:var(--type-overline)] text-[var(--color-legacy-93370d)]">
              <span>Com intervenção: {numberLabel(data.exposed_n)}</span>
              <span>Sem intervenção: {numberLabel(data.no_intervention_n)}</span>
              <span>Exposições mistas excluídas: {numberLabel(data.mixed_exposure_excluded)}</span>
              <span>Sem risco basal: {numberLabel(data.missing_baseline_risk_excluded)}</span>
            </div>
          )}
          <p className="mt-3 text-[length:var(--type-overline)] leading-relaxed text-[var(--color-legacy-93370d)]">
            Critérios: ao menos {data.minimum_group_size} outcomes por grupo, {data.minimum_per_stratum} por faixa de risco e suporte comum suficiente. Transferências não entram no denominador.
          </p>
        </div>
      </div>
    </section>
  );
}

function EducationalHistory({ data }: { data: PermanenceAnalytics["educational"] }) {
  return (
    <section className="overflow-hidden rounded-[10px] border border-[var(--color-line)] bg-white">
      <div className="flex flex-col gap-1 border-b border-[var(--color-line)] px-5 py-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[var(--color-legacy-101828)]">Histórico de resultados por estudante</h2>
          <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">Eventos acadêmicos mais recentes. Exibição limitada a 100 registros.</p>
        </div>
        <span className="text-[length:var(--type-overline)] text-[var(--color-legacy-667085)]">{numberLabel(data.records_total)} outcomes no recorte</span>
      </div>
      {data.records.length === 0 ? (
        <div className="px-5 py-10 text-center">
          <BookOpenCheck className="mx-auto h-5 w-5 text-[var(--color-legacy-98a2b3)]" />
          <p className="mt-3 text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-344054)]">Ainda não há desfechos acadêmicos confirmados</p>
          <p className="mx-auto mt-1 max-w-xl text-[length:var(--type-caption)] leading-relaxed text-[var(--color-legacy-667085)]">
            Importe eventos de matrícula, rematrícula, trancamento, evasão, conclusão ou transferência pelo endpoint acadêmico. Sem outcome registrado, a MIRA não presume permanência nem evasão.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-left text-[length:var(--type-caption)]">
            <thead className="bg-[var(--color-source-f9fafb)] text-[length:var(--type-overline)] font-semibold uppercase tracking-[0.05em] text-[var(--color-legacy-667085)]">
              <tr>
                <th className="px-4 py-3">Estudante</th>
                <th className="px-4 py-3">Curso</th>
                <th className="px-4 py-3">Desfecho acadêmico</th>
                <th className="px-4 py-3">Período letivo</th>
                <th className="px-4 py-3">Observado em</th>
                <th className="px-4 py-3">Fonte</th>
                <th className="px-4 py-3">Intervenções relacionadas</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-legacy-eaecf0)]">
              {data.records.map((record) => (
                <tr key={record.event_id} className="hover:bg-[var(--color-source-f9fafb)]">
                  <td className="px-4 py-3">
                    {record.student_id ? (
                      <Link href={`/alunos/${record.student_id}`} className="font-semibold text-[var(--color-blue)] hover:underline">
                        {record.student_name || record.matricula}
                      </Link>
                    ) : <span className="font-semibold text-[var(--color-legacy-101828)]">{record.student_name || record.matricula}</span>}
                    <span className="mt-0.5 block text-[length:var(--type-overline)] text-[var(--color-legacy-667085)]">{record.matricula}</span>
                  </td>
                  <td className="px-4 py-3 text-[var(--color-legacy-475467)]">{record.course || "Não informado"}</td>
                  <td className="px-4 py-3 font-medium text-[var(--color-legacy-344054)]">{record.outcome_label}</td>
                  <td className="px-4 py-3 text-[var(--color-legacy-475467)]">
                    {record.academic_period || <span className="text-[var(--color-source-b54708)">Não informado</span>}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-[var(--color-legacy-475467)]">{dateTimeLabel(record.outcome_at)}</td>
                  <td className="px-4 py-3 text-[var(--color-legacy-475467)]">{record.outcome_source}</td>
                  <td className="px-4 py-3 text-[var(--color-legacy-475467)]">
                    {record.intervention_count ? (
                      <span title={[...record.channels, ...record.campaigns].join(" · ") || undefined}>
                        {numberLabel(record.intervention_count)} registro(s)
                        {record.channels.length ? ` · ${record.channels.join(", ")}` : ""}
                      </span>
                    ) : "Sem envio identificado em 90 dias"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function EducationalResults({ data }: { data: PermanenceAnalytics }) {
  const education = data.educational;
  const summary = education.summary;
  const noOutcomes = education.records_total === 0;
  return (
    <div className="space-y-4" role="tabpanel" id="panel-educational" aria-labelledby="tab-educational">
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={CheckCircle2} label="Rematrículas confirmadas" value={numberLabel(summary.rematriculados)} detail={`${percentLabel(summary.rematricula_share_pct)} dos desfechos decisivos no recorte`} tone="positive" />
        <MetricCard icon={GraduationCap} label="Permanência observada" value={percentLabel(summary.permanence_rate_pct)} detail={`${numberLabel(summary.permanence_outcomes)} ativos, rematriculados ou concluintes entre os desfechos decisivos`} tone="positive" />
        <MetricCard icon={CircleAlert} label="Evasões / trancamentos" value={numberLabel(summary.evasion_outcomes)} detail={`${percentLabel(summary.evasion_rate_pct)} dos desfechos decisivos confirmados`} tone="danger" />
        <MetricCard icon={CalendarDays} label="Com período letivo informado" value={percentLabel(summary.academic_period_coverage_pct)} detail={`${numberLabel(summary.outcomes_with_academic_period)} de ${numberLabel(summary.confirmed_outcomes)} registros`} tone="warning" />
      </section>

      {noOutcomes && (
        <div className="rounded-xl border border-[var(--color-legacy-b2ccff)] bg-[var(--color-legacy-eff8ff)] p-4 text-[length:var(--type-caption)] leading-relaxed text-[var(--color-legacy-175cd3)]">
          Estes indicadores usam outcomes acadêmicos confirmados. Ausência de registro não significa permanência ou evasão. Para histórico por período letivo, a origem deve enviar o código real do período; ele não é inferido do semestre de curso nem do mês-calendário.
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <EducationalBreakdown title="Permanência por período letivo" description="Agrupamento pelo período informado na origem acadêmica; eventos sem período ficam separados." rows={education.by_academic_period} />
        <EducationalBreakdown title="Resultados por curso" description="Outcomes acadêmicos confirmados por curso no recorte selecionado." rows={education.by_course} />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <EducationalBreakdown title="Outcomes associados a campanhas" description="Estudantes com envio de campanha nos 90 dias anteriores ao outcome. Associação temporal, não causal." rows={education.by_campaign} />
        <EducationalBreakdown title="Outcomes associados a canal" description="Estudantes com envio por canal nos 90 dias anteriores ao outcome. Associação temporal, não causal." rows={education.by_channel} />
      </div>

      <ComparisonCard data={data.comparison} />
      <EducationalHistory data={education} />
      <p className="px-1 text-[length:var(--type-overline)] leading-relaxed text-[var(--color-legacy-667085)]">
        Definição: rematrícula, status ativo, conclusão e formatura são resultados de permanência; evasão e trancamento são saídas; transferências ficam fora das taxas. Taxas são descritivas e não afirmam causalidade.
      </p>
    </div>
  );
}

function OperationalResults({ data }: { data: PermanenceAnalytics }) {
  const operations = data.operational;
  const summary = operations.summary;
  return (
    <div className="space-y-4" role="tabpanel" id="panel-operational" aria-labelledby="tab-operational">
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={MessageSquare} label="Mensagens enviadas" value={numberLabel(summary.messages_sent)} detail={`${numberLabel(summary.records)} registros operacionais no recorte`} />
        <MetricCard icon={Users} label="Estudantes contactados" value={numberLabel(summary.unique_students_contacted)} detail="Estudantes únicos com ao menos um envio confirmado" />
        <MetricCard icon={CheckCircle2} label="Entrega registrada" value={percentLabel(summary.delivery_rate_pct)} detail={`${numberLabel(summary.delivered_messages)} eventos de entrega entre os envios`} tone="positive" />
        <MetricCard icon={Activity} label="Engajamento registrado" value={percentLabel(summary.engagement_rate_pct)} detail={`${numberLabel(summary.engaged_messages)} leituras, cliques ou respostas`} />
      </section>
      <div className="rounded-xl border border-[var(--color-legacy-d1e9ff)] bg-[var(--color-legacy-eff8ff)] p-4 text-[length:var(--type-caption)] leading-relaxed text-[var(--color-legacy-175cd3)]">
        Indicadores operacionais descrevem execução, entrega e engajamento. Mensagem enviada ou entregue não comprova rematrícula nem permanência; consulte a aba “Resultados educacionais” para outcomes acadêmicos confirmados.
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <OperationalBreakdown title="Execução por campanha" description="Campanha vinculada ao registro de intervenção." rows={operations.by_campaign} />
        <OperationalBreakdown title="Execução por canal" description="Volume e entrega por canal no recorte selecionado." rows={operations.by_channel} />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <OperationalBreakdown title="Execução por curso" description="Curso atual do estudante associado ao contato." rows={operations.by_course} />
        <OperationalBreakdown
          title="Evolução por mês-calendário"
          description="Recorte operacional mensal — não equivale a período letivo."
          rows={operations.by_calendar_month.map((row) => ({
            key: row.key,
            label: row.label,
            records: row.records,
            messages_sent: row.messages_sent,
            unique_students_contacted: row.unique_students_contacted,
            delivered_messages: row.delivered_messages,
          }))}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-[var(--color-line)] bg-white p-4">
        <div>
          <p className="text-xs font-semibold text-[var(--color-legacy-101828)]">Precisa revisar um contato específico?</p>
          <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">O histórico detalhado fica separado dos outcomes educacionais.</p>
        </div>
        <Link href="/retencao/logs" className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--color-legacy-d0d5dd)] px-3 text-[length:var(--type-caption)] font-semibold text-[var(--color-legacy-344054)] hover:bg-[var(--color-source-f9fafb)]">
          Histórico de contatos <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}

export function PermanenceResultsPage() {
  const [tab, setTab] = useState<ResultTab>("educational");
  const [days, setDays] = useState<number>(365);
  const [academicPeriod, setAcademicPeriod] = useState("");
  const [course, setCourse] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [channel, setChannel] = useState("");
  const query = useQuery({
    queryKey: ["permanence-analytics", days, academicPeriod, course, campaignId, channel],
    queryFn: () => api.permanenceAnalytics({
      days,
      academic_period: academicPeriod || undefined,
      course: course || undefined,
      campaign_id: campaignId || undefined,
      channel: channel ? channel as "whatsapp" | "email" | "sms" : undefined,
    }),
    retry: false,
  });
  const data = query.data;

  return (
    <>
      <Header title="Resultados de permanência" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <section className="flex flex-col gap-3 border-b border-[var(--color-legacy-e5e7eb)] pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[length:var(--type-caption)] font-semibold uppercase tracking-[0.08em] text-[var(--color-blue)]">
              <BookOpenCheck className="h-3.5 w-3.5" /> Mensuração educacional
            </div>
            <h1 className="text-2xl font-semibold tracking-[-0.035em] text-[var(--color-legacy-101828)]">Resultados de permanência</h1>
            <p className="mt-1 max-w-3xl text-[length:var(--type-body-compact)] leading-relaxed text-[var(--color-legacy-667085)]">
              Acompanhe rematrícula, evasão e permanência por período letivo — e relacione os desfechos acadêmicos às intervenções sem presumir causalidade.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-[var(--color-legacy-d0d5dd)] bg-white px-3 text-xs font-medium text-[var(--color-legacy-344054)] hover:bg-[var(--color-source-f9fafb)] disabled:opacity-60"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${query.isFetching ? "animate-spin" : ""}`} /> Atualizar
            </button>
            <Link href="/retencao/logs" className="inline-flex h-10 items-center gap-2 rounded-lg bg-[var(--color-ink-900)] px-3.5 text-xs font-medium text-white hover:bg-[var(--color-ink)]">
              Histórico de contatos <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </section>

        <section aria-label="Filtros de resultados" className="flex flex-wrap items-end gap-3 rounded-xl border border-[var(--color-legacy-e5e7eb)] bg-white p-4">
          <FilterSelect label="Janela de observação" value={String(days)} onChange={(value) => setDays(Number(value))}>
            {DAYS.map((value) => <option key={value} value={value}>Últimos {value} dias</option>)}
          </FilterSelect>
          <FilterSelect label="Período letivo" value={academicPeriod} onChange={setAcademicPeriod}>
            <option value="">Todos os períodos</option>
            {(data?.options.academic_periods || []).map((period) => <option key={period} value={period}>{period}</option>)}
          </FilterSelect>
          <FilterSelect label="Curso" value={course} onChange={setCourse}>
            <option value="">Todos os cursos</option>
            {(data?.options.courses || []).map((value) => <option key={value} value={value}>{value}</option>)}
          </FilterSelect>
          <FilterSelect label="Campanha" value={campaignId} onChange={setCampaignId}>
            <option value="">Todas as campanhas</option>
            {(data?.options.campaigns || []).map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}
          </FilterSelect>
          <FilterSelect label="Canal" value={channel} onChange={setChannel}>
            <option value="">Todos os canais</option>
            {(data?.options.channels || []).map((value) => <option key={value} value={value}>{value === "whatsapp" ? "WhatsApp" : value === "email" ? "E-mail" : value === "sms" ? "SMS" : value}</option>)}
          </FilterSelect>
        </section>
        <p className="-mt-3 px-1 text-[length:var(--type-overline)] leading-relaxed text-[var(--color-legacy-667085)]">
          O filtro de período letivo restringe os outcomes acadêmicos. Indicadores operacionais usam a janela de dias selecionada e são agrupados por mês-calendário.
        </p>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div role="tablist" aria-label="Tipo de resultados" className="inline-flex items-center gap-5 border-b border-[var(--color-line)] bg-white">
            <button
              id="tab-educational"
              role="tab"
              aria-selected={tab === "educational"}
              aria-controls="panel-educational"
              onClick={() => setTab("educational")}
              className={`inline-flex h-10 items-center gap-2 border-b-2 px-1 text-xs font-medium transition ${tab === "educational" ? "border-[var(--color-legacy-1c1d1f)] text-[var(--color-legacy-1c1d1f)]" : "border-transparent text-[var(--color-legacy-6f7988)] hover:text-[var(--color-legacy-1c1d1f)]"}`}
            >
              <GraduationCap className="h-3.5 w-3.5" /> Resultados educacionais
            </button>
            <button
              id="tab-operational"
              role="tab"
              aria-selected={tab === "operational"}
              aria-controls="panel-operational"
              onClick={() => setTab("operational")}
              className={`inline-flex h-10 items-center gap-2 border-b-2 px-1 text-xs font-medium transition ${tab === "operational" ? "border-[var(--color-legacy-1c1d1f)] text-[var(--color-legacy-1c1d1f)]" : "border-transparent text-[var(--color-legacy-6f7988)] hover:text-[var(--color-legacy-1c1d1f)]"}`}
            >
              <Activity className="h-3.5 w-3.5" /> Resultados operacionais
            </button>
          </div>
          <p className="text-[length:var(--type-overline)] text-[var(--color-legacy-667085)]">
            {data?.generated_at ? `Dados atualizados ${dateTimeLabel(data.generated_at)}` : `Janela: ${days} dias`}
          </p>
        </div>

        {query.isLoading && <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[1, 2, 3, 4].map((n) => <Skeleton key={n} className="h-28 rounded-xl" />)}</div>}
        {query.isError && (
          <div role="alert" className="rounded-xl border border-[var(--color-legacy-fecdca)] bg-[var(--color-red-tint)] p-5 text-xs text-[var(--color-legacy-b42318)]">
            <p className="font-semibold">Não foi possível carregar os resultados de permanência.</p>
            <p className="mt-1">Verifique a disponibilidade da API acadêmica e os dados do período selecionado.</p>
            <button type="button" onClick={() => void query.refetch()} className="mt-3 font-semibold underline">Tentar novamente</button>
          </div>
        )}
        {data && (tab === "educational" ? <EducationalResults data={data} /> : <OperationalResults data={data} />)}

        <div className="flex items-start gap-2 rounded-lg border border-[var(--color-legacy-e5e7eb)] bg-[var(--color-source-f9fafb)] p-3 text-[length:var(--type-overline)] leading-relaxed text-[var(--color-legacy-667085)]">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--color-legacy-667085)]" />
          <p>
            Outcomes acadêmicos dependem de importação explícita da instituição. Dados ausentes não são classificados como permanência ou evasão; envio, resposta e entrega são indicadores operacionais, não outcomes educacionais.
          </p>
        </div>
      </main>
    </>
  );
}
