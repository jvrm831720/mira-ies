"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  AlertCircle, ArrowRight, CheckCircle2, Clock3, FileSpreadsheet, Files,
  History, LoaderCircle, RefreshCw, ShieldCheck, Trash2, UploadCloud,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { ImportField, UploadPreviewResponse, UploadResponse, MultiUploadPreviewResponse, UploadStructureResponse } from "@/types/api";

const IMPORT_FIELDS: ImportField[] = [
  "matricula", "nome", "curso", "turma", "semestre", "forma_ingresso",
  "dias_atraso_boleto", "recorrencia_atrasos", "dias_sem_login",
  "presenca_percentual", "nota_media", "reprovacoes", "telefone", "email",
  "communication_opt_out",
];

const TEMPLATE_CSV = [
  "matricula,nome,email,telefone,curso,turma,semestre,forma_ingresso,dias_atraso_boleto,recorrencia_atrasos,dias_sem_login,presenca_percentual,nota_media,reprovacoes,communication_opt_out",
  "2024001,Ana Souza,ana@example.edu.br,11999990001,Enfermagem,A,2,Transferência,0,0,1,96,8.7,0,false",
  "2024002,Bruno Lima,bruno@example.edu.br,11999990002,Administração,B,4,Ingresso regular,18,2,12,78,6.4,1,false",
].join("\n");

const FIELD_LABELS: Record<ImportField, string> = {
  matricula: "Matrícula", nome: "Nome completo", curso: "Curso", turma: "Turma",
  semestre: "Semestre", forma_ingresso: "Forma de ingresso",
  dias_atraso_boleto: "Dias de atraso financeiro", recorrencia_atrasos: "Recorrência de atrasos",
  dias_sem_login: "Dias sem login", presenca_percentual: "Presença (%)",
  nota_media: "Nota média", reprovacoes: "Reprovações", telefone: "Telefone",
  email: "E-mail", communication_opt_out: "Não contatar",
};

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

