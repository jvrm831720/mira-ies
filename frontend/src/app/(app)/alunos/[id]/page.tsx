"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  CircleAlert,
  History,
  Mail,
  MessageSquareText,
  Phone,
  ShieldCheck,
  Sparkles,
  RefreshCw,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { RiskBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn, formatScore } from "@/lib/utils";
import { StudentWorkTimeline } from "@/components/students/student-work-timeline";

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
    <article className="rounded-xl border border-[#E5E7EB] bg-white p-4">
      <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[#98A2B3]">{label}</p>
      <p className="mt-2 text-[14px] font-semibold text-[#111827]">{value}</p>
    </article>
  );
}

export default function StudentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [preview, setPreview] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["student-risk", id],
    queryFn: () => api.studentRisk(id),
    enabled: Boolean(id),
  });

  const logs = useQuery({
    queryKey: ["student-logs", id],
    queryFn: () => api.retentionLogs({ student_id: id, limit: 20 }),
    enabled: Boolean(id),
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

  const scoreAvailable =
    typeof data?.risk_score === "number" && Number.isFinite(data.risk_score);
  const scoreBarWidth = scoreAvailable
    ? Math.max(0, Math.min(100, data!.risk_score as number))
    : null;
  const scoreBarColor =
    data?.risk_level === "critico"
      ? "#F04438"
      : data?.risk_level === "medio"
        ? "#FDB022"
        : data?.risk_level === "baixo"
          ? "#12B76A"
          : "#98A2B3";

  const summaryText =
    businessText(data?.shap_summary) ||
    businessText(data?.shap_top_factors?.summary) ||
    null;

  const factors = (data?.shap_top_factors?.top_3 || [])
    .map((f) => businessText(f.label) || businessText(f.feature))
    .filter(Boolean) as string[];

  const actions = (
    data?.recommended_actions ||
    data?.shap_top_factors?.recommended_actions ||
    []
  )
    .map((a) => businessText(a))
    .filter(Boolean) as string[];

  return (
    <>
      <Header title="Ficha do aluno" compact />
      <main className="mira-page mx-auto w-full max-w-[1440px] space-y-5 px-4 pb-10 pt-5 md:px-8 md:pt-6 xl:px-10">
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/alunos"
            className="inline-flex items-center gap-2 rounded-lg text-[13px] font-semibold text-[#667085] transition hover:text-[#2563EB] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar para alunos
          </Link>
          {data && (
            <button
              type="button"
              onClick={() => void refetch()}
              disabled={isFetching}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3 text-[12px] font-medium text-[#111827] transition hover:bg-[#F8FAFC] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
              Atualizar
            </button>
          )}
        </div>

        {isLoading && (
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
            <p className="mt-4 text-[15px] font-semibold text-[#111827]">Não foi possível abrir esta ficha.</p>
            <p className="mt-1 text-[13px] text-[#667085]">
              A consulta de risco falhou ou o aluno não está acessível nesta instituição.
            </p>
            <button type="button" onClick={() => void refetch()} className="mt-4 text-[13px] font-semibold text-[#B42318] underline underline-offset-4">
              Tentar novamente
            </button>
          </div>
        )}

        {data && (
          <>
            <section className="rounded-xl border border-[#E5E7EB] bg-white p-5 sm:p-6">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[#98A2B3]">Identificação</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2.5">
                    <h1 className="text-[22px] font-semibold tracking-[-0.03em] text-[#111827] sm:text-[24px]">
                      {data.nome || "Nome não informado"}
                    </h1>
                    <RiskBadge level={data.risk_level} />
                  </div>
                  <p className="mt-1.5 text-[13px] text-[#667085]">
                    Matrícula {data.matricula || "—"}
                    {data.curso ? ` · ${data.curso}` : ""}
                    {data.campus ? ` · ${data.campus}` : ""}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[13px] text-[#344054]">
                    {data.telefone ? (
                      <span className="inline-flex items-center gap-2">
                        <Phone className="h-3.5 w-3.5 text-[#667085]" />
                        {data.telefone}
                      </span>
                    ) : null}
                    {data.email ? (
                      <span className="inline-flex items-center gap-2">
                        <Mail className="h-3.5 w-3.5 text-[#667085]" />
                        {data.email}
                      </span>
                    ) : null}
                    {!data.telefone && !data.email && (
                      <span className="text-[#98A2B3]">Sem telefone ou e-mail cadastrado</span>
                    )}
                  </div>
                </div>
                <div className="w-full shrink-0 rounded-xl border border-[#E5E7EB] bg-[#F8FAFC] p-4 sm:w-[240px]">
                  <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[#98A2B3]">Score de risco</p>
                  {scoreAvailable ? (
                    <>
                      <div className="mt-2 flex items-baseline gap-1">
                        <span className="text-[32px] font-semibold tracking-[-0.04em] tabular-nums text-[#111827]">
                          {formatScore(data.risk_score)}
                        </span>
                        <span className="text-[12px] text-[#98A2B3]">/ 100</span>
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white">
                        <div className="h-full rounded-full transition-all" style={{ width: `${scoreBarWidth}%`, backgroundColor: scoreBarColor }} />
                      </div>
                    </>
                  ) : (
                    <>
                      <p className="mt-3 text-[20px] font-semibold text-[#667085]">Sem score</p>
                      <p className="mt-1 text-[11px] leading-relaxed text-[#98A2B3]">Ausência de score não significa baixo risco.</p>
                    </>
                  )}
                </div>
              </div>
            </section>

            <section aria-label="Resumo acadêmico e financeiro">
              <h2 className="mb-3 text-[15px] font-semibold tracking-[-0.02em] text-[#111827]">Situação acadêmica e financeira</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <InfoCard label="Curso" value={displayValue(data.curso)} />
                <InfoCard label="Semestre" value={data.semestre != null ? `Semestre ${data.semestre}` : "Não informado"} />
                <InfoCard label="Atraso financeiro" value={data.dias_atraso_boleto != null ? `${data.dias_atraso_boleto} dias` : "Não informado"} />
                <InfoCard label="Status financeiro" value={displayValue(data.status_financeiro)} />
              </div>
            </section>

            <StudentWorkTimeline studentId={id} />

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,0.8fr)]">
              <div className="space-y-4">
                <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
                  <h2 className="text-[15px] font-semibold text-[#111827]">Análise de risco</h2>
                  <p className="mt-1 text-[12px] text-[#667085]">Fatores retornados pela avaliação atual. Correlação não implica causalidade.</p>
                  {summaryText ? (
                    <p className="mt-4 text-[13px] leading-relaxed text-[#344054]">{summaryText}</p>
                  ) : (
                    <p className="mt-4 rounded-lg bg-[#F8FAFC] px-3 py-3 text-[13px] text-[#667085]">Explicação detalhada indisponível para este aluno.</p>
                  )}
                  {factors.length > 0 ? (
                    <ul className="mt-4 space-y-2">
                      {factors.map((factor, index) => (
                        <li key={`${factor}-${index}`} className="flex items-center gap-3 rounded-lg border border-[#E5E7EB] px-3.5 py-3">
                          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-[#EFF6FF] text-[11px] font-semibold text-[#2563EB]">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <span className="text-[13px] font-medium text-[#111827]">{factor}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    !summaryText && <p className="mt-3 text-[12px] text-[#98A2B3]">Nenhum fator de negócio disponível nesta avaliação.</p>
                  )}
                </section>

                <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
                  <h2 className="text-[15px] font-semibold text-[#111827]">Sugestões operacionais</h2>
                  <p className="mt-1 text-[12px] text-[#667085]">Sugestões retornadas pelo sistema — não são decisões automáticas nem comprovação de resultado.</p>
                  {actions.length === 0 ? (
                    <p className="mt-4 rounded-lg bg-[#F8FAFC] px-3 py-3 text-[13px] text-[#667085]">Nenhuma sugestão operacional disponível para este aluno.</p>
                  ) : (
                    <ol className="mt-4 space-y-2">
                      {actions.map((action, index) => (
                        <li key={`${index}-${action}`} className="flex items-start gap-3 rounded-lg border border-[#E5E7EB] bg-[#F8FAFC] px-3.5 py-3 text-[13px] leading-relaxed text-[#344054]">
                          <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white text-[10px] font-semibold text-[#2563EB] ring-1 ring-[#E5E7EB]">{index + 1}</span>
                          {action}
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
              </div>

              <div className="space-y-4">
                <section className={cn("rounded-xl border p-5", data.communication_opt_out ? "border-[#FECDCA] bg-[#FEF3F2]" : "border-[#E5E7EB] bg-white")}>
                  <div className="flex items-start gap-3">
                    <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-lg", data.communication_opt_out ? "bg-white text-[#B42318]" : "bg-[#EFF6FF] text-[#2563EB]")}>
                      <ShieldCheck className="h-4 w-4" />
                    </span>
                    <div>
                      <h2 className="text-[15px] font-semibold text-[#111827]">Comunicação</h2>
                      <p className="mt-1 text-[12px] leading-relaxed text-[#667085]">
                        {data.communication_opt_out ? "Opt-out ativo — não contatar automaticamente." : "Contato autorizado, sujeito a regras de anti-spam."}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={preferenceMutation.isPending}
                    onClick={() => preferenceMutation.mutate(!data.communication_opt_out)}
                    className={cn(
                      "mt-4 inline-flex h-10 w-full items-center justify-center rounded-lg text-[13px] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] disabled:opacity-60",
                      data.communication_opt_out ? "bg-[#2563EB] text-white hover:bg-[#1D4ED8]" : "border border-[#E5E7EB] bg-white text-[#111827] hover:bg-[#F8FAFC]"
                    )}
                  >
                    {preferenceMutation.isPending ? "Salvando…" : data.communication_opt_out ? "Revogar opt-out" : "Registrar opt-out"}
                  </button>
                </section>

                <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
                  <div className="flex items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#EFF6FF] text-[#2563EB]">
                      <MessageSquareText className="h-4 w-4" />
                    </span>
                    <div>
                      <h2 className="text-[15px] font-semibold text-[#111827]">Preparar contato</h2>
                      <p className="mt-1 text-[12px] text-[#667085]">Gera a prévia da mensagem sem enviar.</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadPreview()}
                    disabled={loadingPreview}
                    className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-[#2563EB] text-[13px] font-semibold text-white transition hover:bg-[#1D4ED8] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {loadingPreview ? "Preparando…" : "Gerar prévia da mensagem"}
                  </button>
                  {preview && (
                    <div className="mt-4 rounded-lg border border-[#E5E7EB] bg-[#F8FAFC] p-4">
                      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#98A2B3]">Prévia</p>
                      <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-[#344054]">{preview}</p>
                    </div>
                  )}
                </section>

                <section className="rounded-xl border border-[#E5E7EB] bg-white p-5">
                  <div className="flex items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#F8FAFC] text-[#667085]">
                      <History className="h-4 w-4" />
                    </span>
                    <div>
                      <h2 className="text-[15px] font-semibold text-[#111827]">Contatos (retenção)</h2>
                      <p className="mt-1 text-[12px] text-[#667085]">Logs de retenção. Status de envio não confirma permanência.</p>
                    </div>
                  </div>
                  {logs.isLoading && (
                    <div className="mt-4 space-y-2">
                      <Skeleton className="h-14 w-full rounded-lg" />
                      <Skeleton className="h-14 w-full rounded-lg" />
                    </div>
                  )}
                  {logs.isError && <p className="mt-4 text-[12px] text-[#667085]">Histórico de contatos indisponível no momento.</p>}
                  {!logs.isLoading && !logs.isError && (logs.data?.logs?.length ?? 0) === 0 && (
                    <p className="mt-4 rounded-lg bg-[#F8FAFC] px-3 py-3 text-[13px] text-[#667085]">Nenhum contato de retenção registrado para este aluno.</p>
                  )}
                  {!logs.isLoading && !logs.isError && (logs.data?.logs?.length ?? 0) > 0 && (
                    <ul className="mt-4 space-y-2">
                      {logs.data!.logs.map((log) => {
                        const visibleStatus = log.status === "dry_run" ? "dry_run" : log.delivery_status || log.status;
                        const label = STATUS_LABELS[visibleStatus] || visibleStatus.replaceAll("_", " ");
                        return (
                          <li key={log.id} className="rounded-lg border border-[#E5E7EB] px-3 py-2.5">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-[12px] font-semibold capitalize text-[#111827]">{log.channel || "Canal não informado"}</span>
                              <span className="rounded-full bg-[#F8FAFC] px-2 py-0.5 text-[10px] font-medium text-[#667085]">{label}</span>
                            </div>
                            <p className="mt-1 text-[11px] text-[#98A2B3]">
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
            </div>
          </>
        )}
      </main>
    </>
  );
}
