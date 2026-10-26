"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  Check,
  CircleAlert,
  History,
  Mail,
  MessageSquareText,
  Phone,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatScore } from "@/lib/utils";

export default function StudentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [preview, setPreview] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["student-risk", id],
    queryFn: () => api.studentRisk(id),
    enabled: Boolean(id),
  });
  const logs = useQuery({
    queryKey: ["student-logs", id],
    queryFn: () => api.retentionLogs({ student_id: id, limit: 20 }),
    enabled: Boolean(id),
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
      setPreview(String(response.message || JSON.stringify(response, null, 2)));
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

  const actions = data?.recommended_actions || data?.shap_top_factors?.recommended_actions || [];
  const factors = data?.shap_top_factors?.top_3 || [];
  const score =
    typeof data?.risk_score === "number" ? Math.max(0, Math.min(100, data.risk_score)) : 0;
  const scoreColor =
    data?.risk_level === "critico"
      ? "var(--brand-coral)"
      : data?.risk_level === "medio"
        ? "var(--brand-indigo)"
        : "var(--brand-blue)";

  return (
    <>
      <Header
        title="Ficha do aluno"
        subtitle={
          data
            ? `${data.matricula}${data.curso ? ` · ${data.curso}` : ""}`
            : "Score, fatores e próximos passos"
        }
      />
      <main className="mx-auto w-full max-w-[1400px] space-y-5 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        <Link
          href="/alunos"
          className="inline-flex items-center gap-2 rounded-lg text-xs font-semibold text-muted-foreground transition hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" /> Voltar para alunos
        </Link>
        {isLoading && (
          <div className="grid gap-4 lg:grid-cols-3">
            <Skeleton className="h-[420px] rounded-2xl" />
            <Skeleton className="h-[300px] rounded-2xl lg:col-span-2" />
          </div>
        )}
        {error && (
          <Card>
            <CardContent className="flex flex-col items-center p-10 text-center">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-[#fff0ed] text-[#b84336]">
                <CircleAlert className="h-5 w-5" />
              </span>
              <p className="mt-4 text-sm font-semibold">Não foi possível abrir esta ficha.</p>
              <Button variant="outline" size="sm" className="mt-4" onClick={() => void refetch()}>
                Tentar novamente
              </Button>
            </CardContent>
          </Card>
        )}
        {data && (
          <>
            <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
              <Card className="overflow-hidden border-0 bg-[var(--brand-midnight)] text-white shadow-[0_12px_36px_rgba(16,13,80,0.13)]">
                <div className="h-1 bg-[var(--brand-coral)]" />
                <CardContent className="grid gap-6 p-5 sm:p-7 md:grid-cols-[minmax(0,1fr)_230px] md:items-center">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/50">
                      Perfil do aluno
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-3">
                      <h2 className="text-2xl font-semibold tracking-[-0.04em]">
                        {data.nome || "Sem nome"}
                      </h2>
                      <RiskBadge level={data.risk_level} />
                    </div>
                    <p className="mt-2 text-xs text-white/60">
                      Matrícula {data.matricula || "—"}
                      {data.curso ? ` · ${data.curso}` : ""}
                    </p>
                    <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-xs text-white/70">
                      {data.telefone && (
                        <span className="inline-flex items-center gap-2">
                          <Phone className="h-3.5 w-3.5 text-[var(--brand-coral)]" />
                          {data.telefone}
                        </span>
                      )}
                      {data.email && (
                        <span className="inline-flex items-center gap-2">
                          <Mail className="h-3.5 w-3.5 text-[var(--brand-coral)]" />
                          {data.email}
                        </span>
                      )}
                      {!data.telefone && !data.email && (
                        <span className="text-white/55">Sem telefone ou e-mail cadastrado</span>
                      )}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-4">
                    <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-white/55">
                      Score de risco
                    </p>
                    <div className="mt-2 flex items-baseline gap-1">
                      <span className="text-4xl font-semibold tracking-[-0.06em] tabular-nums">
                        {formatScore(data.risk_score)}
                      </span>
                      <span className="text-xs text-white/45">/ 100</span>
                    </div>
                    <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${score}%`, backgroundColor: scoreColor }}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card
                className={
                  data.communication_opt_out
                    ? "border-[#f0c4bd] bg-[#fff8f6]"
                    : "border-[#cfe8dc] bg-[#f7fcf9]"
                }
              >
                <CardHeader className="pb-3">
                  <div className="mb-1 grid h-8 w-8 place-items-center rounded-xl bg-white text-primary shadow-sm">
                    <ShieldCheck className="h-4 w-4" />
                  </div>
                  <CardTitle className="text-sm">Comunicação e LGPD</CardTitle>
                  <CardDescription>
                    Controle explícito de opt-out na régua de retenção.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div
                    className={`rounded-xl p-3 text-xs leading-relaxed ${
                      data.communication_opt_out
                        ? "bg-[#fff0ed] text-[#963b32]"
                        : "bg-[#e9f7f0] text-[#286747]"
                    }`}
                  >
                    <p className="font-semibold">
                      {data.communication_opt_out
                        ? "Opt-out ativo — não contatar"
                        : "Contato autorizado pela instituição"}
                    </p>
                    <p className="mt-1 opacity-85">
                      {data.communication_opt_out
                        ? "Nenhuma mensagem automática será enviada até revogar o opt-out."
                        : "Este aluno pode entrar na régua, respeitando anti-spam."}
                    </p>
                  </div>
                  <Button
                    variant={data.communication_opt_out ? "default" : "outline"}
                    size="sm"
                    className="w-full"
                    disabled={preferenceMutation.isPending}
                    onClick={() => preferenceMutation.mutate(!data.communication_opt_out)}
                  >
                    {preferenceMutation.isPending
                      ? "Salvando…"
                      : data.communication_opt_out
                        ? "Revogar opt-out"
                        : "Registrar opt-out"}
                  </Button>
                </CardContent>
              </Card>
            </section>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Dados acadêmicos e financeiros</CardTitle>
                <CardDescription>
                  Informações importadas da base institucional, separadas dos indicadores comportamentais.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-xl border border-border/80 p-3">
                    <dt className="text-xs text-muted-foreground">Curso</dt>
                    <dd className="mt-1 text-sm font-semibold">{data.curso || "Não informado"}</dd>
                  </div>
                  <div className="rounded-xl border border-border/80 p-3">
                    <dt className="text-xs text-muted-foreground">Semestre</dt>
                    <dd className="mt-1 text-sm font-semibold">
                      {data.semestre != null ? `Semestre ${data.semestre}` : "Não informado"}
                    </dd>
                  </div>
                  <div className="rounded-xl border border-border/80 p-3">
                    <dt className="text-xs text-muted-foreground">Atraso financeiro</dt>
                    <dd className="mt-1 text-sm font-semibold">
                      {data.dias_atraso_boleto != null ? `${data.dias_atraso_boleto} dias` : "Não informado"}
                    </dd>
                  </div>
                </dl>
              </CardContent>
            </Card>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">O que pode estar influenciando este sinal?</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm leading-7 text-foreground/85">
                      {data.shap_summary ||
                        data.shap_top_factors?.summary ||
                        "Fatores detalhados não estão disponíveis para este aluno."}
                    </p>
                    {factors.length > 0 && (
                      <ul className="space-y-2">
                        {factors.map((factor, index) => (
                          <li
                            key={`${factor.feature || factor.label || "factor"}-${index}`}
                            className="flex items-center gap-3 rounded-xl border border-border/80 px-3.5 py-3"
                          >
                            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-secondary text-[10px] font-semibold text-primary">
                              0{index + 1}
                            </span>
                            <span className="min-w-0 flex-1 text-xs font-medium">
                              {factor.label || factor.feature || "Fator"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Sugestões para a equipe</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {actions.length === 0 ? (
                      <p className="rounded-xl bg-muted/30 p-4 text-xs text-muted-foreground">
                        Nenhuma ação específica foi sugerida para este aluno.
                      </p>
                    ) : (
                      <ol className="space-y-2">
                        {actions.map((action, index) => (
                          <li
                            key={`${index}-${action}`}
                            className="flex items-start gap-3 rounded-xl bg-muted/30 p-3.5 text-xs leading-relaxed"
                          >
                            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white text-primary shadow-sm">
                              <Check className="h-3 w-3" />
                            </span>
                            {action}
                          </li>
                        ))}
                      </ol>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <div className="mb-1 grid h-8 w-8 place-items-center rounded-xl bg-[#fff0ed] text-[#c75b4f]">
                      <MessageSquareText className="h-4 w-4" />
                    </div>
                    <CardTitle className="text-base">Preparar um contato</CardTitle>
                    <CardDescription>Gere a mensagem antes de incluir na régua.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button onClick={loadPreview} disabled={loadingPreview} className="w-full">
                      <Sparkles className="h-4 w-4" />
                      {loadingPreview ? "Preparando…" : "Gerar prévia da mensagem"}
                    </Button>
                    {preview && (
                      <div className="mt-4 rounded-xl border border-border bg-muted/25 p-4">
                        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          Prévia
                        </p>
                        <p className="whitespace-pre-wrap text-xs leading-relaxed">{preview}</p>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <div className="mb-1 grid h-8 w-8 place-items-center rounded-xl bg-secondary text-primary">
                      <History className="h-4 w-4" />
                    </div>
                    <CardTitle className="text-base">Histórico de contatos</CardTitle>
                    <CardDescription>Últimas interações registradas para este aluno.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {logs.isLoading && <Skeleton className="h-20 w-full" />}
                    {!logs.isLoading && (logs.data?.logs?.length ?? 0) === 0 && (
                      <p className="text-xs text-muted-foreground">Nenhum contato registrado ainda.</p>
                    )}
                    <ul className="space-y-2">
                      {logs.data?.logs?.map((log) => (
                        <li
                          key={log.id}
                          className="rounded-xl border border-border/80 px-3 py-2.5 text-xs"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold capitalize">{log.channel || "—"}</span>
                            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">
                              {log.status}
                            </span>
                          </div>
                          <p className="mt-1 text-[10px] text-muted-foreground">
                            {log.created_at
                              ? new Date(log.created_at).toLocaleString("pt-BR")
                              : "—"}
                            {log.campaign_id ? ` · ${log.campaign_id}` : ""}
                          </p>
                          {(log.message_preview || log.skip_reason || log.error) && (
                            <p className="mt-1 line-clamp-2 text-muted-foreground">
                              {log.message_preview || log.skip_reason || log.error}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              </div>
            </div>
          </>
        )}
      </main>
    </>
  );
}
