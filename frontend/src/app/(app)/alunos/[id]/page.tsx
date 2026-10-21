"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Header } from "@/components/layout/header";
import { RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatScore } from "@/lib/utils";
import { ArrowLeft, Mail, Phone, Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

export default function StudentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [preview, setPreview] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["student-risk", id],
    queryFn: () => api.studentRisk(id),
    enabled: Boolean(id),
  });

  async function loadPreview() {
    setLoadingPreview(true);
    try {
      const res = await api.retentionPreview(id);
      setPreview(String(res.message || JSON.stringify(res, null, 2)));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha ao gerar preview");
    } finally {
      setLoadingPreview(false);
    }
  }

  const actions =
    data?.recommended_actions || data?.shap_top_factors?.recommended_actions || [];

  return (
    <>
      <Header title="Ficha do aluno" subtitle="Score, fatores e próximo passo" />
      <main className="space-y-6 p-4 md:p-8">
        <Link
          href="/alunos"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Voltar para alunos
        </Link>

        {isLoading && <Skeleton className="h-48 w-full rounded-xl" />}
        {error && (
          <Card>
            <CardContent className="p-6 text-sm text-destructive">
              Não foi possível carregar este aluno.
            </CardContent>
          </Card>
        )}

        {data && (
          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-1">
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle className="text-xl">{data.nome || "Sem nome"}</CardTitle>
                    <CardDescription>
                      {data.matricula}
                      {data.curso ? ` · ${data.curso}` : ""}
                    </CardDescription>
                  </div>
                  <RiskBadge level={data.risk_level} />
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">Risk score</p>
                  <p className="text-4xl font-semibold tabular-nums">{formatScore(data.risk_score)}</p>
                </div>
                <div className="space-y-1 text-sm text-muted-foreground">
                  {data.telefone && (
                    <p className="flex items-center gap-2">
                      <Phone className="h-3.5 w-3.5" /> {data.telefone}
                    </p>
                  )}
                  {data.email && (
                    <p className="flex items-center gap-2">
                      <Mail className="h-3.5 w-3.5" /> {data.email}
                    </p>
                  )}
                  {!data.telefone && !data.email && (
                    <p>Sem telefone/e-mail na base — retenção pode ser ignorada.</p>
                  )}
                </div>
                <Button onClick={loadPreview} disabled={loadingPreview} className="w-full">
                  <Sparkles className="h-4 w-4" />
                  {loadingPreview ? "Gerando..." : "Preview da mensagem"}
                </Button>
              </CardContent>
            </Card>

            <div className="space-y-6 lg:col-span-2">
              <Card>
                <CardHeader>
                  <CardTitle>Por que este risco?</CardTitle>
                  <CardDescription>Explicação em linguagem de coordenação</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="leading-relaxed text-foreground">
                    {data.shap_summary ||
                      data.shap_top_factors?.summary ||
                      "Fatores detalhados não disponíveis para este aluno."}
                  </p>
                  {Array.isArray(data.shap_top_factors?.top_3) &&
                    data.shap_top_factors!.top_3!.length > 0 && (
                      <ul className="space-y-2">
                        {data.shap_top_factors!.top_3!.map((f, i) => (
                          <li
                            key={i}
                            className="rounded-lg border border-border bg-muted/30 px-3 py-2"
                          >
                            {f.label || f.feature || "Fator"}
                            {typeof f.value === "number"
                              ? ` (${f.value.toFixed?.(2) ?? f.value})`
                              : ""}
                          </li>
                        ))}
                      </ul>
                    )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Ações recomendadas</CardTitle>
                </CardHeader>
                <CardContent>
                  {actions.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Nenhuma ação específica listada.</p>
                  ) : (
                    <ol className="list-decimal space-y-2 pl-5 text-sm">
                      {actions.map((a, i) => (
                        <li key={i}>{a}</li>
                      ))}
                    </ol>
                  )}
                </CardContent>
              </Card>

              {preview && (
                <Card>
                  <CardHeader>
                    <CardTitle>Preview de contato</CardTitle>
                    <CardDescription>Nada foi enviado</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <pre className="whitespace-pre-wrap rounded-lg bg-muted/50 p-4 text-sm leading-relaxed">
                      {preview}
                    </pre>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}
      </main>
    </>
  );
}
