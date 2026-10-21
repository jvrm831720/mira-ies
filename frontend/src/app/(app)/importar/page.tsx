"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { UploadResponse } from "@/types/api";
import { FileSpreadsheet, Upload } from "lucide-react";

export default function ImportarPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [autoScore, setAutoScore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);

  async function onUpload() {
    if (!file) {
      toast.error("Selecione um arquivo CSV ou XLSX");
      return;
    }
    setLoading(true);
    try {
      const res = await api.upload(file, autoScore);
      setResult(res);
      toast.success(res.message || "Arquivo processado");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha no upload");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Header title="Importar planilha" subtitle="CSV ou XLSX com dados dos alunos" />
      <main className="mx-auto max-w-3xl space-y-6 p-4 md:p-8">
        <Card>
          <CardHeader>
            <CardTitle>Enviar arquivo</CardTitle>
            <CardDescription>
              Colunas mínimas: matrícula e nome. Telefone/e-mail permitem retenção ativa.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-muted/20 px-6 py-12 text-center transition hover:bg-muted/40">
              <div className="rounded-full bg-primary/10 p-3 text-primary">
                <FileSpreadsheet className="h-6 w-6" />
              </div>
              <div>
                <p className="font-medium">{file ? file.name : "Arraste ou clique para escolher"}</p>
                <p className="text-xs text-muted-foreground">.csv, .xlsx, .xls</p>
              </div>
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={autoScore}
                onChange={(e) => setAutoScore(e.target.checked)}
              />
              Calcular risk score automaticamente após o upload
            </label>

            <Button onClick={onUpload} disabled={loading || !file} className="w-full sm:w-auto">
              <Upload className="h-4 w-4" />
              {loading ? "Processando..." : "Importar e processar"}
            </Button>
          </CardContent>
        </Card>

        {result && (
          <Card>
            <CardHeader>
              <CardTitle>Resultado</CardTitle>
              <CardDescription>{result.message}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p>
                <span className="text-muted-foreground">Alunos importados:</span>{" "}
                <strong>{result.students_imported ?? "—"}</strong>
              </p>
              {result.scoring?.scored !== undefined && (
                <p>
                  <span className="text-muted-foreground">Pontuados:</span>{" "}
                  <strong>{result.scoring.scored}</strong>
                </p>
              )}
              {result.scoring?.summary && (
                <p className="text-muted-foreground">
                  Crítico {result.scoring.summary.critico ?? 0} · Médio{" "}
                  {result.scoring.summary.medio ?? 0} · Baixo {result.scoring.summary.baixo ?? 0}
                </p>
              )}
              <Button variant="outline" onClick={() => router.push("/")}>
                Ir para a central de comando
              </Button>
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}
