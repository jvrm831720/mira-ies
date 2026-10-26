"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Download,
  FileCheck2,
  FileSpreadsheet,
  Info,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Trash2,
  UploadCloud,
  WandSparkles,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { ImportField, UploadPreviewResponse, UploadResponse } from "@/types/api";

const IMPORT_FIELDS: ImportField[] = [
  "matricula",
  "nome",
  "curso",
  "turma",
  "semestre",
  "forma_ingresso",
  "dias_atraso_boleto",
  "recorrencia_atrasos",
  "dias_sem_login",
  "presenca_percentual",
  "nota_media",
  "reprovacoes",
  "telefone",
  "email",
  "communication_opt_out",
];

const TEMPLATE_CSV = [
  "matricula,nome,email,telefone,curso,turma,semestre,forma_ingresso,dias_atraso_boleto,recorrencia_atrasos,dias_sem_login,presenca_percentual,nota_media,reprovacoes,communication_opt_out",
  "2024001,Ana Souza,ana@example.edu.br,11999990001,Enfermagem,A,2,Transferência,0,0,1,96,8.7,0,false",
  "2024002,Bruno Lima,bruno@example.edu.br,11999990002,Administração,B,4,Ingresso regular,18,2,12,78,6.4,1,false",
].join("\n");

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function number(value?: number | null) {
  return (value ?? 0).toLocaleString("pt-BR");
}

