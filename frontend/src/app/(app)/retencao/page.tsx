"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { copy } from "@/lib/copy";
import type { RiskLevel, RetentionRunResult } from "@/types/api";
import { AlertTriangle, Play } from "lucide-react";

export default function RetencaoPage() {
  const qc = useQueryClient();
  const [dryRun, setDryRun] = useState(true);
  const [limit, setLimit] = useState(50);
  const [levels, setLevels] = useState<RiskLevel[]>(["critico"]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RetentionRunResult | null>(null);

  const status = useQuery({ queryKey: ["agents-status"], queryFn: () => api.agentsStatus() });

  function toggleLevel(level: RiskLevel) {
    setLevels((prev) =>
      prev.includes(level) ? prev.filter((l) => l !== level) : [...prev, level]
    );
  }

  async function run() {
    if (levels.length === 0) {
      toast.error("Selecione ao menos um nível de risco");
      return;
    }
    if (!dryRun) {
      const ok = window.confirm(
        "Isso pode enviar WhatsApp, e-mail ou SMS reais, se os providers estiverem configurados. Continuar?"
      );
      if (!ok) return;
    }
    setLoading(true);
    try {
      const res = await api.retentionRun({
        risk_levels: levels,
        limit,
        dry_run: dryRun,
      }, crypto.randomUUID());
      setResult(res);
      toast.success(dryRun ? "Simulação concluída" : "Retenção executada");
      qc.invalidateQueries({ queryKey: ["retention-logs"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha na retenção");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Header title="Retenção ativa" subtitle="Régua de contatos com simulação segura" />
      <main className="mx-auto max-w-3xl space-y-6 p-4 md:p-8">
        {(dryRun || status.data?.dry_run_default) && (
          <div className="flex items-start gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {copy.dryRunBanner}
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Configurar execução</CardTitle>
            <CardDescription>
              Providers atuais: WhatsApp {status.data?.providers.whatsapp ?? "—"} · E-mail{" "}
              {status.data?.providers.email ?? "—"} · SMS {status.data?.providers.sms ?? "—"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div>
              <p className="mb-2 text-sm font-medium">Níveis de risco</p>
              <div className="flex flex-wrap gap-2">
                {(["critico", "medio", "baixo"] as RiskLevel[]).map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => toggleLevel(level)}
                    className={`rounded-full px-3 py-1 text-xs font-medium ring-1 transition ${
                      levels.includes(level)
                        ? "bg-primary text-primary-foreground ring-primary"
                        : "bg-background text-muted-foreground ring-border"
                    }`}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="font-medium">Limite de alunos</span>
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value) || 50)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                />
              </label>
              <label className="flex items-center gap-2 pt-6 text-sm">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                />
                Sempre iniciar em simulação (dry-run)
              </label>
            </div>

            <Button onClick={run} disabled={loading}>
              <Play className="h-4 w-4" />
              {loading ? "Executando..." : dryRun ? "Simular contatos" : "Executar contatos"}
            </Button>
          </CardContent>
        </Card>

        {result && (
          <Card>
            <CardHeader>
              <CardTitle>Resultado</CardTitle>
              <CardDescription>{result.message || "Execução finalizada"}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {result.dry_run !== undefined && (
                <p>
                  Modo: <strong>{result.dry_run ? "simulação" : "real"}</strong>
                </p>
              )}
              {result.totals && (
                <pre className="overflow-x-auto rounded-lg bg-muted/50 p-3 text-xs">
                  {JSON.stringify(result.totals, null, 2)}
                </pre>
              )}
              {result.by_channel && (
                <pre className="overflow-x-auto rounded-lg bg-muted/50 p-3 text-xs">
                  {JSON.stringify(result.by_channel, null, 2)}
                </pre>
              )}
              {!result.totals && !result.by_channel && (
                <pre className="overflow-x-auto rounded-lg bg-muted/50 p-3 text-xs">
                  {JSON.stringify(result, null, 2)}
                </pre>
              )}
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}
