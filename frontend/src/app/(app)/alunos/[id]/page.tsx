"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  CircleAlert,
  History,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
  RefreshCw,
  GraduationCap,
  Wallet,
  UserRound,
} from "@/components/ui/icons";
import { Header } from "@/components/layout/header";
import { RiskBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { RecordPage } from "@/components/record/record-page";
import { RecordProperties } from "@/components/record/record-properties";
import { RecordRelations } from "@/components/record/record-relations";
import { StudentRecordActivity } from "@/components/record/student-record-activity";
import { studentPropertyGroups, studentRelations, studentRecordIdentity } from "@/components/record/student-record-data";
import { getVisibleNavigation, hasNavigationPermission } from "@/components/layout/navigation";
import { cn, formatScore } from "@/lib/utils";
import { NativeAcademicPanel } from "@/components/students/native-academic-panel";

const STATUS_LABELS: Record<string, string> = {
  dry_run: "Simulado",
  sent: "Envio registrado",
  sending: "Enviando",
  submitted: "Submetido",
  queued: "Na fila",
  delivered: "Entregue",
  read: "Lido",
  unknown: "Status incerto",
  skipped: "Ignorado",
  failed: "Falhou",
  bounced: "Devolvido",
  rejected: "Rejeitado",
  planned: "Planejado",
  pending: "Pendente",
};

function businessText(raw?: string | null): string | null {
  if (!raw?.trim()) return null;
  const t = raw.trim();
  if (/\/api\/|GET\s+\/|POST\s+\/|SHAP sob demanda|students\/\{?id\}?\/risk/i.test(t)) {
    return null;
  }
  return t;
}

function formatDateTime(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function displayValue(
  value: string | number | null | undefined,
  suffix?: string
): string {
  if (value == null || value === "") return "Não informado";
  return suffix ? `${value}${suffix}` : String(value);
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="rounded-[10px] border border-[var(--color-border)] bg-white p-4">
      <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-muted)]">{label}</p>
      <p className="mt-2 text-[14px] font-semibold text-[var(--color-ink)]">{value}</p>
    </article>
  );
}