function downloadTemplate() {
  const csv = "\uFEFF" + TEMPLATE_CSV + "\n";
  const url = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
  const link = document.createElement("a");
  link.href = url;
  link.download = "modelo-importacao-mira.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export default function ImportarPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<UploadPreviewResponse | null>(null);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [autoScore, setAutoScore] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [confirmedImportPolicy, setConfirmedImportPolicy] = useState(false);

  function selectFile(nextFile?: File) {
    if (!nextFile) return;
    const extension = nextFile.name.split(".").pop()?.toLowerCase();
    if (!extension || !["csv", "xlsx", "xls"].includes(extension)) {
      toast.error("Escolha um arquivo CSV ou Excel (.xlsx, .xls).");
      return;
    }
    if (nextFile.size > 50 * 1024 * 1024) {
      toast.error("O arquivo excede o limite de 50 MB.");
      return;
    }
    setFile(nextFile);
    setMapping({});
    setPreview(null);
    setResult(null);
    setErrorMessage(null);
  }

  async function analyzeFile(nextMapping?: Record<string, string>) {
    if (!file) {
      toast.error("Selecione um arquivo antes de analisar.");
      return;
    }
    setPreviewLoading(true);
    setErrorMessage(null);
    try {
      const response = await api.previewUpload(file, nextMapping);
      setPreview(response);
      const confirmedMapping = Object.fromEntries(
        response.columns.map((column) => [
          column.key,
          response.mapped_columns[column.key] || "",
        ])
      );
      setMapping(confirmedMapping);
      if (response.can_import) {
        toast.success("Prévia pronta. Revise as colunas e os avisos antes de importar.");
      } else {
        toast.error("A prévia encontrou itens que precisam de correção.");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Não foi possível analisar o arquivo.";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setPreviewLoading(false);
    }
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0]);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  function clearFile() {
    setFile(null);
    setMapping({});
    setPreview(null);
    setResult(null);
    setErrorMessage(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function onUpload() {
    if (!file || !preview) {
      toast.error("Selecione e analise uma planilha antes de importar.");
      return;
    }
    if (mappingDirty) {
      toast.error("Revalide o mapeamento das colunas antes de importar.");
      return;
    }
    if (!preview.can_import) {
      toast.error("Corrija o mapeamento das colunas obrigatórias antes de continuar.");
      return;
    }
    setUploadLoading(true);
    setErrorMessage(null);
    setResult(null);
    try {
      const response = await api.upload(file, autoScore, mapping);
      setResult(response);
      toast.success(response.message || "Arquivo processado com sucesso.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["risk-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["risk-critical"] }),
        queryClient.invalidateQueries({ queryKey: ["students"] }),
        queryClient.invalidateQueries({ queryKey: ["students-home"] }),
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Não foi possível importar o arquivo.";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setUploadLoading(false);
    }
  }

  const previewMap = preview?.mapped_columns || {};
  const mapIsSameAsPreview = Boolean(preview) && (preview?.columns || []).every(
    (column) => (mapping[column.key] || "") === (previewMap[column.key] || "")
  );
  const mappingDirty = Boolean(preview) && !mapIsSameAsPreview;
  const criticalCount = result?.scoring?.summary?.critico ?? 0;
  const canImport = Boolean(preview?.can_import) && !mappingDirty && confirmedImportPolicy && !uploadLoading && !previewLoading;

  return (
    <>
      <Header
        title="Importar dados"
        subtitle="Uma importação guiada para revisar, corrigir e atualizar sua base com segurança."
      />
      <div className="mx-auto flex w-full max-w-[1500px] justify-end px-4 pt-4 md:px-8 xl:px-10">
        <button
          type="button"
          onClick={() => router.push("/importacoes")}
          className="text-xs font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
        >
          Consultar histórico de importações
        </button>
      </div>
      <main className="mx-auto w-full max-w-[1500px] space-y-5 px-4 pb-12 pt-5 md:px-8 md:pt-7 xl:px-10">
        <section className="grid gap-3 md:grid-cols-3" aria-label="Etapas da importação">
          <StepCard number="01" title="Selecionar arquivo" detail="CSV ou planilha Excel" active={!preview && !result} complete={Boolean(file)} />
          <StepCard number="02" title="Revisar e mapear" detail="Prévia, avisos e correspondências" active={Boolean(preview) && !result} complete={Boolean(result)} />
          <StepCard number="03" title="Importar base" detail="Criar e atualizar registros" active={Boolean(result)} complete={Boolean(result)} />
        </section>

        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Card className="overflow-hidden">
            <CardHeader className="border-b border-black/[0.05] pb-5">
              <div className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.15em] text-primary">
                <span className="grid h-6 w-6 place-items-center rounded-lg bg-secondary">01</span>
                Importação inteligente · sem IA
              </div>
              <CardTitle className="text-xl tracking-[-0.035em]">Selecione a base da instituição</CardTitle>
              <CardDescription>
                A Mira reconhece nomes de colunas por regras determinísticas e permite ajustar o mapeamento antes de salvar qualquer dado.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5 p-5 md:p-6">
              <label
                onDragEnter={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
                }}
                onDrop={onDrop}
                className={`relative flex min-h-[190px] cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-5 py-7 text-center transition ${dragging ? "border-primary bg-secondary" : file ? "border-[#b9c2f2] bg-[#f7f8ff]" : "border-border bg-muted/20 hover:border-primary/40 hover:bg-secondary/40"}`}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                  aria-label="Escolher arquivo CSV ou Excel"
                  onChange={onFileChange}
                />
                <span className="grid h-12 w-12 place-items-center rounded-2xl bg-white text-primary shadow-sm">
                  {file ? <FileCheck2 className="h-6 w-6" /> : <UploadCloud className="h-6 w-6" />}
                </span>
                {file ? (
                  <>
                    <span className="mt-3 max-w-full truncate text-sm font-semibold text-neutral-900">{file.name}</span>
                    <span className="mt-1 text-xs text-muted-foreground">{formatFileSize(file.size)} · pronto para prévia</span>
                  </>
                ) : (
                  <>
                    <span className="mt-3 text-sm font-semibold text-neutral-900">Arraste o arquivo até aqui</span>
                    <span className="mt-1 text-xs text-muted-foreground">ou clique para procurar no computador</span>
                    <span className="mt-4 rounded-lg border border-border bg-white px-3 py-1.5 text-[10px] font-medium text-muted-foreground">CSV · XLSX · XLS · até 50 MB</span>
                  </>
                )}
              </label>

              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={downloadTemplate}>
                    <Download className="h-3.5 w-3.5" /> Baixar modelo CSV
                  </Button>
                  {file && (
                    <Button variant="ghost" size="sm" onClick={clearFile} disabled={previewLoading || uploadLoading}>
                      <Trash2 className="h-3.5 w-3.5" /> Remover arquivo
                    </Button>
                  )}
                </div>
                <Button onClick={() => void analyzeFile()} disabled={!file || previewLoading || uploadLoading}>
                  {previewLoading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <WandSparkles className="h-4 w-4" />}
                  {previewLoading ? "Analisando..." : "Analisar planilha"}
                  {!previewLoading && <ArrowRight className="h-3.5 w-3.5" />}
                </Button>
              </div>

              {errorMessage && (
                <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-xs text-red-800">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{errorMessage}</span>
                </div>
              )}

              {preview && (
                <div className="space-y-5 border-t border-border pt-5">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-primary">02 · Revisão</p>
                      <h2 className="mt-1 text-lg font-semibold tracking-[-0.03em] text-neutral-950">Confira o que será importado</h2>
                      <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted-foreground">{preview.message}</p>
                    </div>
                    <div className="shrink-0 rounded-xl border border-border bg-[var(--brand-paper)] px-3 py-2 text-right">
                      <p className="text-[10px] text-neutral-500">Indicador de qualidade</p>
                      <p className="mt-0.5 text-xl font-semibold tabular-nums text-neutral-900">{preview.quality_score.toLocaleString("pt-BR")}/100</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
                    <ReviewStat label="Linhas recebidas" value={preview.rows_received} tone="neutral" />
                    <ReviewStat label="Prontas para importar" value={preview.rows_to_import} tone="success" />
                    <ReviewStat label="Correspondências existentes" value={preview.existing_matches} tone="indigo" />
                    <ReviewStat label="Linhas inválidas" value={preview.invalid_rows_count} tone={preview.invalid_rows_count ? "warning" : "neutral"} />
                    <ReviewStat label="Duplicadas no arquivo" value={preview.duplicates_in_file} tone={preview.duplicates_in_file ? "warning" : "neutral"} />
                  </div>

                  <section className="space-y-3">
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                      <div>
                        <h3 className="text-sm font-semibold text-neutral-900">Mapeamento de colunas</h3>
                        <p className="mt-1 text-xs text-neutral-500">Confira as sugestões e escolha manualmente o campo correto para cada coluna.</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void analyzeFile()}
                        disabled={previewLoading || uploadLoading}
                        className="inline-flex items-center gap-1.5 self-start text-xs font-semibold text-primary hover:underline disabled:opacity-50 sm:self-auto"
                      >
                        <RefreshCw className="h-3.5 w-3.5" /> Sugerir novamente
                      </button>
                    </div>
                    <div className="overflow-hidden rounded-2xl border border-border">
                      <div className="hidden grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.05fr)] gap-3 bg-muted/40 px-4 py-2.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground sm:grid">
                        <span>Coluna no arquivo</span><span>Exemplo de valor</span><span>Campo Mira</span>
                      </div>
                      <div className="divide-y divide-border/70">
                        {preview.columns.map((column) => (
                          <div key={column.key} className="grid gap-2.5 px-3.5 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.05fr)] sm:items-center sm:gap-3 sm:px-4">
                            <div className="min-w-0">
                              <p className="break-words text-xs font-semibold text-neutral-800">{column.label}</p>
                              <p className="mt-0.5 truncate font-mono text-[10px] text-neutral-400">{column.key}</p>
                            </div>
                            <div className="min-w-0 truncate rounded-lg bg-[var(--brand-paper)] px-2.5 py-2 text-xs text-neutral-600" title={column.sample || "Sem amostra"}>
                              {column.sample || <span className="text-neutral-400">Sem amostra</span>}
                            </div>
                            <label className="relative block min-w-0">
                              <span className="sr-only">Campo Mira para {column.label}</span>
                              <select
                                value={mapping[column.key] || ""}
                                onChange={(event) => setMapping((current) => ({ ...current, [column.key]: event.target.value }))}
                                disabled={uploadLoading}
                                className="h-10 w-full appearance-none rounded-xl border border-input bg-white pl-3 pr-8 text-xs font-medium text-neutral-800 outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:opacity-60"
                              >
                                <option value="">Não importar esta coluna</option>
                                {IMPORT_FIELDS.map((field) => {
                                  const alreadyUsed = Object.entries(mapping).some(([key, value]) => key !== column.key && value === field);
                                  return <option key={field} value={field}>{preview.field_labels[field]}{alreadyUsed ? " · já selecionado" : ""}</option>;
                                })}
                              </select>
                              <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-neutral-400" />
                            </label>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-[11px] leading-relaxed text-neutral-500">
                        O mapeamento é baseado em aliases conhecidos, não em IA. Colunas desconhecidas ficam fora até você escolher um destino.
                      </p>
                      <Button variant="outline" onClick={() => void analyzeFile(mapping)} disabled={!mappingDirty || previewLoading || uploadLoading} className="shrink-0">
                        {previewLoading ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                        Revalidar mapeamento
                      </Button>
                    </div>
                    {mappingDirty && (
                      <p role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                        Você alterou colunas. Revalide o mapeamento para atualizar a prévia antes de importar.
                      </p>
                    )}
                  </section>

                  {preview.missing_required_columns.length > 0 && (
                    <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-xs text-red-800">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>
                        Faltam campos obrigatórios: <strong>{preview.missing_required_columns.map((field) => preview.field_labels[field as ImportField] || field).join(", ")}</strong>. Ajuste o mapeamento acima e revalide.
                      </span>
                    </div>
                  )}

                  {preview.invalid_rows_count > 0 && (
                    <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-3.5">
                      <p className="flex items-center gap-2 text-xs font-semibold text-amber-900">
                        <AlertTriangle className="h-4 w-4" /> {number(preview.invalid_rows_count)} linha(s) não serão importadas
                      </p>
                      <ul className="mt-2 space-y-1.5">
                        {preview.invalid_rows.slice(0, 5).map((item) => (
                          <li key={`${item.line}-${item.message}`} className="text-[11px] leading-relaxed text-amber-900/80">{item.message}</li>
                        ))}
                        {preview.invalid_rows_count > preview.invalid_rows.length && <li className="text-[11px] text-amber-900/70">Outras linhas inválidas foram omitidas desta prévia.</li>}
                      </ul>
                    </div>
                  )}

                  {preview.warnings.length > 0 && (
                    <div className="rounded-xl border border-[#dce0ff] bg-[#f7f7ff] p-3.5">
                      <p className="flex items-center gap-2 text-xs font-semibold text-[#313e9e]"><Info className="h-4 w-4" /> Revisões recomendadas</p>
                      <ul className="mt-2 space-y-1.5">
                        {preview.warnings.slice(0, 6).map((warning, index) => <li key={`${index}-${warning}`} className="text-[11px] leading-relaxed text-[#313e9e]/85">{warning}</li>)}
                        {preview.warnings_total > preview.warnings.length && <li className="text-[11px] text-[#313e9e]/70">Mais {preview.warnings_total - preview.warnings.length} aviso(s) não exibidos aqui.</li>}
                      </ul>
                    </div>
                  )}

                  {preview.missing_recommended_columns.length > 0 && (
                    <p className="text-[11px] leading-relaxed text-neutral-500">
                      Para uma análise de risco mais completa, considere incluir: {preview.missing_recommended_columns.map((field) => preview.field_labels[field as ImportField] || field).join(", ")}.
                    </p>
                  )}

                  <section className="space-y-3">
                    <div>
                      <h3 className="text-sm font-semibold text-neutral-900">Prévia dos registros</h3>
                      <p className="mt-1 text-xs text-neutral-500">Amostra das primeiras linhas válidas após o mapeamento. Nenhum dado foi salvo nesta etapa.</p>
                    </div>
                    {preview.sample_rows.length > 0 ? (
                      <div className="overflow-x-auto rounded-xl border border-border">
                        <table className="w-full min-w-[760px] border-collapse text-left">
                          <thead className="bg-muted/40">
                            <tr>{[
                              ["line", "Linha"],
                              ["matricula", "Matrícula"],
                              ["nome", "Nome"],
                              ["email", "E-mail"],
                              ["curso", "Curso"],
                              ["semestre", "Semestre"],
                              ["presenca_percentual", "Presença"],
                            ].map(([key, label]) => <th key={key} className="whitespace-nowrap px-3 py-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-neutral-500">{label}</th>)}</tr>
                          </thead>
                          <tbody className="divide-y divide-border/70">
                            {preview.sample_rows.map((row, index) => <tr key={`${row.line ?? index}-${index}`} className="hover:bg-muted/20">
                              <td className="px-3 py-2.5 text-[11px] text-neutral-400">{row.line ?? "—"}</td>
                              <td className="px-3 py-2.5 text-xs font-medium text-neutral-700">{String(row.matricula ?? "—")}</td>
                              <td className="max-w-[180px] truncate px-3 py-2.5 text-xs text-neutral-800">{String(row.nome ?? "—")}</td>
                              <td className="max-w-[180px] truncate px-3 py-2.5 text-xs text-neutral-500">{String(row.email ?? "—")}</td>
                              <td className="max-w-[180px] truncate px-3 py-2.5 text-xs text-neutral-500">{String(row.curso ?? "—")}</td>
                              <td className="px-3 py-2.5 text-xs tabular-nums text-neutral-500">{String(row.semestre ?? "—")}</td>
                              <td className="px-3 py-2.5 text-xs tabular-nums text-neutral-500">{row.presenca_percentual == null ? "—" : `${row.presenca_percentual}%`}</td>
                            </tr>)}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-xs text-neutral-500">
                        Nenhuma linha válida para exibir. Ajuste o mapeamento ou corrija as linhas inválidas no arquivo de origem.
                      </div>
                    )}
                  </section>

                  <div className="space-y-4 rounded-2xl border border-border bg-muted/20 p-4">
                    <label className="flex cursor-pointer items-start gap-3">
                      <input type="checkbox" checked={autoScore} onChange={(event) => setAutoScore(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#4050cd]" />
                      <span>
                        <span className="block text-sm font-semibold text-neutral-900">Calcular o risco após a importação</span>
                        <span className="mt-1 block text-xs leading-relaxed text-neutral-500">Ao concluir, a Mira pontua os registros do lote e atualiza os indicadores.</span>
                      </span>
                    </label>
                    <div className="border-t border-border pt-3">
                      <label className="flex cursor-pointer items-start gap-3">
                        <input
                          type="checkbox"
                          checked={confirmedImportPolicy}
                          onChange={(event) => setConfirmedImportPolicy(event.target.checked)}
                          disabled={uploadLoading || previewLoading || mappingDirty || !preview.can_import}
                          className="mt-0.5 h-4 w-4 accent-[#4050cd]"
                        />
                        <span>
                          <span className="block text-sm font-semibold text-neutral-900">Confirmo as regras desta importação</span>
                          <span className="mt-1 block text-xs leading-relaxed text-neutral-600">
                            Matrículas existentes nesta instituição serão atualizadas; campos vazios preservarão valores atuais. Linhas inválidas serão excluídas e duplicatas pela matrícula serão consolidadas usando a última ocorrência do arquivo.
                          </span>
                        </span>
                      </label>
                    </div>
                  </div>

                  <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
                    <p className="flex items-start gap-2 text-[11px] leading-relaxed text-muted-foreground">
                      <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                      Escopo da instituição autenticada. Matrículas existentes serão atualizadas e células vazias preservarão os dados atuais.
                    </p>
                    <Button onClick={() => void onUpload()} disabled={!canImport} className="w-full shrink-0 sm:w-auto">
                      {uploadLoading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                      {uploadLoading ? "Importando..." : `Importar ${number(preview.rows_to_import)} registro(s)`}
                      {!uploadLoading && <ArrowRight className="h-3.5 w-3.5" />}
                    </Button>
                  </div>
                </div>
              )}

              {result && (
                <div className="space-y-4 border-t border-border pt-5">
                  <div className="flex items-start gap-3">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#e9f7f0] text-[#287653]"><CheckCircle2 className="h-5 w-5" /></span>
                    <div className="min-w-0">
                      <h2 className="text-lg font-semibold tracking-[-0.03em] text-neutral-950">{(result.quality?.rows_discarded ?? 0) > 0 ? "Importação concluída com ressalvas" : "Importação concluída"}</h2>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{result.message || "A planilha foi processada."}</p>
                    </div>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <ResultStat label="Registros processados" value={result.students_imported} />
                    <ResultStat label="Novos registros" value={result.quality?.rows_created} />
                    <ResultStat label="Registros atualizados" value={result.quality?.rows_updated} />
                    <ResultStat label="Descartados" value={result.quality?.rows_discarded} />
                  </div>
                  {result.quality?.duplicates_removed ? (
                    <p className="text-xs text-amber-700">{number(result.quality.duplicates_removed)} duplicata(s) no arquivo foram consolidadas pela matrícula.</p>
                  ) : null}
                  {result.quality?.warnings?.length ? (
                    <div className="rounded-xl border border-[#dce0ff] bg-[#f7f7ff] p-3.5">
                      <p className="text-xs font-semibold text-[#313e9e]">Pontos para revisar</p>
                      <ul className="mt-2 space-y-1.5">{result.quality.warnings.slice(0, 6).map((warning, index) => <li key={`${index}-${warning}`} className="text-[11px] leading-relaxed text-[#313e9e]/85">{warning}</li>)}</ul>
                    </div>
                  ) : null}
                  {result.scoring?.summary && (
                    <div className="flex flex-wrap gap-2 border-t border-border pt-4 text-xs">
                      <span className="mr-1 self-center font-medium text-muted-foreground">Faixas de risco</span>
                      <span className="rounded-full bg-[#fff0ed] px-3 py-1.5 font-semibold text-[#b84336]">Crítico {number(result.scoring.summary.critico)}</span>
                      <span className="rounded-full bg-[#eef0ff] px-3 py-1.5 font-semibold text-[#3848b5]">Médio {number(result.scoring.summary.medio)}</span>
                      <span className="rounded-full bg-[#edf0fb] px-3 py-1.5 font-semibold text-[#29399f]">Baixo {number(result.scoring.summary.baixo)}</span>
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => router.push("/")}>Ver painel <ArrowRight className="h-4 w-4" /></Button>
                    {criticalCount > 0 && <Button variant="outline" onClick={() => router.push("/alunos?risk=critico")}>Ver {number(criticalCount)} críticos</Button>}
                    <Button variant="outline" onClick={clearFile}>Importar outra planilha</Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <aside className="space-y-4">
            <Card className="bg-[var(--brand-midnight)] text-white shadow-none">
              <CardHeader>
                <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/10 text-[var(--brand-coral)]"><FileSpreadsheet className="h-4 w-4" /></span>
                <CardTitle className="pt-1 text-[15px] text-white">Como a importação funciona</CardTitle>
                <CardDescription className="text-white/60">Regras claras, prévia primeiro e confirmação antes de salvar.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-xs leading-relaxed text-white/75">
                <GuidanceItem title="Mapeamento automático">A Mira sugere campos por nomes e aliases conhecidos. Você pode ajustar qualquer coluna.</GuidanceItem>
                <GuidanceItem title="Validação antes de salvar">Linhas sem matrícula ou nome são sinalizadas; valores numéricos e e-mails suspeitos geram avisos.</GuidanceItem>
                <GuidanceItem title="Deduplicação por matrícula">Duplicatas dentro do arquivo são consolidadas. Registros existentes da mesma instituição são atualizados.</GuidanceItem>
                <GuidanceItem title="Preservação de dados">Células vazias não apagam valores existentes, e a preferência de não contato é preservada quando não informada.</GuidanceItem>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-[15px]">Campos essenciais</CardTitle>
                <CardDescription>Obrigatórios para importar uma linha.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-xs">
                <div className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /><div><p className="font-semibold text-neutral-800">Matrícula / RA</p><p className="mt-0.5 text-neutral-500">Identificador usado para localizar registros existentes dentro da instituição.</p></div></div>
                <div className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /><div><p className="font-semibold text-neutral-800">Nome completo</p><p className="mt-0.5 text-neutral-500">Usado para identificar o aluno nas telas da Mira.</p></div></div>
              </CardContent>
            </Card>

            <div className="rounded-2xl border border-[#dce0ff] bg-[#f3f4ff] p-4 text-xs leading-relaxed text-[#313e9e]">
              <div className="flex items-start gap-2"><Info className="mt-0.5 h-4 w-4 shrink-0" /><p><strong>Privacidade e consentimento:</strong> importe somente dados necessários e autorizados pela instituição. Marque <code>communication_opt_out</code> como verdadeiro para registrar que o aluno não deve ser contatado.</p></div>
            </div>

            <div className="flex items-start gap-2 rounded-2xl border border-border bg-white px-3.5 py-3 text-[11px] leading-relaxed text-neutral-500">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              Prévia e importação usam a sessão autenticada. Nenhum dado é salvo até você confirmar a importação.
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}

function StepCard({ number: step, title, detail, active, complete }: { number: string; title: string; detail: string; active?: boolean; complete?: boolean }) {
  return (
    <div className={`flex items-center gap-3 rounded-2xl border px-4 py-3 transition ${active ? "border-[rgba(64,80,205,0.25)] bg-[#f4f5ff]" : "border-black/[0.06] bg-white"}`}>
      <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl text-xs font-semibold ${complete ? "bg-[#e9f7f0] text-[#287653]" : active ? "bg-[var(--brand-indigo)] text-white" : "bg-neutral-100 text-neutral-500"}`}>
        {complete ? <CheckCircle2 className="h-4 w-4" /> : step}
      </span>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-neutral-900">{title}</p>
        <p className="mt-0.5 text-[10px] text-neutral-500">{detail}</p>
      </div>
    </div>
  );
}

function ReviewStat({ label, value, tone }: { label: string; value: number; tone: "neutral" | "success" | "indigo" | "warning" }) {
  const tones = {
    neutral: "bg-white text-neutral-900",
    success: "bg-[#eff8f3] text-[#287653]",
    indigo: "bg-[#f1f2ff] text-[#3848b5]",
    warning: "bg-[#fff7e8] text-[#966215]",
  };
  return (
    <div className={`rounded-xl border border-black/[0.055] p-3 ${tones[tone]}`}>
      <p className="min-h-7 text-[10px] font-medium leading-relaxed opacity-75">{label}</p>
      <p className="mt-1 text-2xl font-semibold leading-none tracking-[-0.04em] tabular-nums">{number(value)}</p>
    </div>
  );
}

function ResultStat({ label, value }: { label: string; value?: number }) {
  return (
    <div className="rounded-xl border border-border/80 bg-muted/20 p-3.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">{label}</p>
      <p className="mt-1.5 text-lg font-semibold tabular-nums">{value == null ? "—" : number(value)}</p>
    </div>
  );
}

function GuidanceItem({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="flex gap-2.5"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand-coral)]" /><p><strong className="font-semibold text-white">{title}.</strong> {children}</p></div>;
}