function isSupported(file: File) {
  return ["csv", "xlsx", "xls"].includes(file.name.split(".").pop()?.toLowerCase() || "");
}

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ImportarPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const multiInputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<"single" | "multiple">("single");
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<UploadPreviewResponse | null>(null);
  const [structure, setStructure] = useState<UploadStructureResponse | null>(null);
  const [selectedSheet, setSelectedSheet] = useState<string>("");
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [autoScore, setAutoScore] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [confirmedImportPolicy, setConfirmedImportPolicy] = useState(false);
  const [multiFiles, setMultiFiles] = useState<File[]>([]);
  const [multiRoles, setMultiRoles] = useState<string[]>([]);
  const [multiPreview, setMultiPreview] = useState<MultiUploadPreviewResponse | null>(null);
  const [multiPreviewLoading, setMultiPreviewLoading] = useState(false);
  const [multiConfirmationLoading, setMultiConfirmationLoading] = useState(false);
  const [multiIdempotencyKey, setMultiIdempotencyKey] = useState<string | null>(null);
  const [multiConfirmedPolicy, setMultiConfirmedPolicy] = useState(false);
  const [multiError, setMultiError] = useState<string | null>(null);

  function selectFile(nextFile?: File) {
    if (!nextFile) return;
    if (!isSupported(nextFile)) {
      toast.error("Escolha um arquivo CSV ou Excel (.xlsx, .xls).");
      return;
    }
    if (nextFile.size > 50 * 1024 * 1024) {
      toast.error("O arquivo excede o limite de 50 MB.");
      return;
    }
    setFile(nextFile);
    setMapping({});
    setStructure(null);
    setSelectedSheet("");
    setPreview(null);
    setResult(null);
    setErrorMessage(null);
    setConfirmedImportPolicy(false);
  }

  function selectMultipleFiles(files: FileList | File[]) {
    const selected = Array.from(files);
    if (!selected.length) return;
    if (selected.length > 10) return void toast.error("Selecione no máximo 10 arquivos por vez.");
    const unsupported = selected.find((item) => !isSupported(item));
    if (unsupported) return void toast.error(`"${unsupported.name}" não é CSV ou Excel.`);
    if (selected.some((item) => item.size > 50 * 1024 * 1024) || selected.reduce((sum, item) => sum + item.size, 0) > 50 * 1024 * 1024) {
      return void toast.error("O limite total da importação é 50 MB.");
    }
    setMultiFiles((current) => {
      const merged = [...current];
      selected.forEach((item) => { if (!merged.some((existing) => existing.name === item.name && existing.size === item.size && existing.lastModified === item.lastModified)) merged.push(item); });
      if (merged.length > 10) {
        toast.error("Selecione no máximo 10 arquivos por vez.");
        return current;
      }
      setMultiRoles(merged.map((_, index) => index === 0 ? "cadastro" : "financeiro"));
      return merged;
    });
    setMultiPreview(null);
    setMultiIdempotencyKey(crypto.randomUUID());
    setMultiConfirmedPolicy(false);
    setMultiError(null);
  }

  async function analyzeFile() {
    if (!file) return;
    setPreviewLoading(true);
    setErrorMessage(null);
    setPreview(null);
    try {
      const response = await api.inspectUploadStructure(file);
      setStructure(response);
      const chosen = response.suggested_sheet || response.sheets[0]?.name || "";
      setSelectedSheet(chosen);
      setMapping({});
      setConfirmedImportPolicy(false);
      if (response.requires_sheet_selection) toast.message("Escolha a aba que contém a base antes de validar os registros.");
      else toast.success("Estrutura identificada. Confira a aba e valide os dados.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Não foi possível inspecionar o arquivo.";
      setErrorMessage(message);
      toast.error(message);
    } finally { setPreviewLoading(false); }
  }

  async function validateSelectedSheet(nextMapping?: Record<string, string>) {
    if (!file || !selectedSheet) return;
    setPreviewLoading(true);
    setErrorMessage(null);
    try {
      const response = await api.previewUpload(file, nextMapping, selectedSheet);
      setPreview(response);
      setMapping(Object.fromEntries(response.columns.map((column) => [column.key, response.mapped_columns[column.key] || ""])));
      setConfirmedImportPolicy(false);
      if (!response.can_import) toast.error("A prévia encontrou campos obrigatórios pendentes.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Não foi possível validar esta aba.";
      setErrorMessage(message);
      toast.error(message);
    } finally { setPreviewLoading(false); }
  }

    async function analyzeMultipleFiles() {
    if (!multiFiles.length) return;
    setMultiPreviewLoading(true);
    setMultiError(null);
    try {
      const response = await api.previewMultipleUploads(multiFiles, multiRoles);
      setMultiPreview(response);
      toast.success("Análise concluída. Nenhum dado foi salvo.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Não foi possível analisar os arquivos.";
      setMultiError(message);
      toast.error(message);
    } finally {
      setMultiPreviewLoading(false);
    }
  }

  async function onUpload() {
    if (!file || !preview || !preview.can_import || mappingDirty || !confirmedImportPolicy) return;
    setUploadLoading(true);
    setErrorMessage(null);
    try {
      const response = await api.upload(file, autoScore, mapping, selectedSheet);
      setResult(response);
      toast.success(response.message || "Importação processada.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["risk-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["risk-critical"] }),
        queryClient.invalidateQueries({ queryKey: ["students"] }),
        queryClient.invalidateQueries({ queryKey: ["students-home"] }),
        queryClient.invalidateQueries({ queryKey: ["upload-history"] }),
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Não foi possível importar o arquivo.";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setUploadLoading(false);
    }
  }

  async function confirmMultipleFiles() {
    if (!multiPreview || !multiIdempotencyKey || !multiFiles.length || !multiConfirmedPolicy) return;
    if (multiPreview.items.some((item) => !item.valid) || (multiPreview.conflicts?.length || 0) || (multiPreview.duplicate_matriculas?.length || 0)) {
      toast.error("Resolva os erros e conflitos antes de confirmar.");
      return;
    }
    setMultiConfirmationLoading(true);
    setMultiError(null);
    try {
      const response = await api.confirmMultipleUploads(multiFiles, multiRoles, multiIdempotencyKey);
      toast.success(response.message || "Bases importadas com sucesso.");
      setMultiPreview(null);
      setMultiFiles([]);
      setMultiRoles([]);
      setMultiIdempotencyKey(null);
      setMultiConfirmedPolicy(false);
      if (multiInputRef.current) multiInputRef.current.value = "";
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["risk-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["risk-critical"] }),
        queryClient.invalidateQueries({ queryKey: ["students"] }),
        queryClient.invalidateQueries({ queryKey: ["students-home"] }),
        queryClient.invalidateQueries({ queryKey: ["upload-history"] }),
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Não foi possível confirmar a importação.";
      setMultiError(message);
      toast.error(message);
    } finally {
      setMultiConfirmationLoading(false);
    }
  }

  const previewMap = preview?.mapped_columns || {};
  const mappingDirty = Boolean(preview) && (preview?.columns || []).some((column) => (mapping[column.key] || "") !== (previewMap[column.key] || ""));
  const canImport = Boolean(preview?.can_import) && !mappingDirty && confirmedImportPolicy && !uploadLoading && !previewLoading;
  const canConfirmMultiple = Boolean(multiPreview && multiFiles.length && multiIdempotencyKey && multiConfirmedPolicy) &&
    !multiPreviewLoading && !multiConfirmationLoading && !multiPreview?.items.some((item) => !item.valid) &&
    !(multiPreview?.conflicts?.length) && !(multiPreview?.duplicate_matriculas?.length);

  function clearSingle() {
    setFile(null); setMapping({}); setStructure(null); setSelectedSheet(""); setPreview(null); setResult(null); setErrorMessage(null); setConfirmedImportPolicy(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault(); setDragging(false);
    if (mode === "single") selectFile(event.dataTransfer.files?.[0]);
    else selectMultipleFiles(event.dataTransfer.files);
  }

  return (
    <>
      <Header title="Importar dados" subtitle="Envie sua base, confira os dados e importe com segurança." />
      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 pb-12 pt-6 md:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">DADOS E INTEGRAÇÕES</p>
          <Button variant="ghost" size="sm" onClick={() => router.push("/importacoes")}><History className="h-4 w-4" /> Histórico de importações</Button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" onClick={() => setMode("single")} className={`rounded-2xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${mode === "single" ? "border-neutral-900 bg-neutral-50 shadow-sm" : "border-border bg-white hover:border-neutral-400"}`}>
            <span className="flex items-center gap-2 text-sm font-semibold text-foreground"><FileSpreadsheet className="h-4 w-4" /> Importação rápida</span>
            <span className="mt-2 block text-sm text-muted-foreground">Uma planilha com os dados dos alunos.</span>
            <span className="mt-3 block text-xs font-medium text-foreground">{mode === "single" ? "Selecionada" : "Selecionar uma planilha"}</span>
          </button>
          <button type="button" onClick={() => setMode("multiple")} className={`rounded-2xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${mode === "multiple" ? "border-neutral-900 bg-neutral-50 shadow-sm" : "border-border bg-white hover:border-neutral-400"}`}>
            <span className="flex items-center gap-2 text-sm font-semibold text-foreground"><Files className="h-4 w-4" /> Importação completa</span>
            <span className="mt-2 block text-sm text-muted-foreground">Combine bases relacionadas em uma operação.</span>
            <span className="mt-3 block text-xs font-medium text-foreground">{mode === "multiple" ? "Selecionada" : "Adicionar vários arquivos"}</span>
          </button>
        </div>

        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-lg">{mode === "single" ? "Sua planilha" : "Seus arquivos"}</CardTitle>
            <CardDescription>{mode === "single" ? "Formatos aceitos: CSV, XLS e XLSX · até 50 MB." : "Adicione até 10 arquivos CSV ou Excel, com limite total de 50 MB."}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(event: ChangeEvent<HTMLInputElement>) => selectFile(event.target.files?.[0])} />
            <input ref={multiInputRef} type="file" accept=".csv,.xlsx,.xls" multiple className="hidden" onChange={(event: ChangeEvent<HTMLInputElement>) => selectMultipleFiles(event.target.files || [])} />
            <label
              onClick={(event) => { event.preventDefault(); (mode === "single" ? inputRef.current : multiInputRef.current)?.click(); }}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={`flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-4 py-6 text-center transition ${dragging ? "border-primary bg-primary/5" : "border-neutral-300 hover:border-neutral-500 hover:bg-neutral-50"}`}
            >
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-muted"><UploadCloud className="h-5 w-5 text-foreground" /></span>
              <span className="mt-3 text-sm font-semibold text-foreground">Arraste os arquivos até aqui</span>
              <span className="mt-1 text-xs text-muted-foreground">ou clique para procurar no computador</span>
            </label>

            {mode === "single" ? (
              file ? (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border px-3.5 py-3">
                  <div className="flex min-w-0 items-center gap-3"><FileSpreadsheet className="h-5 w-5 shrink-0 text-muted-foreground" /><div className="min-w-0"><p className="break-all text-sm font-medium">{file.name}</p><p className="text-xs text-muted-foreground">{formatSize(file.size)}</p></div></div>
                  <Button variant="ghost" size="sm" onClick={clearSingle}><Trash2 className="h-4 w-4" /> Remover</Button>
                </div>
              ) : <p className="text-center text-xs text-muted-foreground">Nenhum arquivo selecionado.</p>
            ) : (
              <div className="space-y-2">
                {multiFiles.map((item, index) => (
                  <div key={item.name + item.size + item.lastModified} className="flex flex-col gap-2 rounded-xl border border-border px-3.5 py-3 sm:flex-row sm:items-center">
                    <FileSpreadsheet className="hidden h-5 w-5 shrink-0 text-muted-foreground sm:block" />
                    <div className="min-w-0 flex-1"><p className="break-all text-sm font-medium">{item.name}</p><p className="text-xs text-muted-foreground">{formatSize(item.size)}</p></div>
                    <select aria-label={`Tipo da base ${item.name}`} value={multiRoles[index] || "cadastro"} onChange={(event) => { setMultiRoles((current) => current.map((role, i) => i === index ? event.target.value : role)); setMultiPreview(null); setMultiConfirmedPolicy(false); }} className="h-9 rounded-lg border border-border bg-white px-2 text-xs">
                      <option value="cadastro">Cadastro de alunos</option><option value="financeiro">Financeiro</option><option value="academico">Acadêmico</option><option value="historico">Histórico acadêmico</option><option value="matriculas">Matrículas</option>
                    </select>
                    <Button variant="ghost" size="sm" onClick={() => { setMultiFiles((current) => current.filter((_, i) => i !== index)); setMultiRoles((current) => current.filter((_, i) => i !== index)); setMultiPreview(null); setMultiConfirmedPolicy(false); }}><Trash2 className="h-4 w-4" /><span className="sm:hidden">Remover</span></Button>
                  </div>
                ))}
                {multiFiles.length > 0 && <Button variant="outline" size="sm" onClick={() => multiInputRef.current?.click()}><Files className="h-4 w-4" /> Adicionar outro arquivo</Button>}
              </div>
            )}

            {mode === "single" ? (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
                <Button variant="ghost" size="sm" onClick={downloadTemplate}>Baixar modelo CSV</Button>
                <Button onClick={() => void analyzeFile()} disabled={!file || previewLoading || uploadLoading}>
                  {previewLoading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />} {previewLoading ? "Inspecionando..." : "Inspecionar estrutura"}
                </Button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
                <p className="text-xs text-muted-foreground">A MIRA vai validar cada arquivo antes de gravar qualquer dado.</p>
                <Button onClick={() => void analyzeMultipleFiles()} disabled={!multiFiles.length || multiPreviewLoading || multiConfirmationLoading}>
                  {multiPreviewLoading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />} {multiPreviewLoading ? "Analisando..." : "Analisar arquivos"}
                </Button>
              </div>
            )}

            {(errorMessage || multiError) && <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{errorMessage || multiError}</div>}

            {mode === "single" && structure && !result && (
              <section className="space-y-4 border-t border-border pt-5">
                <div>
                  <h2 className="text-base font-semibold">Confira a estrutura do arquivo</h2>
                  <p className="mt-1 text-xs text-muted-foreground">A MIRA identifica as abas e mostra exemplos antes de validar os alunos. Nenhum dado foi salvo.</p>
                </div>
                {structure.sheets.length > 1 ? (
                  <div className="space-y-2">
                    <label htmlFor="sheet-name" className="text-sm font-medium">Aba que contém os dados</label>
                    <select id="sheet-name" value={selectedSheet} onChange={(event) => { setSelectedSheet(event.target.value); setPreview(null); setConfirmedImportPolicy(false); }} className="h-10 w-full rounded-lg border border-border bg-white px-3 text-sm">
                      {structure.sheets.map((sheet) => <option key={sheet.name} value={sheet.name}>{sheet.name} · {sheet.rows} linhas · {sheet.columns.length} colunas{sheet.required_fields_found ? " · cadastro reconhecido" : ""}</option>)}
                    </select>
                  </div>
                ) : <p className="text-sm text-muted-foreground">Aba identificada: <strong>{selectedSheet}</strong></p>}
                {(() => {
                  const sheet = structure.sheets.find((item) => item.name === selectedSheet);
                  if (!sheet) return <p className="text-sm text-amber-800">Selecione uma aba válida para continuar.</p>;
                  const statusClass = sheet.required_fields_found ? "bg-emerald-50 text-emerald-800" : sheet.tabular ? "bg-amber-50 text-amber-800" : "bg-red-50 text-red-800";
                  const statusLabel = sheet.required_fields_found ? "Matrícula e nome reconhecidos" : sheet.tabular ? "Confira os cabeçalhos" : "Aba possivelmente explicativa";
                  return (
                    <div className="space-y-3 rounded-xl border border-border p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={"rounded-full px-2.5 py-1 text-xs font-medium " + statusClass}>{statusLabel}</span>
                        <span className="text-xs text-muted-foreground">{sheet.rows} linhas de dados</span>
                      </div>
                      <div><p className="text-xs font-medium text-muted-foreground">Cabeçalhos detectados</p><div className="mt-2 flex flex-wrap gap-1.5">{sheet.columns.map((column) => <span key={column} className="rounded-md bg-muted px-2 py-1 text-xs">{column}</span>)}</div></div>
                      {sheet.sample_rows.length > 0 && <div className="overflow-x-auto rounded-lg border border-border"><table className="w-full min-w-[500px] text-left text-xs"><thead className="bg-muted/50"><tr>{sheet.columns.map((column) => <th key={column} className="px-3 py-2 font-medium text-muted-foreground">{column}</th>)}</tr></thead><tbody className="divide-y divide-border">{sheet.sample_rows.map((row, index) => <tr key={index}>{sheet.columns.map((column) => <td key={column} className="max-w-48 truncate px-3 py-2">{row[column] || "—"}</td>)}</tr>)}</tbody></table></div>}
                      {!sheet.required_fields_found && <p className="text-xs text-amber-900">Não encontramos automaticamente matrícula e nome nesta aba. Escolha outra aba ou continue para mapear manualmente; a importação ficará bloqueada até os campos obrigatórios serem identificados.</p>}
                    </div>
                  );
                })()}
                <div className="flex justify-end"><Button onClick={() => void validateSelectedSheet()} disabled={!selectedSheet || previewLoading || !structure.sheets.some((sheet) => sheet.name === selectedSheet)}><ArrowRight className="h-4 w-4" /> {previewLoading ? "Validando..." : "Validar dados desta aba"}</Button></div>
              </section>
            )}

            {mode === "single" && preview && !result && (
              <section className="space-y-5 border-t border-border pt-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><h2 className="text-base font-semibold">Revise os dados</h2><p className="mt-1 text-xs text-muted-foreground">Esta análise não altera sua base.</p></div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${preview.can_import ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}>{preview.can_import ? "Pronta para revisar" : "Campos obrigatórios pendentes"}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Stat label="Linhas recebidas" value={preview.rows_received} />
                  <Stat label="Para importar" value={preview.rows_to_import} />
                  <Stat label="Duplicatas" value={preview.duplicates_in_file} />
                  <Stat label="Registros existentes" value={preview.existing_matches} />
                </div>
                {preview.missing_required_columns.length > 0 && <Notice tone="error" title="Campos obrigatórios ausentes" text={preview.missing_required_columns.map((field) => preview.field_labels[field as ImportField] || field).join(", ")} />}
                {preview.invalid_rows_count > 0 && <Notice tone="warning" title={`${number(preview.invalid_rows_count)} linhas precisam de atenção`} text={preview.invalid_rows.slice(0, 4).map((row) => `Linha ${row.line}: ${row.message}`).join(" · ")} />}
                {preview.warnings.length > 0 && <Notice tone="info" title="Pontos para revisar" text={preview.warnings.slice(0, 4).join(" · ")} />}
                <div className="space-y-3">
                  <div><h3 className="text-sm font-semibold">Conferir colunas</h3><p className="mt-1 text-xs text-muted-foreground">Revise apenas as correspondências que precisam de ajuste.</p></div>
                  <div className="divide-y divide-border rounded-xl border border-border">
                    {preview.columns.map((column) => <div key={column.key} className="grid gap-2 px-3 py-3 sm:grid-cols-[1fr_1fr] sm:items-center">
                      <div className="min-w-0"><p className="break-all text-sm font-medium">{column.label}</p><p className="mt-0.5 truncate text-xs text-muted-foreground">Exemplo: {column.sample || "—"}</p></div>
                      <select aria-label={`Campo MIRA para ${column.label}`} value={mapping[column.key] || ""} onChange={(event) => { setMapping((current) => ({ ...current, [column.key]: event.target.value })); setConfirmedImportPolicy(false); }} className="h-9 w-full rounded-lg border border-border bg-white px-2 text-sm">
                        <option value="">Não importar esta coluna</option>
                        {IMPORT_FIELDS.map((field) => <option key={field} value={field}>{FIELD_LABELS[field]}{Object.entries(mapping).some(([key, value]) => key !== column.key && value === field) ? " · já selecionado" : ""}</option>)}
                      </select>
                    </div>)}
                  </div>
                  {mappingDirty && <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900"><span>Você alterou o mapeamento. Reanalise antes de continuar.</span><Button size="sm" variant="outline" onClick={() => void validateSelectedSheet(mapping)} disabled={previewLoading}><RefreshCw className="h-3.5 w-3.5" /> Reanalisar</Button></div>}
                </div>
                {preview.sample_rows.length > 0 && <div className="space-y-2"><h3 className="text-sm font-semibold">Amostra dos registros</h3><div className="overflow-x-auto rounded-xl border border-border"><table className="w-full min-w-[620px] text-left text-xs"><thead className="bg-muted/50"><tr>{["Matrícula","Nome","Curso","Semestre","Presença"].map((label) => <th key={label} className="px-3 py-2.5 font-medium text-muted-foreground">{label}</th>)}</tr></thead><tbody className="divide-y divide-border">{preview.sample_rows.slice(0, 5).map((row, i) => <tr key={String(row.matricula || i)}><td className="px-3 py-2">{String(row.matricula ?? "—")}</td><td className="px-3 py-2">{String(row.nome ?? "—")}</td><td className="px-3 py-2">{String(row.curso ?? "—")}</td><td className="px-3 py-2">{String(row.semestre ?? "—")}</td><td className="px-3 py-2">{row.presenca_percentual == null ? "—" : `${row.presenca_percentual}%`}</td></tr>)}</tbody></table></div></div>}
                <div className="space-y-3 rounded-xl bg-muted/40 p-4">
                  <label className="flex items-start gap-2.5 text-sm"><input type="checkbox" checked={autoScore} onChange={(event) => setAutoScore(event.target.checked)} className="mt-0.5 accent-neutral-900" /><span><strong className="font-medium">Calcular risco após importar</strong><span className="mt-0.5 block text-xs text-muted-foreground">Atualiza os indicadores da MIRA depois do processamento.</span></span></label>
                  <label className="flex items-start gap-2.5 text-sm"><input type="checkbox" checked={confirmedImportPolicy} onChange={(event) => setConfirmedImportPolicy(event.target.checked)} disabled={uploadLoading || previewLoading || mappingDirty || !preview.can_import} className="mt-0.5 accent-neutral-900" /><span><strong className="font-medium">Revisei as regras de atualização</strong><span className="mt-0.5 block text-xs text-muted-foreground">Matrículas existentes serão atualizadas; células vazias preservam os valores atuais. Linhas inválidas não serão importadas e duplicatas por matrícula serão consolidadas.</span></span></label>
                </div>
                <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck className="h-4 w-4 shrink-0" /> Nada é salvo antes da confirmação.</p><Button onClick={() => void onUpload()} disabled={!canImport}>{uploadLoading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}{uploadLoading ? "Importando..." : `Confirmar importação · ${number(preview.rows_to_import)} registros`}</Button></div>
              </section>
            )}

            {mode === "multiple" && multiPreview && (
              <section className="space-y-4 border-t border-border pt-5">
                <div><h2 className="text-base font-semibold">Resumo da análise</h2><p className="mt-1 text-xs text-muted-foreground">Prévia calculada pelo servidor. Nenhum dado foi gravado.</p></div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4"><Stat label="Arquivos válidos" value={multiPreview.summary.files_valid} /><Stat label="Com erros" value={multiPreview.summary.files_with_errors} /><Stat label="Matrículas identificadas" value={multiPreview.summary.distinct_matriculas_across_files} /><Stat label="Conflitos" value={(multiPreview.conflicts?.length || 0) + (multiPreview.duplicate_matriculas?.length || 0)} /></div>
                <div className="space-y-2">{multiPreview.items.map((item) => <div key={item.index} className="flex items-start gap-3 rounded-xl border border-border p-3"><span className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg ${item.valid ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>{item.valid ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}</span><div className="min-w-0 flex-1"><p className="break-all text-sm font-medium">{item.filename}</p><p className="mt-1 text-xs text-muted-foreground">{item.total_rows == null ? "Linhas não informadas" : `${number(item.total_rows)} linhas`} · {item.role || "Tipo não identificado"}</p>{item.errors?.length ? <p className="mt-1 text-xs text-red-700">{item.errors.join(" · ")}</p> : null}{item.warnings?.length ? <p className="mt-1 text-xs text-amber-800">{item.warnings.join(" · ")}</p> : null}</div></div>)}</div>
                {(multiPreview.conflicts?.length || multiPreview.duplicate_matriculas?.length) ? <Notice tone="error" title="É necessário resolver os conflitos" text="Há matrículas duplicadas ou valores divergentes entre arquivos. A confirmação fica bloqueada para evitar combinar registros incorretamente." /> : null}
                <label className="flex items-start gap-2.5 rounded-xl bg-muted/40 p-3 text-sm"><input type="checkbox" checked={multiConfirmedPolicy} onChange={(event) => setMultiConfirmedPolicy(event.target.checked)} className="mt-0.5 accent-neutral-900" /><span><strong className="font-medium">Revisei os arquivos e seus tipos</strong><span className="mt-0.5 block text-xs text-muted-foreground">Confirmo que os arquivos selecionados e as regras de relacionamento estão corretos.</span></span></label>
                <div className="flex justify-end border-t border-border pt-4"><Button onClick={() => void confirmMultipleFiles()} disabled={!canConfirmMultiple}>{multiConfirmationLoading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}{multiConfirmationLoading ? "Importando..." : "Confirmar importação"}</Button></div>
              </section>
            )}

            {mode === "single" && result && (
              <section className="space-y-4 border-t border-border pt-5">
                <div className="flex items-start gap-3"><CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" /><div><h2 className="text-base font-semibold">{(result.quality?.rows_discarded ?? 0) > 0 ? "Importação concluída com ressalvas" : "Importação concluída"}</h2><p className="mt-1 text-sm text-muted-foreground">{result.message || "O processamento terminou."}</p></div></div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4"><Stat label="Processados" value={result.students_imported} /><Stat label="Novos" value={result.quality?.rows_created} /><Stat label="Atualizados" value={result.quality?.rows_updated} /><Stat label="Descartados" value={result.quality?.rows_discarded} /></div>
                {result.quality?.warnings?.length ? <Notice tone="warning" title="Pontos para revisar" text={result.quality.warnings.slice(0, 5).join(" · ")} /> : null}
                <div className="flex flex-wrap gap-2"><Button onClick={() => router.push("/")}>Ver painel <ArrowRight className="h-4 w-4" /></Button><Button variant="outline" onClick={() => router.push("/importacoes")}>Ver histórico</Button><Button variant="outline" onClick={clearSingle}>Importar outra planilha</Button></div>
              </section>
            )}
          </CardContent>
        </Card>
        <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" /> A importação usa a sessão autenticada da instituição. A MIRA valida os dados antes de gravar e mantém o histórico das operações.</p>
      </main>
    </>
  );
}

function Stat({ label, value }: { label: string; value?: number | null }) {
  return <div className="rounded-xl border border-border bg-white p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-xl font-semibold tracking-tight tabular-nums">{value == null ? "—" : number(value)}</p></div>;
}

function Notice({ tone, title, text }: { tone: "error" | "warning" | "info"; title: string; text: string }) {
  const styles = { error: "border-red-200 bg-red-50 text-red-900", warning: "border-amber-200 bg-amber-50 text-amber-950", info: "border-blue-200 bg-blue-50 text-blue-950" };
  return <div className={`rounded-xl border px-3.5 py-3 ${styles[tone]}`}><p className="text-sm font-semibold">{title}</p><p className="mt-1 text-xs leading-relaxed opacity-80">{text}</p></div>;
}