export default function StudentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [preview, setPreview] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<"overview" | "academic" | "finance" | "risk" | "activity" | "communication">("overview");

  function navigateToSection(section: "overview" | "academic" | "finance" | "risk" | "activity" | "communication", id: string) {
    setActiveSection(section);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  const [loadingPreview, setLoadingPreview] = useState(false);
  const queryClient = useQueryClient();
  const me = useQuery({queryKey:["org-me"],queryFn:api.me,retry:false,staleTime:60_000});
  const availableNavigation = getVisibleNavigation(me.data);
  const canRead = availableNavigation.some(g=>g.items.some(i=>i.href==="/alunos"));
  const canSensitive = hasNavigationPermission(me.data,"students.sensitive.view");
  const canEdit = hasNavigationPermission(me.data,"students.edit");
  const canPrepareContact = availableNavigation.some(g=>g.items.some(i=>i.href==="/disparos"));

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["student-risk", id],
    queryFn: () => api.studentRisk(id),
    enabled: Boolean(id) && canRead,
    staleTime:30_000,
  });

  const logs = useQuery({
    queryKey: ["student-logs", id],
    queryFn: () => api.retentionLogs({ student_id: id, limit: 20 }),
    enabled: Boolean(id) && canSensitive,
    retry: false,
  });

  const preferenceMutation = useMutation({
    mutationFn: (optOut: boolean) => api.updateCommunicationPreference(id, optOut),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["student-risk", id] });
      toast.success("Preferência de comunicação atualizada.");
    },
    onError: (mutationError) =>
      toast.error(
        mutationError instanceof Error
          ? mutationError.message
          : "Não foi possível atualizar a preferência."
      ),
  });

  async function loadPreview() {
    setLoadingPreview(true);
    try {
      const response = await api.retentionPreview(id);
      const msg =
        response && typeof response === "object" && "message" in response
          ? String((response as { message?: unknown }).message ?? "")
          : "";
      setPreview(msg || "Prévia gerada sem texto legível.");
    } catch (previewError) {
      toast.error(
        previewError instanceof Error
          ? previewError.message
          : "Não foi possível gerar a prévia."
      );
    } finally {
      setLoadingPreview(false);
    }
  }

  const summaryText =
    businessText(data?.shap_summary) ||
    businessText(data?.shap_top_factors?.summary) ||
    null;

  const factors = (data?.shap_top_factors?.top_3 || [])
    .map((factor) => {
      const label = businessText(factor.label) || businessText(factor.feature);
      if (!label) return null;
      if (factor.contribution === "aumenta_saida_modelo") return "Eleva a saída do estimador: " + label;
      if (factor.contribution === "reduz_saida_modelo") return "Reduz a saída do estimador: " + label;
      return label;
    })
    .filter(Boolean) as string[];

  const actions = (
    data?.recommended_actions ||
    data?.shap_top_factors?.recommended_actions ||
    []
  )
    .map((a) => businessText(a))
    .filter(Boolean) as string[];
  const scoreBreakdown = data?.shap_top_factors?.score_breakdown;
  const ruleAdjustments = Array.isArray(data?.shap_top_factors?.rule_adjustments)
    ? data.shap_top_factors.rule_adjustments
    : [];
  const explanationMetadata = data?.shap_top_factors?.explanation_metadata;

  return (
    <>
      <Header title="Ficha do aluno" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        {me.isLoading && <p role="status" className="px-5 py-8 text-[12px] text-[var(--color-slate-600)]">Verificando acesso…</p>}
        {me.isError || (!me.isLoading && !canRead) ? <p role="alert" className="px-5 py-8 text-[12px] text-[var(--color-red)]">O registro não está disponível para este perfil e workspace.</p> : null}
        {canRead && isLoading && (
          <div className="space-y-4">
            <Skeleton className="h-36 w-full rounded-xl" />
            <div className="grid gap-3 sm:grid-cols-3">
              <Skeleton className="h-24 rounded-xl" />
              <Skeleton className="h-24 rounded-xl" />
              <Skeleton className="h-24 rounded-xl" />
            </div>
            <Skeleton className="h-64 rounded-xl" />
          </div>
        )}

        {error && (
          <div role="alert" className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-8 text-center">
            <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-white text-[#B42318]">
              <CircleAlert className="h-5 w-5" />
            </span>
            <p className="mt-4 text-[15px] font-semibold text-[var(--color-ink)]">Não foi possível abrir esta ficha.</p>
            <p className="mt-1 text-[13px] text-[var(--color-slate-600)]">
              A consulta de risco falhou ou o aluno não está acessível nesta instituição.
            </p>
            <button type="button" onClick={() => void refetch()} className="mt-4 text-[13px] font-semibold text-[#B42318] underline underline-offset-4">
              Tentar novamente
            </button>
          </div>
        )}

        {data && canRead && (
            <RecordPage
              record={studentRecordIdentity(id,data)}
              backHref="/alunos"
              status={canSensitive ? <RiskBadge level={data.risk_level}/> : undefined}
              actions={[
                {id:"refresh",label:isFetching?"Atualizando…":"Atualizar",onClick:()=>void refetch(),disabled:isFetching},
                ...(canPrepareContact?[{id:"prepare",label:"Preparar contato",href:"/disparos?mode=individual&student="+encodeURIComponent(id)}]:[]),
              ]}
              aside={<div className="space-y-4">
                <RecordProperties compact groups={studentPropertyGroups(data,canSensitive)}/>
                <RecordRelations relations={studentRelations(data)}/>
              </div>}>
              <div className="space-y-5">

            <nav aria-label="Seções da ficha do aluno" className="flex flex-wrap items-center gap-6 border-b border-[var(--color-border)]">
              {([
                ["overview", "Visão geral", "student-overview"],
                ["academic", "Acadêmico", "student-academic"],
                ["finance", "Financeiro", "student-finance"],
                ["risk", "Análise de risco", "risk-analysis"],
                ["activity", "Atividade", "student-activity"],
                ["communication", "Comunicação", "student-communication"],
              ] as const).filter(([section])=>canSensitive||section==="overview").map(([section, label, id]) => (
                <button
                  key={section}
                  type="button"
                  aria-current={activeSection === section ? "page" : undefined}
                  onClick={() => navigateToSection(section, id)}
                  className={`inline-flex h-10 items-center border-b-2 text-[12px] font-medium transition ${activeSection === section ? "border-[#1C1D1F] text-[#1C1D1F]" : "border-transparent text-[#6F7988] hover:border-[var(--color-border)] hover:text-[#1C1D1F]"}`}
                >
                  {label}
                </button>
              ))}
            </nav>

            <section id="student-overview" className="scroll-mt-24" aria-label="Resumo acadêmico e financeiro">
              <h2 className="mb-3 text-[15px] font-semibold tracking-[-0.02em] text-[var(--color-ink)]">Situação acadêmica e financeira</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <InfoCard label="Curso" value={displayValue(data.curso)} />
                <InfoCard label="Semestre" value={data.semestre != null ? `Semestre ${data.semestre}` : "Não informado"} />
                {canSensitive && <><InfoCard label="Atraso financeiro" value={data.dias_atraso_boleto != null ? `${data.dias_atraso_boleto} dias` : "Não informado"} />
                <InfoCard label="Status financeiro" value={displayValue(data.status_financeiro)} /></>}
              </div>
            </section>

            <section id="student-academic" className="scroll-mt-24 rounded-[10px] border border-[var(--color-border)] bg-white p-5" aria-label="Dados acadêmicos">
              <div className="flex items-center gap-2"><GraduationCap className="h-4 w-4 text-[var(--color-slate-600)]" /><h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Acadêmico</h2></div>
              <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Dados recebidos da instituição. Informações não integradas permanecem indisponíveis.</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <InfoCard label="Programa / curso" value={displayValue(data.curso)} />
                <InfoCard label="Campus" value={displayValue(data.campus)} />
                <InfoCard label="Semestre" value={data.semestre != null ? String(data.semestre) : "Não informado"} />
                <InfoCard label="Situação acadêmica" value={displayValue(data.status_aluno)} />
                <InfoCard label="Turma" value={displayValue(data.turma)} />
                <InfoCard label="Forma de ingresso" value={displayValue(data.forma_ingresso)} />
                <InfoCard label="Matrícula" value={displayValue(data.matricula)} />
                {canSensitive && <InfoCard label="Engajamento" value={data.engagement_score != null ? String(data.engagement_score) : "Não informado"} />}
              </div>
              {canSensitive && <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-[var(--color-border)] p-4"><p className="text-[13px] font-semibold">Frequência e presença</p><p className="mt-2 text-[20px] font-semibold tabular-nums text-[var(--color-ink)]">{data.presenca_percentual != null ? `${data.presenca_percentual}%` : "Não informado"}</p><p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Presença agregada informada pela instituição; histórico por disciplina ainda não disponível.</p></div>
                <div className="rounded-lg border border-[var(--color-border)] p-4"><p className="text-[13px] font-semibold">Notas e avaliações</p><p className="mt-2 text-[20px] font-semibold tabular-nums text-[var(--color-ink)]">{data.nota_media != null ? String(data.nota_media) : "Não informado"}</p><p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Média informada pela instituição · {data.reprovacoes != null ? `${data.reprovacoes} reprovações` : "reprovações não informadas"}. Histórico por disciplina ainda não disponível.</p></div>
              </div>}
            </section>

            {canSensitive && me.data?.available_features?.academic_catalog === true && <NativeAcademicPanel studentId={id} />}

            {canSensitive && <section id="student-finance" className="scroll-mt-24 rounded-[10px] border border-[var(--color-border)] bg-white p-5" aria-label="Dados financeiros">
              <div className="flex items-center gap-2"><Wallet className="h-4 w-4 text-[var(--color-slate-600)]" /><h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Financeiro</h2></div>
              <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Resumo financeiro informado pela fonte de dados, não um extrato transacional ou confirmação de pagamento.</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <InfoCard label="Saldo informado" value={data.saldo_devedor != null && Number.isFinite(data.saldo_devedor) ? new Intl.NumberFormat("pt-BR", {style:"currency", currency:"BRL"}).format(data.saldo_devedor) : "Não informado"} />
                <InfoCard label="Dias em atraso" value={data.dias_atraso_boleto != null ? String(data.dias_atraso_boleto) : "Não informado"} />
                <InfoCard label="Status financeiro" value={displayValue(data.status_financeiro)} />
              </div>
              <div className="mt-4 overflow-hidden rounded-lg border border-[var(--color-border)]">
                <div className="grid grid-cols-3 border-b border-[var(--color-border)] bg-[#F9FAFB] px-4 py-3 text-[11px] font-medium text-[var(--color-slate-600)]"><span>Obrigação / parcela</span><span>Vencimento</span><span>Pagamento</span></div>
                <p className="px-4 py-6 text-center text-[12px] text-[var(--color-slate-600)]">Faturas, parcelas e pagamentos ainda não estão disponíveis como registros verificados nesta ficha.</p>
              </div>
              <div className="mt-3 rounded-lg border border-[var(--color-border)] px-4 py-4"><p className="text-[13px] font-semibold text-[var(--color-ink)]">Acordos e negociações</p><p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Sem integração homologada para consultar acordos vinculados a este aluno.</p></div>
            </section>}

            {canSensitive && <section className="rounded-[10px] border border-[var(--color-border)] bg-white p-5" aria-label="Atributos adicionais">
              <div className="flex items-center gap-2"><UserRound className="h-4 w-4 text-[var(--color-slate-600)]" /><h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Campos personalizados</h2></div>
              {Object.entries(data.behavior_properties?.custom_properties ?? {}).length > 0 ? (
                <dl className="mt-4 grid gap-3 sm:grid-cols-2">
                  {Object.entries(data.behavior_properties?.custom_properties ?? {}).map(([key, value]) => (
                    <div key={key} className="rounded-lg border border-[var(--color-border)] px-3 py-2"><dt className="text-[11px] text-[var(--color-slate-600)]">{key.replaceAll("_", " ")}</dt><dd className="mt-1 break-words text-[13px] font-medium text-[var(--color-ink)]">{value == null ? "Não informado" : String(value)}</dd></div>
                  ))}
                </dl>
              ) : <p className="mt-3 text-[12px] text-[var(--color-slate-600)]">Nenhum campo personalizado disponível na fonte atual.</p>}
            </section>}

            {canSensitive && <section id="student-activity" className="scroll-mt-24" aria-label="Atividade do aluno">
              <StudentRecordActivity studentId={id} canView={canSensitive} />
            </section>}

            {canSensitive && <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,0.8fr)]">
              <div className="space-y-4">
                <section id="risk-analysis" className="scroll-mt-24 rounded-xl border border-[var(--color-border)] bg-white p-5">
                  <h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Análise de risco</h2>
                  <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">O sinal indica a direção da saída bruta do estimador. Não representa pontos adicionados ao score final nem prova causalidade.</p>
                  {explanationMetadata?.available && (
                    <p className="mt-2 text-[11px] text-[var(--color-muted)]">
                      SHAP · modelo {explanationMetadata.model_scope || "não informado"} · versão {explanationMetadata.model_version || "não informada"}
                    </p>
                  )}
                  {summaryText ? (
                    <p className="mt-4 text-[13px] leading-relaxed text-[#344054]">{summaryText}</p>
                  ) : (
                    <p className="mt-4 rounded-lg bg-[var(--color-panel)] px-3 py-3 text-[13px] text-[var(--color-slate-600)]">Explicação detalhada indisponível para este aluno.</p>
                  )}
                  {factors.length > 0 ? (
                    <ul className="mt-4 space-y-2">
                      {factors.map((factor, index) => (
                        <li key={`${factor}-${index}`} className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] px-3.5 py-3">
                          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-[var(--color-blue-tint)] text-[11px] font-semibold text-[var(--color-blue)]">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <span className="text-[13px] font-medium text-[var(--color-ink)]">{factor}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    !summaryText && <p className="mt-3 text-[12px] text-[var(--color-muted)]">Nenhum fator de negócio disponível nesta avaliação.</p>
                  )}
                </section>

                {scoreBreakdown && (
                  <section className="rounded-xl border border-[var(--color-border)] bg-white p-5">
                    <h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Composição do score</h2>
                    <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">
                      Componentes apresentados separadamente. Os pontos das regras e os ajustes dinâmicos não são contribuições SHAP.
                    </p>
                    <div className="mt-4 grid gap-2 sm:grid-cols-2">
                      <InfoCard label="Score do modelo" value={displayValue(scoreBreakdown.model_score)} />
                      <InfoCard label="Regras aplicadas" value={scoreBreakdown.business_rule_adjustment_applied != null ? `${Number(scoreBreakdown.business_rule_adjustment_applied) > 0 ? "+" : ""}${scoreBreakdown.business_rule_adjustment_applied} pts` : "Não informado"} />
                      <InfoCard label="Ajuste dinâmico" value={scoreBreakdown.dynamic_adjustment_applied != null ? `${Number(scoreBreakdown.dynamic_adjustment_applied) > 0 ? "+" : ""}${scoreBreakdown.dynamic_adjustment_applied} pts` : "Não informado"} />
                      <InfoCard label="Score final" value={displayValue(scoreBreakdown.final_score)} />
                    </div>
                  </section>
                )}

                {ruleAdjustments.length > 0 && (
                  <section className="rounded-xl border border-[var(--color-border)] bg-white p-5">
                    <h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Regras acionadas</h2>
                    <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">
                      Cada item mostra a condição observada e o ajuste solicitado pela regra.
                    </p>
                    <ul className="mt-4 space-y-2">
                      {ruleAdjustments.map((rule, index) => {
                        const evidence = rule.evidence && typeof rule.evidence === "object"
                          ? rule.evidence as Record<string, unknown>
                          : {};
                        const observed = evidence.observed;
                        const threshold = evidence.threshold;
                        const field = typeof evidence.field === "string" ? evidence.field : null;
                        const recommendation = businessText(typeof rule.recommendation === "string" ? rule.recommendation : null);
                        return (
                          <li key={String(rule.flag || index)} className="rounded-lg border border-[var(--color-border)] px-3.5 py-3">
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <p className="text-[13px] font-semibold text-[var(--color-ink)]">{businessText(String(rule.description || rule.flag || "Regra aplicada"))}</p>
                              <span className="shrink-0 rounded-md bg-[#FFF7ED] px-2 py-1 text-[11px] font-semibold tabular-nums text-[#9A3412]">
                                +{displayValue(typeof rule.delta_points === "number" ? rule.delta_points : null)} pts
                              </span>
                            </div>
                            {field && observed != null && (
                              <p className="mt-1.5 text-[12px] text-[var(--color-slate-600)]">
                                Evidência: {field} = {String(observed)}
                                {threshold != null ? ` · limite ${String(evidence.operator || "")} ${String(threshold)}` : ""}
                              </p>
                            )}
                            {recommendation && <p className="mt-2 text-[12px] leading-relaxed text-[#344054]">Próxima ação sugerida: {recommendation}</p>}
                          </li>
                        );
                      })}
                    </ul>
                  </section>
                )}

                {explanationMetadata?.status === "unavailable" && (
                  <p className="rounded-lg border border-[#FDE68A] bg-[#FFFBEB] px-3 py-2 text-[12px] text-[#92400E]">
                    O score foi calculado, mas a explicação SHAP não ficou disponível nesta avaliação.
                  </p>
                )}

                <section className="rounded-xl border border-[var(--color-border)] bg-white p-5">
                  <h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Sugestões operacionais</h2>
                  <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Sugestões retornadas pelo sistema — não são decisões automáticas nem comprovação de resultado.</p>
                  {actions.length === 0 ? (
                    <p className="mt-4 rounded-lg bg-[var(--color-panel)] px-3 py-3 text-[13px] text-[var(--color-slate-600)]">Nenhuma sugestão operacional disponível para este aluno.</p>
                  ) : (
                    <ol className="mt-4 space-y-2">
                      {actions.map((action, index) => (
                        <li key={`${index}-${action}`} className="flex items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3.5 py-3 text-[13px] leading-relaxed text-[#344054]">
                          <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white text-[10px] font-semibold text-[var(--color-blue)] ring-1 ring-[var(--color-border)]">{index + 1}</span>
                          {action}
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
              </div>

              <div className="space-y-4">
                <section id="student-communication" className={cn("scroll-mt-24 rounded-xl border p-5", data.communication_opt_out ? "border-[#FECDCA] bg-[#FEF3F2]" : "border-[var(--color-border)] bg-white")}>
                  <div className="flex items-start gap-3">
                    <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-lg", data.communication_opt_out ? "bg-white text-[#B42318]" : "bg-[var(--color-blue-tint)] text-[var(--color-blue)]")}>
                      <ShieldCheck className="h-4 w-4" />
                    </span>
                    <div>
                      <h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Comunicação</h2>
                      <p className="mt-1 text-[12px] leading-relaxed text-[var(--color-slate-600)]">
                        {data.communication_opt_out ? "Opt-out ativo — não contatar automaticamente." : "Sem opt-out global registrado. A autorização por canal e finalidade deve ser verificada antes de qualquer contato."}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={preferenceMutation.isPending || !canEdit || typeof data.communication_opt_out !== "boolean"}
                    onClick={() => preferenceMutation.mutate(!data.communication_opt_out)}
                    className={cn(
                      "mt-4 inline-flex h-10 w-full items-center justify-center rounded-lg text-[13px] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-blue)] disabled:opacity-60",
                      data.communication_opt_out ? "bg-[var(--color-blue)] text-white hover:bg-[#1F5DD1]" : "border border-[var(--color-border)] bg-white text-[var(--color-ink)] hover:bg-[var(--color-panel)]"
                    )}
                  >
                    {preferenceMutation.isPending ? "Salvando…" : data.communication_opt_out ? "Revogar opt-out" : "Registrar opt-out"}
                  </button>
                </section>

                <section className="rounded-xl border border-[var(--color-border)] bg-white p-5">
                  <div className="flex items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-blue-tint)] text-[var(--color-blue)]">
                      <MessageSquareText className="h-4 w-4" />
                    </span>
                    <div>
                      <h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Preparar contato</h2>
                      <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Gera a prévia da mensagem sem enviar.</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadPreview()}
                    disabled={loadingPreview}
                    className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-[var(--color-blue)] text-[13px] font-semibold text-white transition hover:bg-[#1F5DD1] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {loadingPreview ? "Preparando…" : "Gerar prévia da mensagem"}
                  </button>
                  {preview && (
                    <div className="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
                      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--color-muted)]">Prévia</p>
                      <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-[#344054]">{preview}</p>
                    </div>
                  )}
                </section>

                <section className="rounded-xl border border-[var(--color-border)] bg-white p-5">
                  <div className="flex items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-panel)] text-[var(--color-slate-600)]">
                      <History className="h-4 w-4" />
                    </span>
                    <div>
                      <h2 className="text-[15px] font-semibold text-[var(--color-ink)]">Contatos (retenção)</h2>
                      <p className="mt-1 text-[12px] text-[var(--color-slate-600)]">Logs de retenção. Status de envio não confirma permanência.</p>
                    </div>
                  </div>
                  {logs.isLoading && (
                    <div className="mt-4 space-y-2">
                      <Skeleton className="h-14 w-full rounded-lg" />
                      <Skeleton className="h-14 w-full rounded-lg" />
                    </div>
                  )}
                  {logs.isError && <p className="mt-4 text-[12px] text-[var(--color-slate-600)]">Histórico de contatos indisponível no momento.</p>}
                  {!logs.isLoading && !logs.isError && (logs.data?.logs?.length ?? 0) === 0 && (
                    <p className="mt-4 rounded-lg bg-[var(--color-panel)] px-3 py-3 text-[13px] text-[var(--color-slate-600)]">Nenhum contato de retenção registrado para este aluno.</p>
                  )}
                  {!logs.isLoading && !logs.isError && (logs.data?.logs?.length ?? 0) > 0 && (
                    <ul className="mt-4 space-y-2">
                      {logs.data!.logs.map((log) => {
                        const visibleStatus = log.status === "dry_run" ? "dry_run" : log.delivery_status || log.status;
                        const label = STATUS_LABELS[visibleStatus] || visibleStatus.replaceAll("_", " ");
                        return (
                          <li key={log.id} className="rounded-lg border border-[var(--color-border)] px-3 py-2.5">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-[12px] font-semibold capitalize text-[var(--color-ink)]">{log.channel || "Canal não informado"}</span>
                              <span className="rounded-full bg-[var(--color-panel)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-slate-600)]">{label}</span>
                            </div>
                            <p className="mt-1 text-[11px] text-[var(--color-muted)]">
                              {formatDateTime(log.created_at) || "Data indisponível"}
                              {log.campaign_id ? ` · Campanha ${log.campaign_id}` : ""}
                            </p>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </section>
              </div>
            </div>}
              </div>
            </RecordPage>
        )}
      </main>
    </>
  );
}
