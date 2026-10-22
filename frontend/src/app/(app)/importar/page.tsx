"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowRight,
  CheckCircle2,
  FileSpreadsheet,
  FileText,
  Info,
  LoaderCircle,
  ShieldCheck,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { UploadResponse } from "@/types/api";

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ImportarPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [autoScore, setAutoScore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);

  function selectFile(nextFile?: File) {
    if (!nextFile) return;
    const extension = nextFile.name.split(".").pop()?.toLowerCase();
    if (!extension || !["csv", "xlsx", "xls"].includes(extension)) {
      toast.error("Escolha um arquivo CSV ou Excel (.xlsx, .xls).");
      return;
    }
    setFile(nextFile);
    setResult(null);
  }

  async function onUpload() {
    if (!file) {
      toast.error("Selecione um arquivo CSV ou Excel para continuar.");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const response = await api.upload(file, autoScore);
      setResult(response);
      toast.success(response.message || "Arquivo processado com sucesso.");
      qc.invalidateQueries({ queryKey: ["risk-summary"] });
      qc.invalidateQueries({ queryKey: ["risk-critical"] });
      qc.invalidateQueries({ queryKey: ["students"] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Não foi possível importar o arquivo.");
    } finally {
      setLoading(false);
    }
  }

  function clearFile() {
    setFile(null);
    setResult(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  const criticalCount = result?.scoring?.summary?.critico ?? 0;

  return (
    <>
      <Header
        title="Importar dados"
        subtitle="Adicione ou atualize a base de alunos da sua instituição."
      />
      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 pb-10 pt-5 md:px-9 md:pt-7">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <Card>
            <CardHeader className="pb-4">
              <div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
                <span className="grid h-6 w-6 place-items-center rounded-lg bg-secondary">01</span>{" "}
                Envio seguro
              </div>
              <CardTitle className="text-lg">Selecione sua planilha</CardTitle>
              <CardDescription>Os dados ficam vinculados à instituição da sua sessão.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <label
                onDragEnter={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget as Node | null))
                    setDragging(false);
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  selectFile(event.dataTransfer.files?.[0]);
                }}
                className={`relative flex min-h-[218px] cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-5 py-8 text-center transition ${
                  dragging
                    ? "border-primary bg-secondary"
                    : file
                      ? "border-[#b9c2f2] bg-[#f7f8ff]"
                      : "border-border bg-muted/25 hover:border-primary/40 hover:bg-secondary/50"
                }`}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                  aria-label="Escolher arquivo CSV ou Excel"
                  onChange={(event) => selectFile(event.target.files?.[0])}
                />
                <span
                  className={`grid h-12 w-12 place-items-center rounded-2xl ${
                    file ? "bg-[#e8ebff] text-primary" : "bg-white text-primary shadow-sm"
                  }`}
                >
                  {file ? <FileCheckIcon /> : <UploadCloud className="h-6 w-6" />}
                </span>
                {file ? (
                  <>
                    <span className="mt-3 max-w-full truncate text-sm font-semibold">{file.name}</span>
                    <span className="mt-1 text-xs text-muted-foreground">
                      {formatFileSize(file.size)} · pronto para importar
                    </span>
                  </>
                ) : (
                  <>
                    <span className="mt-3 text-sm font-semibold">Arraste o arquivo até aqui</span>
                    <span className="mt-1 text-xs text-muted-foreground">
                      ou clique para procurar no computador
                    </span>
                    <span className="mt-4 rounded-lg border border-border bg-white px-3 py-1.5 text-[10px] font-medium text-muted-foreground">
                      CSV · XLSX · XLS
                    </span>
                  </>
                )}
              </label>
              {file && (
                <button
                  type="button"
                  onClick={clearFile}
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Remover arquivo
                </button>
              )}

              <div className="rounded-xl border border-border/80 bg-muted/25 p-4">
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={autoScore}
                    onChange={(event) => setAutoScore(event.target.checked)}
                    className="mt-0.5 h-4 w-4 accent-[#4050cd]"
                  />
                  <span>
                    <span className="block text-sm font-semibold">
                      Calcular o risco após a importação
                    </span>
                    <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
                      A Mira pontua os registros e atualiza os indicadores do painel.
                    </span>
                  </span>
                </label>
              </div>
              <div className="flex flex-col-reverse gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="flex items-start gap-2 text-[11px] leading-relaxed text-muted-foreground">
                  <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" /> Importação
                  protegida por instituição e sessão.
                </p>
                <Button onClick={onUpload} disabled={loading || !file} className="w-full sm:w-auto">
                  {loading ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <UploadCloud className="h-4 w-4" />
                  )}
                  {loading ? "Importando…" : "Importar base"}
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>

          <aside className="space-y-4">
            <Card className="bg-[var(--brand-midnight)] text-white shadow-none">
              <CardHeader>
                <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/10 text-[var(--brand-coral)]">
                  <FileSpreadsheet className="h-4 w-4" />
                </span>
                <CardTitle className="pt-1 text-[15px] text-white">Prepare sua base</CardTitle>
                <CardDescription className="text-white/60">
                  Uma planilha organizada melhora a qualidade da análise.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-xs leading-relaxed text-white/75">
                <div className="flex gap-2">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand-coral)]" />
                  <span>Inclua matrícula e nome para identificar cada registro.</span>
                </div>
                <div className="flex gap-2">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand-coral)]" />
                  <span>Dados acadêmicos ajudam a contextualizar os sinais de risco.</span>
                </div>
                <div className="flex gap-2">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand-coral)]" />
                  <span>Telefone e e-mail podem apoiar o acompanhamento de retenção.</span>
                </div>
              </CardContent>
            </Card>
            <div className="rounded-2xl border border-[#dce0ff] bg-[#f3f4ff] p-4 text-xs leading-relaxed text-[#313e9e]">
              <div className="flex items-start gap-2">
                <Info className="mt-0.5 h-4 w-4 shrink-0" />
                <p>
                  <strong>Antes de enviar:</strong> confirme que a planilha contém somente os dados
                  necessários e está autorizada pela sua instituição.
                </p>
              </div>
            </div>
          </aside>
        </div>

        {result && (
          <Card className="overflow-hidden border-[#cfe8dc]">
            <div className="h-1 bg-[#3b9b71]" />
            <CardHeader className="flex-row items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#e9f7f0] text-[#287653]">
                <CheckCircle2 className="h-5 w-5" />
              </span>
              <div>
                <CardTitle>Importação concluída</CardTitle>
                <CardDescription className="mt-1">
                  {result.message || "Sua planilha foi processada."}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <ImportStat label="Registros importados" value={result.students_imported} />
                <ImportStat label="Alunos pontuados" value={result.scoring?.scored} />
                <ImportStat
                  label="Lote"
                  value={result.batch?.id ? result.batch.id.slice(0, 8) : undefined}
                />
              </div>
              {result.scoring?.summary && (
                <div className="flex flex-wrap gap-2 border-t border-border pt-4 text-xs">
                  <span className="mr-1 self-center font-medium text-muted-foreground">
                    Faixas de risco
                  </span>
                  <span className="rounded-full bg-[#fff0ed] px-3 py-1.5 font-semibold text-[#b84336]">
                    Crítico {result.scoring.summary.critico ?? 0}
                  </span>
                  <span className="rounded-full bg-[#eef0ff] px-3 py-1.5 font-semibold text-[#3848b5]">
                    Médio {result.scoring.summary.medio ?? 0}
                  </span>
                  <span className="rounded-full bg-[#edf0fb] px-3 py-1.5 font-semibold text-[#29399f]">
                    Baixo {result.scoring.summary.baixo ?? 0}
                  </span>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => router.push("/")}>
                  Ver painel <ArrowRight className="h-4 w-4" />
                </Button>
                {criticalCount > 0 && (
                  <Button variant="outline" onClick={() => router.push("/alunos?risk=critico")}>
                    Ver {criticalCount} críticos
                  </Button>
                )}
                <Button variant="outline" onClick={clearFile}>
                  Importar outra planilha
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}

function FileCheckIcon() {
  return (
    <span className="relative">
      <FileText className="h-6 w-6" />
      <CheckCircle2 className="absolute -bottom-1 -right-1 h-3.5 w-3.5 rounded-full bg-white text-[#35835f]" />
    </span>
  );
}

function ImportStat({ label, value }: { label: string; value?: number | string }) {
  return (
    <div className="rounded-xl border border-border/80 bg-muted/20 p-3.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-1.5 truncate text-lg font-semibold tabular-nums">{value ?? "—"}</p>
    </div>
  );
}
