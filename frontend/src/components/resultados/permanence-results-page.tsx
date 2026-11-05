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
} from "lucide-react";
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
    neutral: "bg-[#F2F4F7] text-[#475467]",
    positive: "bg-[#ECFDF3] text-[#027A48]",
    warning: "bg-[#FFFAEB] text-[#B54708]",
    danger: "bg-[#FEF3F2] text-[#B42318]",
  }[tone];

  return (
    <article className="rounded-[10px] border border-[#E4E7EC] bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium text-[#667085]">{label}</p>
          <p className="mt-2 text-[24px] font-semibold tracking-[-0.035em] text-[#101828]">{value}</p>
        </div>
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${toneClass}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-[#667085]">{detail}</p>
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
    <label className="flex min-w-[155px] flex-1 flex-col gap-1.5 text-[11px] font-medium text-[#475467]">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] text-[#344054] outline-none focus:border-[#266DF0] focus:ring-2 focus:ring-[#266DF0]/15"
      >
        {children}
      </select>
    </label>
  );
}

function EmptyBreakdown({ text }: { text: string }) {
  return <p className="rounded-lg bg-[#F8FAFC] px-4 py-6 text-center text-[12px] text-[#667085]">{text}</p>;
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
    <section className="rounded-[10px] border border-[#E4E7EC] bg-white p-5">
      <div className="mb-4">
        <h2 className="text-[14px] font-semibold text-[#101828]">{title}</h2>
        <p className="mt-1 text-[11px] text-[#667085]">{description}</p>
      </div>
      {rows.length === 0 ? <EmptyBreakdown text="Sem outcomes acadêmicos confirmados neste recorte." /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-[12px]">
            <thead className="bg-[#F8F9FA] text-[10px] font-semibold uppercase tracking-[0.05em] text-[#667085]">
              <tr>
                <th className="px-3 py-2">Grupo</th>
                <th className="px-3 py-2">Desfechos</th>
                <th className="px-3 py-2">Rematrículas</th>
                <th className="px-3 py-2">Evasões</th>
                <th className="px-3 py-2">Permanência obs.</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EAECF0]">
              {rows.map((row) => (
                <tr key={row.key}>
                  <td className="px-3 py-2.5 font-medium text-[#101828]">{row.label}</td>
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
    <section className="rounded-[10px] border border-[#E4E7EC] bg-white p-5">
      <div className="mb-4">
        <h2 className="text-[14px] font-semibold text-[#101828]">{title}</h2>
        <p className="mt-1 text-[11px] text-[#667085]">{description}</p>
      </div>
      {rows.length === 0 ? <EmptyBreakdown text="Sem registros operacionais para agrupar neste recorte." /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-[12px]">
            <thead className="bg-[#F9FAFB] text-[10px] font-semibold uppercase tracking-[0.05em] text-[#667085]">
              <tr>
                <th className="px-3 py-2">Grupo</th>
                <th className="px-3 py-2">Mensagens enviadas</th>
                <th className="px-3 py-2">Alunos contactados</th>
                <th className="px-3 py-2">Entregues</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EAECF0]">
              {rows.map((row) => (
                <tr key={row.key}>
                  <td className="px-3 py-2.5 font-medium text-[#101828]">{row.label}</td>
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
    <section className="rounded-xl border border-[#FEDF89] bg-[#FFFAEB] p-5">
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#B54708]" />
        <div className="min-w-0 flex-1">
          <h2 className="text-[14px] font-semibold text-[#7A2E0E]">Comparação observacional entre grupos</h2>
          <p className="mt-1 text-[11px] leading-relaxed text-[#93370D]">
            {available
              ? "Diferença padronizada por faixa de risco basal. A comparação não demonstra que a intervenção causou o resultado."
              : data.reason}
          </p>
          {available ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-[#FDE68A] bg-white/70 p-3">
                <p className="text-[10px] text-[#93370D]">Com intervenção</p>
                <p className="mt-1 text-lg font-semibold text-[#7A2E0E]">{percentLabel(data.permanence_rate_exposed_pct)}</p>
                <p className="text-[10px] text-[#93370D]">n = {numberLabel(data.exposed_n)}</p>
              </div>
              <div className="rounded-lg border border-[#FDE68A] bg-white/70 p-3">
                <p className="text-[10px] text-[#93370D]">Sem intervenção enviada em 90 dias</p>
                <p className="mt-1 text-lg font-semibold text-[#7A2E0E]">{percentLabel(data.permanence_rate_no_intervention_standardized_pct)}</p>
                <p className="text-[10px] text-[#93370D]">n = {numberLabel(data.no_intervention_n)}</p>
              </div>
              <div className="rounded-lg border border-[#FDE68A] bg-white/70 p-3">
                <p className="text-[10px] text-[#93370D]">Diferença descritiva</p>
                <p className="mt-1 text-lg font-semibold text-[#7A2E0E]">
                  {data.difference_percentage_points == null ? "—" : `${data.difference_percentage_points > 0 ? "+" : ""}${data.difference_percentage_points.toLocaleString("pt-BR")} p.p.`}
                </p>
                <p className="text-[10px] text-[#93370D]">Faixas de risco: {data.common_risk_bands?.join(", ") || "—"}</p>
              </div>
            </div>
          ) : (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-[#93370D]">
              <span>Com intervenção: {numberLabel(data.exposed_n)}</span>
              <span>Sem intervenção: {numberLabel(data.no_intervention_n)}</span>
              <span>Exposições mistas excluídas: {numberLabel(data.mixed_exposure_excluded)}</span>
              <span>Sem risco basal: {numberLabel(data.missing_baseline_risk_excluded)}</span>
            </div>
          )}
          <p className="mt-3 text-[10px] leading-relaxed text-[#93370D]">
            Critérios: ao menos {data.minimum_group_size} outcomes por grupo, {data.minimum_per_stratum} por faixa de risco e suporte comum suficiente. Transferências não entram no denominador.
          </p>
        </div>
      </div>
    </section>
  );
}

function EducationalHistory({ data }: { data: PermanenceAnalytics["educational"] }) {
  return (
    <section className="overflow-hidden rounded-[10px] border border-[#E4E7EC] bg-white">
      <div className="flex flex-col gap-1 border-b border-[#E4E7EC] px-5 py-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-[14px] font-semibold text-[#101828]">Histórico de resultados por estudante</h2>
          <p className="mt-1 text-[11px] text-[#667085]">Eventos acadêmicos mais recentes. Exibição limitada a 100 registros.</p>
        </div>
        <span className="text-[10px] text-[#667085]">{numberLabel(data.records_total)} outcomes no recorte</span>
      </div>
      {data.records.length === 0 ? (
        <div className="px-5 py-10 text-center">
          <BookOpenCheck className="mx-auto h-5 w-5 text-[#98A2B3]" />
          <p className="mt-3 text-[13px] font-semibold text-[#344054]">Ainda não há desfechos acadêmicos confirmados</p>
          <p className="mx-auto mt-1 max-w-xl text-[11px] leading-relaxed text-[#667085]">
            Importe eventos de matrícula, rematrícula, trancamento, evasão, conclusão ou transferência pelo endpoint acadêmico. Sem outcome registrado, a MIRA não presume permanência nem evasão.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-left text-[11px]">
            <thead className="bg-[#F9FAFB] text-[10px] font-semibold uppercase tracking-[0.05em] text-[#667085]">
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
            <tbody className="divide-y divide-[#EAECF0]">
              {data.records.map((record) => (
                <tr key={record.event_id} className="hover:bg-[#F9FAFB]">
                  <td className="px-4 py-3">
                    {record.student_id ? (
                      <Link href={`/alunos/${record.student_id}`} className="font-semibold text-[#266DF0] hover:underline">
                        {record.student_name || record.matricula}
                      </Link>
                    ) : <span className="font-semibold text-[#101828]">{record.student_name || record.matricula}</span>}
                    <span className="mt-0.5 block text-[10px] text-[#667085]">{record.matricula}</span>
                  </td>
                  <td className="px-4 py-3 text-[#475467]">{record.course || "Não informado"}</td>
                  <td className="px-4 py-3 font-medium text-[#344054]">{record.outcome_label}</td>
                  <td className="px-4 py-3 text-[#475467]">
                    {record.academic_period || <span className="text-[#B54708">Não informado</span>}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-[#475467]">{dateTimeLabel(record.outcome_at)}</td>
                  <td className="px-4 py-3 text-[#475467]">{record.outcome_source}</td>
                  <td className="px-4 py-3 text-[#475467]">
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
        <div className="rounded-xl border border-[#B2CCFF] bg-[#EFF8FF] p-4 text-[11px] leading-relaxed text-[#175CD3]">
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
      <p className="px-1 text-[10px] leading-relaxed text-[#667085]">
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
      <div className="rounded-xl border border-[#D1E9FF] bg-[#EFF8FF] p-4 text-[11px] leading-relaxed text-[#175CD3]">
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
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-[#E4E7EC] bg-white p-4">
        <div>
          <p className="text-[12px] font-semibold text-[#101828]">Precisa revisar um contato específico?</p>
          <p className="mt-1 text-[11px] text-[#667085]">O histórico detalhado fica separado dos outcomes educacionais.</p>
        </div>
        <Link href="/retencao/logs" className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#D0D5DD] px-3 text-[11px] font-semibold text-[#344054] hover:bg-[#F9FAFB]">
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
        <section className="flex flex-col gap-3 border-b border-[#E5E7EB] pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#266DF0]">
              <BookOpenCheck className="h-3.5 w-3.5" /> Mensuração educacional
            </div>
            <h1 className="text-[24px] font-semibold tracking-[-0.035em] text-[#101828]">Resultados de permanência</h1>
            <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-[#667085]">
              Acompanhe rematrícula, evasão e permanência por período letivo — e relacione os desfechos acadêmicos às intervenções sem presumir causalidade.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] font-medium text-[#344054] hover:bg-[#F9FAFB] disabled:opacity-60"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${query.isFetching ? "animate-spin" : ""}`} /> Atualizar
            </button>
            <Link href="/retencao/logs" className="inline-flex h-10 items-center gap-2 rounded-lg bg-[#232529] px-3.5 text-[12px] font-medium text-white hover:bg-[#101112]">
              Histórico de contatos <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </section>

        <section aria-label="Filtros de resultados" className="flex flex-wrap items-end gap-3 rounded-xl border border-[#E5E7EB] bg-white p-4">
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
        <p className="-mt-3 px-1 text-[10px] leading-relaxed text-[#667085]">
          O filtro de período letivo restringe os outcomes acadêmicos. Indicadores operacionais usam a janela de dias selecionada e são agrupados por mês-calendário.
        </p>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div role="tablist" aria-label="Tipo de resultados" className="inline-flex items-center gap-5 border-b border-[#E4E7EC] bg-white">
            <button
              id="tab-educational"
              role="tab"
              aria-selected={tab === "educational"}
              aria-controls="panel-educational"
              onClick={() => setTab("educational")}
              className={`inline-flex h-10 items-center gap-2 border-b-2 px-1 text-[12px] font-medium transition ${tab === "educational" ? "border-[#1C1D1F] text-[#1C1D1F]" : "border-transparent text-[#6F7988] hover:text-[#1C1D1F]"}`}
            >
              <GraduationCap className="h-3.5 w-3.5" /> Resultados educacionais
            </button>
            <button
              id="tab-operational"
              role="tab"
              aria-selected={tab === "operational"}
              aria-controls="panel-operational"
              onClick={() => setTab("operational")}
              className={`inline-flex h-10 items-center gap-2 border-b-2 px-1 text-[12px] font-medium transition ${tab === "operational" ? "border-[#1C1D1F] text-[#1C1D1F]" : "border-transparent text-[#6F7988] hover:text-[#1C1D1F]"}`}
            >
              <Activity className="h-3.5 w-3.5" /> Resultados operacionais
            </button>
          </div>
          <p className="text-[10px] text-[#667085]">
            {data?.generated_at ? `Dados atualizados ${dateTimeLabel(data.generated_at)}` : `Janela: ${days} dias`}
          </p>
        </div>

        {query.isLoading && <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[1, 2, 3, 4].map((n) => <Skeleton key={n} className="h-28 rounded-xl" />)}</div>}
        {query.isError && (
          <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-5 text-[12px] text-[#B42318]">
            <p className="font-semibold">Não foi possível carregar os resultados de permanência.</p>
            <p className="mt-1">Verifique a disponibilidade da API acadêmica e os dados do período selecionado.</p>
            <button type="button" onClick={() => void query.refetch()} className="mt-3 font-semibold underline">Tentar novamente</button>
          </div>
        )}
        {data && (tab === "educational" ? <EducationalResults data={data} /> : <OperationalResults data={data} />)}

        <div className="flex items-start gap-2 rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] p-3 text-[10px] leading-relaxed text-[#667085]">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#667085]" />
          <p>
            Outcomes acadêmicos dependem de importação explícita da instituição. Dados ausentes não são classificados como permanência ou evasão; envio, resposta e entrega são indicadores operacionais, não outcomes educacionais.
          </p>
        </div>
      </main>
    </>
  );
}
