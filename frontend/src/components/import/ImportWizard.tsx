"use client";

import { ChangeEvent, DragEvent, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft, ArrowRight, CheckCircle2, FileSpreadsheet, Files, History,
  ShieldCheck, Trash2, UploadCloud,
} from "lucide-react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Stepper } from "@/components/ui/stepper";
import { ProgressiveFluxLoader, type FluxPhase } from "@/components/ui/progressive-flux-loader";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import type {
  UploadPreviewResponse, UploadResponse, MultiUploadPreviewResponse, UploadStructureResponse,
} from "@/types/api";
import {
  IMPORT_FIELDS, FIELD_LABELS, IMPORT_STEPS, downloadImportTemplate,
  isSupportedImportFile, formatFileSize, ImportStat as Stat, ImportNotice as Notice,
} from "@/components/import/import-helpers";

export function ImportWizard() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const multiInputRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<"single" | "multiple">("single");
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<UploadPreviewResponse | null>(null);
  const [structure, setStructure] = useState<UploadStructureResponse | null>(null);
  const [selectedSheet, setSelectedSheet] = useState("");
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
  const [multiResultMessage, setMultiResultMessage] = useState<string | null>(null);

  const fluxPhase: FluxPhase = useMemo(() => {
    if (errorMessage || multiError) return "error";
    if ((result || multiResultMessage) && step === 5) return "success";
    if (previewLoading || multiPreviewLoading)
      return !structure && mode === "single" ? "validating_structure" : "analyzing";
    if (uploadLoading) return autoScore ? "scoring" : "preparing";
    if (multiConfirmationLoading) return "preparing";
    return "idle";
  }, [errorMessage, multiError, result, multiResultMessage, step, previewLoading, multiPreviewLoading, structure, mode, uploadLoading, autoScore, multiConfirmationLoading]);

  function resetSingleDownstream() {
    setMapping({}); setStructure(null); setSelectedSheet(""); setPreview(null);
    setResult(null); setErrorMessage(null); setConfirmedImportPolicy(false);
  }

  function selectFile(nextFile?: File) {
    if (!nextFile) return;
    if (!isSupportedImportFile(nextFile)) return void toast.error("Escolha CSV ou Excel (.xlsx, .xls).");
    if (nextFile.size > 50 * 1024 * 1024) return void toast.error("O arquivo excede 50 MB.");
    setFile(nextFile); resetSingleDownstream(); setStep(0);
  }

  function selectMultipleFiles(files: FileList | File[]) {
    const selected = Array.from(files);
    if (!selected.length) return;
    if (selected.length > 10) return void toast.error("Máximo 10 arquivos.");
    if (selected.find((f) => !isSupportedImportFile(f))) return void toast.error("Apenas CSV/Excel.");
    if (
      selected.some((f) => f.size > 50 * 1024 * 1024) ||
      selected.reduce((s, f) => s + f.size, 0) > 50 * 1024 * 1024
    ) {
      return void toast.error("Limite total 50 MB.");
    }

    const merged = [...multiFiles];
    selected.forEach((item) => {
      if (
        !merged.some(
          (e) => e.name === item.name && e.size === item.size && e.lastModified === item.lastModified
        )
      ) {
        merged.push(item);
      }
    });
    if (merged.length > 10) {
      toast.error("Máximo 10 arquivos.");
      return;
    }

    const nextRoles = merged.map((_, i) => multiRoles[i] || (i === 0 ? "cadastro" : "financeiro"));
    setMultiFiles(merged);
    setMultiRoles(nextRoles);
    setMultiPreview(null);
    setMultiIdempotencyKey(crypto.randomUUID());
    setMultiConfirmedPolicy(false);
    setMultiError(null);
    setMultiResultMessage(null);
    setStep(0);
  }

  async function analyzeFile() {
    if (!file) return false;
    setPreviewLoading(true); setErrorMessage(null); setPreview(null);
    try {
      const response = await api.inspectUploadStructure(file);
      setStructure(response);
      setSelectedSheet(response.suggested_sheet || response.sheets[0]?.name || "");
      setMapping({}); setConfirmedImportPolicy(false);
      toast.success("Estrutura identificada.");
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha ao inspecionar.";
      setErrorMessage(message); toast.error(message); return false;
    } finally { setPreviewLoading(false); }
  }

  async function validateSelectedSheet(nextMapping?: Record<string, string>) {
    if (!file || !selectedSheet) return false;
    setPreviewLoading(true); setErrorMessage(null);
    try {
      const response = await api.previewUpload(file, nextMapping, selectedSheet);
      setPreview(response);
      setMapping(Object.fromEntries(response.columns.map((c) => [c.key, response.mapped_columns[c.key] || ""])));
      setConfirmedImportPolicy(false);
      if (!response.can_import)
        toast.error(response.missing_required_columns.length ? "Faltam campos obrigatórios." : "Nenhuma linha segura para importar.");
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha ao validar.";
      setErrorMessage(message); toast.error(message); return false;
    } finally { setPreviewLoading(false); }
  }

  async function analyzeMultipleFiles() {
    if (!multiFiles.length) return false;
    setMultiPreviewLoading(true); setMultiError(null);
    try {
      setMultiPreview(await api.previewMultipleUploads(multiFiles, multiRoles));
      toast.success("Análise concluída. Nada foi salvo.");
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha na análise.";
      setMultiError(message); toast.error(message); return false;
    } finally { setMultiPreviewLoading(false); }
  }

  async function onUpload() {
    if (!file || !preview || !preview.can_import || mappingDirty || !confirmedImportPolicy || uploadLoading) return;
    setUploadLoading(true); setErrorMessage(null);
    try {
      const response = await api.upload(file, autoScore, mapping, selectedSheet);
      setResult(response); setStep(5);
      toast.success(response.message || "Importação processada.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["risk-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["risk-critical"] }),
        queryClient.invalidateQueries({ queryKey: ["students"] }),
        queryClient.invalidateQueries({ queryKey: ["students-home"] }),
        queryClient.invalidateQueries({ queryKey: ["upload-history"] }),
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha na importação.";
      setErrorMessage(message); toast.error(message);
    } finally { setUploadLoading(false); }
  }

  async function confirmMultipleFiles() {
    if (!multiPreview || !multiIdempotencyKey || !multiFiles.length || !multiConfirmedPolicy || multiConfirmationLoading) return;
    if (multiPreview.items.some((i) => !i.valid) || multiPreview.conflicts?.length || multiPreview.duplicate_matriculas?.length) {
      toast.error("Resolva erros e conflitos antes de confirmar.");
      return;
    }
    setMultiConfirmationLoading(true); setMultiError(null);
    try {
      const response = await api.confirmMultipleUploads(multiFiles, multiRoles, multiIdempotencyKey);
      setMultiResultMessage(response.message || "Bases importadas.");
      setStep(5);
      toast.success(response.message || "Bases importadas.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["risk-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["risk-critical"] }),
        queryClient.invalidateQueries({ queryKey: ["students"] }),
        queryClient.invalidateQueries({ queryKey: ["students-home"] }),
        queryClient.invalidateQueries({ queryKey: ["upload-history"] }),
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha ao confirmar.";
      setMultiError(message); toast.error(message);
    } finally { setMultiConfirmationLoading(false); }
  }

  const previewMap = preview?.mapped_columns || {};
  const mappingDirty = Boolean(preview) && (preview?.columns || []).some((c) => (mapping[c.key] || "") !== (previewMap[c.key] || ""));
  const canImport = Boolean(preview?.can_import) && !mappingDirty && confirmedImportPolicy && !uploadLoading && !previewLoading;
  const canConfirmMultiple =
    Boolean(multiPreview && multiFiles.length && multiIdempotencyKey && multiConfirmedPolicy) &&
    !multiPreviewLoading && !multiConfirmationLoading &&
    !multiPreview?.items.some((i) => !i.valid) &&
    !(multiPreview?.conflicts?.length) && !(multiPreview?.duplicate_matriculas?.length);

  function clearAll() {
    setFile(null); resetSingleDownstream();
    setMultiFiles([]); setMultiRoles([]); setMultiPreview(null); setMultiIdempotencyKey(null);
    setMultiConfirmedPolicy(false); setMultiError(null); setMultiResultMessage(null); setStep(0);
    if (inputRef.current) inputRef.current.value = "";
    if (multiInputRef.current) multiInputRef.current.value = "";
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault(); setDragging(false);
    if (mode === "single") selectFile(event.dataTransfer.files?.[0]);
    else selectMultipleFiles(event.dataTransfer.files);
  }

  async function goNext() {
    if (mode === "single") {
      if (step === 0) { if (!file) return void toast.error("Selecione um arquivo."); if (await analyzeFile()) setStep(1); return; }
      if (step === 1) { if (!selectedSheet) return void toast.error("Selecione a aba."); if (await validateSelectedSheet()) setStep(2); return; }
      if (step === 2) {
        if (mappingDirty && !(await validateSelectedSheet(mapping))) return;
        if (!preview) return void toast.error("Valide o mapeamento.");
        setStep(3); return;
      }
      if (step === 3) { if (!preview?.can_import) return void toast.error("Corrija os bloqueios."); setStep(4); return; }
      if (step === 4) { await onUpload(); return; }
    } else {
      if (step === 0) { if (!multiFiles.length) return void toast.error("Adicione arquivos."); if (await analyzeMultipleFiles()) setStep(1); return; }
      if (step === 1 || step === 2) { setStep(3); return; }
      if (step === 3) {
        if (
          !multiPreview ||
          multiPreview.items.some((i) => !i.valid) ||
          (multiPreview.conflicts?.length || 0) > 0 ||
          (multiPreview.duplicate_matriculas?.length || 0) > 0
        ) {
          return void toast.error("Há arquivos inválidos, conflitos ou duplicidades.");
        }
        setStep(4); return;
      }
      if (step === 4) await confirmMultipleFiles();
    }
  }

  const busy = previewLoading || uploadLoading || multiPreviewLoading || multiConfirmationLoading;

  return (
    <>
      <Header title="Importar dados" subtitle="Fluxo guiado: envie, valide, confirme e registre com segurança." />
      <main className="mira-page mx-auto w-full max-w-5xl space-y-6 px-4 pb-12 pt-6 md:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--brand-indigo)]">Dados e integrações</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={downloadImportTemplate}>Baixar modelo CSV</Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push("/importacoes")}><History className="h-4 w-4" /> Histórico</Button>
          </div>
        </div>

        <Card>
          <CardContent className="space-y-5 pt-6">
            <Stepper steps={IMPORT_STEPS} current={step} />
            <ProgressiveFluxLoader
              phase={fluxPhase}
              compact
              errorMessage={errorMessage || multiError}
              detail={
                uploadLoading ? (autoScore ? "Gravando e solicitando pontuação…" : "Gravando sem pontuação automática…")
                : multiConfirmationLoading ? "Confirmando lote (idempotência)…"
                : previewLoading || multiPreviewLoading ? "Consulta à API — sem percentual simulado."
                : undefined
              }
            />
          </CardContent>
        </Card>

        {step === 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">1. Enviar arquivos</CardTitle>
              <CardDescription>CSV, XLS ou XLSX · até 50 MB. Nada é gravado nesta etapa.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-2">
                <button type="button" onClick={() => { setMode("single"); clearAll(); }}
                  className={`rounded-2xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${mode === "single" ? "border-[var(--brand-indigo)] bg-[var(--brand-indigo)]/5" : "border-border bg-white"}`}>
                  <span className="flex items-center gap-2 text-sm font-semibold"><FileSpreadsheet className="h-4 w-4" /> Importação rápida</span>
                  <span className="mt-2 block text-sm text-muted-foreground">Uma planilha de alunos.</span>
                </button>
                <button type="button" onClick={() => { setMode("multiple"); clearAll(); }}
                  className={`rounded-2xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${mode === "multiple" ? "border-[var(--brand-indigo)] bg-[var(--brand-indigo)]/5" : "border-border bg-white"}`}>
                  <span className="flex items-center gap-2 text-sm font-semibold"><Files className="h-4 w-4" /> Importação completa</span>
                  <span className="mt-2 block text-sm text-muted-foreground">Até 10 bases com validação cruzada.</span>
                </button>
              </div>
              <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e: ChangeEvent<HTMLInputElement>) => selectFile(e.target.files?.[0])} />
              <input ref={multiInputRef} type="file" accept=".csv,.xlsx,.xls" multiple className="hidden" onChange={(e: ChangeEvent<HTMLInputElement>) => selectMultipleFiles(e.target.files || [])} />
              <label
                onClick={(e) => { e.preventDefault(); (mode === "single" ? inputRef.current : multiInputRef.current)?.click(); }}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-4 py-6 text-center transition ${dragging ? "border-primary bg-primary/5" : "border-neutral-300 hover:bg-neutral-50"}`}
              >
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-muted"><UploadCloud className="h-5 w-5" /></span>
                <span className="mt-3 text-sm font-semibold">Arraste os arquivos até aqui</span>
                <span className="mt-1 text-xs text-muted-foreground">ou clique para procurar</span>
              </label>
              {mode === "single" ? (
                file ? (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border px-3.5 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <FileSpreadsheet className="h-5 w-5 shrink-0 text-muted-foreground" />
                      <div className="min-w-0"><p className="break-all text-sm font-medium">{file.name}</p><p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p></div>
                    </div>
                    <Button type="button" variant="ghost" size="sm" onClick={clearAll}><Trash2 className="h-4 w-4" /> Remover</Button>
                  </div>
                ) : <EmptyState title="Nenhum arquivo" description="Adicione uma planilha para continuar." />
              ) : (
                <div className="space-y-2">
                  {multiFiles.length === 0 && <EmptyState title="Nenhum arquivo" description="Até 10 arquivos CSV/Excel." />}
                  {multiFiles.map((item, index) => (
                    <div key={item.name + item.size + item.lastModified} className="flex flex-col gap-2 rounded-xl border px-3.5 py-3 sm:flex-row sm:items-center">
                      <div className="min-w-0 flex-1"><p className="break-all text-sm font-medium">{item.name}</p><p className="text-xs text-muted-foreground">{formatFileSize(item.size)}</p></div>
                      <select aria-label={`Tipo ${item.name}`} value={multiRoles[index] || "cadastro"}
                        onChange={(e) => {
                          setMultiRoles((r) => r.map((x, i) => (i === index ? e.target.value : x)));
                          setMultiPreview(null);
                          setMultiConfirmedPolicy(false);
                          setMultiIdempotencyKey(crypto.randomUUID());
                          setMultiError(null);
                        }}
                        className="h-9 rounded-lg border bg-white px-2 text-xs">
                        <option value="cadastro">Cadastro</option><option value="financeiro">Financeiro</option>
                        <option value="academico">Acadêmico</option><option value="historico">Histórico</option><option value="matriculas">Matrículas</option>
                      </select>
                      <Button type="button" variant="ghost" size="sm" onClick={() => {
                        const nextFiles = multiFiles.filter((_, i) => i !== index);
                        const nextRoles = multiRoles.filter((_, i) => i !== index);
                        setMultiFiles(nextFiles);
                        setMultiRoles(nextRoles);
                        setMultiPreview(null);
                        setMultiConfirmedPolicy(false);
                        setMultiIdempotencyKey(nextFiles.length ? crypto.randomUUID() : null);
                        setMultiError(null);
                      }}><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {step === 1 && mode === "single" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">2. Analisar estrutura</CardTitle><CardDescription>Dados da API de inspeção — sem totais inventados.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              {structure ? (
                <>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <Stat label="Abas" value={structure.sheets?.length ?? null} />
                    <Stat label="Colunas (aba)" value={structure.sheets?.find((s) => s.name === selectedSheet)?.columns?.length ?? structure.sheets?.[0]?.columns?.length ?? null} />
                    <div className="rounded-xl border bg-white p-3"><p className="text-xs text-muted-foreground">Arquivo</p><p className="mt-1 truncate text-sm font-semibold">{file?.name}</p></div>
                  </div>
                  {(structure.sheets?.length || 0) > 0 && (
                    <select value={selectedSheet} onChange={(e) => { setSelectedSheet(e.target.value); setPreview(null); }} className="h-10 w-full rounded-lg border bg-white px-3 text-sm" aria-label="Aba">
                      {structure.sheets.map((sheet) => (
                        <option key={sheet.name} value={sheet.name}>{sheet.name}{sheet.columns?.length ? ` (${sheet.columns.length} colunas)` : ""}</option>
                      ))}
                    </select>
                  )}
                </>
              ) : !previewLoading ? <EmptyState title="Sem estrutura" description="Volte e avance para inspecionar." /> : null}
              {errorMessage && <Notice tone="error" title="Falha" text={errorMessage} />}
            </CardContent>
          </Card>
        )}

        {step === 1 && mode === "multiple" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">2. Análise dos arquivos</CardTitle><CardDescription>Preview multiarquivo — nada persistido.</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              {multiPreview?.items?.map((item, idx) => (
                <div key={idx} className="rounded-xl border px-3.5 py-3 text-sm">
                  <p className="font-semibold">{item.filename || multiFiles[idx]?.name || `Arquivo ${idx + 1}`}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{item.valid ? "Válido" : "Bloqueado"}{(item.error || item.errors?.join("; ")) ? ` · ${item.error || item.errors?.join("; ")}` : ""}</p>
                </div>
              ))}
              {multiError && <Notice tone="error" title="Erro" text={multiError} />}
            </CardContent>
          </Card>
        )}

        {step === 2 && mode === "single" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">3. Mapear colunas</CardTitle><CardDescription>Sugestão do backend; revalida se alterar.</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              {!preview ? <EmptyState title="Sem preview" description="Conclua a análise." /> : (
                <>
                  {preview.missing_required_columns?.length ? <Notice tone="error" title="Obrigatórios ausentes" text={preview.missing_required_columns.join(", ")} /> : null}
                  <div className="max-h-80 space-y-2 overflow-y-auto">
                    {preview.columns.map((column) => (
                      <div key={column.key} className="grid gap-2 rounded-xl border px-3 py-2.5 sm:grid-cols-2">
                        <div><p className="text-sm font-medium">{column.key}</p><p className="text-[11px] text-muted-foreground">Coluna do arquivo</p></div>
                        <select value={mapping[column.key] || ""} onChange={(e) => setMapping((m) => ({ ...m, [column.key]: e.target.value }))}
                          className="h-9 rounded-lg border bg-white px-2 text-xs" aria-label={`Mapear ${column.key}`}>
                          <option value="">— ignorar —</option>
                          {IMPORT_FIELDS.map((field) => <option key={field} value={field}>{FIELD_LABELS[field]}</option>)}
                        </select>
                      </div>
                    ))}
                  </div>
                  {mappingDirty && <Notice tone="warning" title="Mapeamento alterado" text="Ao continuar, o preview será revalidado." />}
                </>
              )}
            </CardContent>
          </Card>
        )}

        {step === 2 && mode === "multiple" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">3. Papéis das bases</CardTitle><CardDescription>Defina os tipos na etapa Enviar; o backend resolve o mapeamento por papel.</CardDescription></CardHeader>
            <CardContent><p className="text-sm text-muted-foreground">{multiFiles.length} arquivo(s) no lote.</p></CardContent>
          </Card>
        )}

        {step === 3 && mode === "single" && preview && (
          <Card>
            <CardHeader><CardTitle className="text-lg">4. Revisar qualidade</CardTitle><CardDescription>Indicadores do preview da API.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Stat label="Linhas preview" value={preview.rows_received ?? preview.rows_to_import ?? null} />
                <Stat label="Pode importar" value={preview.can_import ? 1 : 0} />
                <Stat label="Obrig. faltando" value={preview.missing_required_columns?.length ?? 0} />
                <Stat label="Avisos" value={preview.warnings?.length ?? 0} />
              </div>
              {preview.warnings?.length ? <Notice tone="warning" title="Avisos" text={preview.warnings.slice(0, 8).join(" · ")} /> : null}
              {!preview.can_import && <Notice tone="error" title="Bloqueado" text="Corrija mapeamento ou arquivo antes de confirmar." />}
            </CardContent>
          </Card>
        )}

        {step === 3 && mode === "multiple" && multiPreview && (
          <Card>
            <CardHeader><CardTitle className="text-lg">4. Qualidade e conflitos</CardTitle><CardDescription>Duplicidades e validação cruzada da API.</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              {(multiPreview.duplicate_matriculas?.length || 0) > 0 && <Notice tone="warning" title="Matrículas duplicadas" text={multiPreview.duplicate_matriculas!.slice(0, 12).map((d) => (typeof d === "string" ? d : d.matricula)).join(", ")} />}
              {(multiPreview.conflicts?.length || 0) > 0 && <Notice tone="error" title="Conflitos" text={multiPreview.conflicts!.slice(0, 8).map((c) => (typeof c === "string" ? c : c.message)).join(" · ")} />}
              {multiPreview.items.every((i) => i.valid) && !(multiPreview.conflicts?.length || 0) && !(multiPreview.duplicate_matriculas?.length || 0) && (
                <Notice tone="info" title="Lote apto" text="Nenhum bloqueio reportado no preview." />
              )}
            </CardContent>
          </Card>
        )}

        {step === 4 && mode === "single" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">5. Confirmar importação</CardTitle><CardDescription>Gravação definitiva somente após esta confirmação.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-xl border bg-[var(--surface-subtle)] px-4 py-3 text-sm">
                <p>Arquivo: <strong>{file?.name}</strong></p>
                <p className="mt-1 text-muted-foreground">Aba: {selectedSheet || "—"} · Pode importar: {preview?.can_import ? "sim" : "não"}</p>
              </div>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={autoScore} onChange={(e) => setAutoScore(e.target.checked)} />
                <span>Calcular scores automaticamente após gravar (quando o backend suportar).</span>
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={confirmedImportPolicy} onChange={(e) => setConfirmedImportPolicy(e.target.checked)} />
                <span>Confirmo a revisão e autorizo a gravação na base desta instituição.</span>
              </label>
              {!canImport && <Notice tone="warning" title="Incompleto" text="Marque a autorização e resolva bloqueios." />}
            </CardContent>
          </Card>
        )}

        {step === 4 && mode === "multiple" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">5. Confirmar lote</CardTitle>
              <CardDescription>Idempotency-Key: {multiIdempotencyKey ? `${multiIdempotencyKey.slice(0, 8)}…` : "—"}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">{multiFiles.length} arquivo(s). A chave identifica a operação; falha de rede pode reutilizar a mesma chave.</p>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={multiConfirmedPolicy} onChange={(e) => setMultiConfirmedPolicy(e.target.checked)} />
                <span>Autorizo a confirmação e gravação deste lote.</span>
              </label>
            </CardContent>
          </Card>
        )}

        {step === 5 && (
          <Card>
            <CardHeader><CardTitle className="text-lg">6. Resultado</CardTitle><CardDescription>Resposta oficial do backend.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              {result && (
                <>
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />
                    <div>
                      <h2 className="text-base font-semibold">{(result.quality?.rows_discarded ?? 0) > 0 ? "Concluída com ressalvas" : "Importação concluída"}</h2>
                      <p className="mt-1 text-sm text-muted-foreground">{result.message || "Processamento terminou."}</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Stat label="Processados" value={result.students_imported} />
                    <Stat label="Novos" value={result.quality?.rows_created} />
                    <Stat label="Atualizados" value={result.quality?.rows_updated} />
                    <Stat label="Descartados" value={result.quality?.rows_discarded} />
                  </div>
                  {result.quality?.warnings?.length ? <Notice tone="warning" title="Revisar" text={result.quality.warnings.slice(0, 5).join(" · ")} /> : null}
                </>
              )}
              {multiResultMessage && !result && (
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />
                  <div><h2 className="text-base font-semibold">Lote confirmado</h2><p className="mt-1 text-sm text-muted-foreground">{multiResultMessage}</p></div>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button type="button" onClick={() => router.push("/")}>Ver painel <ArrowRight className="h-4 w-4" /></Button>
                <Button type="button" variant="outline" onClick={() => router.push("/importacoes")}>Histórico</Button>
                <Button type="button" variant="outline" onClick={clearAll}>Nova importação</Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step < 5 && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button type="button" variant="outline" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0 || busy}>
              <ArrowLeft className="h-4 w-4" /> Voltar
            </Button>
            <Button type="button" onClick={() => void goNext()}
              disabled={busy || (step === 0 && mode === "single" && !file) || (step === 0 && mode === "multiple" && !multiFiles.length) || (step === 4 && mode === "single" && !canImport) || (step === 4 && mode === "multiple" && !canConfirmMultiple)}>
              {step === 4 ? (busy ? "Processando…" : "Confirmar e gravar") : "Continuar"}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          Sessão autenticada da instituição. Validação antes de gravar, idempotência no lote multiarquivo e histórico das operações.
        </p>
      </main>
    </>
  );
}
