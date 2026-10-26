"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, CheckCircle2, Clock3, FileSpreadsheet, LoaderCircle, RefreshCw, XCircle } from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { UploadHistoryItem, UploadHistoryResponse } from "@/types/api";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function statusDetails(status: string) {
  const normalized = status.toLowerCase();
  if (["completed", "complete", "success", "succeeded", "processed", "concluida", "concluída"].includes(normalized)) {
    return { label: "Concluída", tone: "border-emerald-200 bg-emerald-50 text-emerald-800", icon: CheckCircle2 };
  }
  if (["failed", "error", "falha", "erro"].includes(normalized)) {
    return { label: "Falha", tone: "border-red-200 bg-red-50 text-red-800", icon: XCircle };
  }
  if (["processing", "running", "pending", "received", "queued"].includes(normalized)) {
    return { label: normalized === "processing" || normalized === "running" ? "Em processamento" : "Aguardando processamento", tone: "border-amber-200 bg-amber-50 text-amber-800", icon: Clock3 };
  }
  return { label: status || "Estado não informado", tone: "border-neutral-200 bg-neutral-50 text-neutral-700", icon: AlertTriangle };
}

export default function ImportacoesPage() {
  const router = useRouter();
  const [data, setData] = useState<UploadHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 20;

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.uploadHistory(limit, offset);
      setData(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível carregar o histórico.");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  return (
    <>
      <Header title="Histórico de importações" subtitle="Consulte as operações realizadas pela sua instituição e seus resultados." />
      <main className="mx-auto w-full max-w-[1200px] space-y-5 px-4 pb-12 pt-5 md:px-8 md:pt-7 xl:px-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button variant="outline" onClick={() => router.push("/importar")}>
            <ArrowLeft className="h-4 w-4" /> Voltar para importar dados
          </Button>
          <Button variant="outline" onClick={() => void loadHistory()} disabled={loading}>
            {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Atualizar
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg tracking-tight">Importações da instituição</CardTitle>
            <CardDescription>Os dados abaixo são carregados do servidor e limitados à instituição da sua sessão.</CardDescription>
          </CardHeader>
          <CardContent>
            {loading && !data ? (
              <div className="flex items-center gap-2 py-12 text-sm text-neutral-500"><LoaderCircle className="h-4 w-4 animate-spin" /> Carregando histórico...</div>
            ) : error ? (
              <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                <p>{error}</p>
                <Button variant="outline" onClick={() => void loadHistory()}>Tentar novamente</Button>
              </div>
            ) : data && data.items.length ? (
              <div className="space-y-0 divide-y divide-neutral-100">
                {data.items.map((item: UploadHistoryItem) => {
                  const status = statusDetails(item.status);
                  const StatusIcon = status.icon;
                  return (
                    <article key={item.id} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex min-w-0 items-start gap-3">
                        <span className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-neutral-100 text-neutral-700"><FileSpreadsheet className="h-5 w-5" /></span>
                        <div className="min-w-0">
                          <p className="break-words text-sm font-semibold text-neutral-900">{item.filename || "Arquivo sem nome"}</p>
                          <p className="mt-1 text-xs text-neutral-500">{formatDate(item.uploaded_at)} · {item.total_rows.toLocaleString("pt-BR")} linhas recebidas</p>
                          {item.error_message && <p className="mt-2 max-w-2xl text-xs text-red-700">{item.error_message}</p>}
                          <p className="mt-1 text-xs text-neutral-500">{item.processed_rows.toLocaleString("pt-BR")} registros processados</p>
                        </div>
                      </div>
                      <span className={`inline-flex w-fit shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${status.tone}`}>
                        <StatusIcon className="h-3.5 w-3.5" /> {status.label}
                      </span>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="flex flex-col items-center py-12 text-center">
                <span className="grid h-12 w-12 place-items-center rounded-2xl bg-neutral-100 text-neutral-600"><FileSpreadsheet className="h-6 w-6" /></span>
                <h3 className="mt-4 text-sm font-semibold text-neutral-900">Nenhuma importação encontrada</h3>
                <p className="mt-1 max-w-sm text-xs leading-relaxed text-neutral-500">Quando você importar uma base, ela aparecerá aqui com o estado e os totais registrados pelo servidor.</p>
                <Button className="mt-4" onClick={() => router.push("/importar")}>Importar dados</Button>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-neutral-500">{data ? `Exibindo ${data.items.length.toLocaleString("pt-BR")} operações nesta página` : ""}</p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setOffset((current) => Math.max(0, current - limit))} disabled={offset === 0 || loading}>Anterior</Button>
            <Button variant="outline" size="sm" onClick={() => setOffset((current) => current + limit)} disabled={!data?.has_more || loading}>Próxima</Button>
          </div>
        </div>
      </main>
    </>
  );
}
