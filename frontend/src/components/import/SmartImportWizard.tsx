"use client"

// Wizard de importação inteligente: preview com dry-run, revisão do de-para
// (fuzzy), criação inline de campos customizados e confirmação idempotente.
// Para adotar: monte esta rota/página e conecte o resultado ao fluxo atual.

import { useMemo, useState } from "react"

import {
  ImportPreview,
  applySmartImport,
  createCustomField,
  previewSmartImport,
} from "@/lib/smart-import-api"

type Phase = "upload" | "mapping" | "applying" | "done"

const TYPE_LABELS: Record<string, string> = {
  text: "Texto",
  integer: "Número inteiro",
  number: "Número",
  boolean: "Sim/Não",
  date: "Data",
  enum: "Lista de opções",
}

export function SmartImportWizard() {
  const [phase, setPhase] = useState<Phase>("upload")
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [creatingFor, setCreatingFor] = useState<string | null>(null)
  const [result, setResult] = useState<Awaited<ReturnType<typeof applySmartImport>> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [mappingValidated, setMappingValidated] = useState(true)
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null)

  const allHeaders = useMemo(
    () => (preview ? Array.from(new Set([...preview.headers, ...Object.keys(preview.suggestions)])) : []),
    [preview],
  )

  async function runPreview(selected: File, selectedMapping?: Record<string, string>) {
    setBusy(true)
    setError(null)
    try {
      const data = await previewSmartImport(selected, selectedMapping)
      setPreview(data)
      setDraft(selectedMapping || Object.fromEntries(Object.entries(data.mapping).map(([h, m]) => [h, m.field])))
      setMappingValidated(true)
      setPhase("mapping")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao analisar o arquivo.")
    } finally {
      setBusy(false)
    }
  }

  async function confirmImport() {
    if (!file || !preview || !confirmed || !mappingValidated || !idempotencyKey || preview.key_stats.valid < 1) return
    setBusy(true)
    setError(null)
    try {
      const outcome = await applySmartImport(file, draft, idempotencyKey)
      setResult(outcome)
      setPhase("done")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao confirmar a importação.")
    } finally {
      setBusy(false)
    }
  }

  async function handleCreateField(header: string, input: { label: string; data_type: string; options?: string[]; is_pii?: boolean }) {
    setBusy(true)
    setConfirmed(false)
    try {
    const created = await createCustomField({
      label: input.label,
      data_type: input.data_type as never,
      options: input.options,
      is_pii: input.is_pii,
      aliases: [header],
    })
    // Preserva o restante do de-para manual durante a criação inline.
    setCreatingFor(null)
    if (file) await runPreview(file, { ...draft, [header]: created.name })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível criar o campo.")
    } finally {
      setBusy(false)
    }
  }

  if (phase === "upload") {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-slate-900">Importação inteligente</h2>
        <p className="mt-1 text-sm text-slate-500">
          Envie a planilha: sugerimos o de-para das colunas, validamos linha a linha e só
          persistimos com a sua confirmação.
        </p>
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          className="mt-4 block w-full text-sm text-slate-600"
          onChange={(event) => {
            const selected = event.target.files?.[0] ?? null
            if (selected && selected.size > 50 * 1024 * 1024) {
              setError("Arquivo excede o limite de 50 MB.")
              return
            }
            setFile(selected)
            setConfirmed(false)
            setIdempotencyKey(selected ? crypto.randomUUID() : null)
            if (selected) void runPreview(selected)
          }}
        />
        {busy && <p className="mt-3 text-sm text-slate-500">Analisando arquivo…</p>}
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>
    )
  }

  if (phase === "done" && result) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-slate-900">Importação concluída</h2>
        <dl className="mt-4 grid grid-cols-3 gap-3 text-center">
          <div className="rounded-xl bg-slate-50 p-3">
            <dt className="text-xs uppercase tracking-wide text-slate-500">Criados</dt>
            <dd className="text-2xl font-semibold text-slate-900">{result.created}</dd>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <dt className="text-xs uppercase tracking-wide text-slate-500">Atualizados</dt>
            <dd className="text-2xl font-semibold text-slate-900">{result.updated}</dd>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <dt className="text-xs uppercase tracking-wide text-slate-500">Rejeitados</dt>
            <dd className="text-2xl font-semibold text-slate-900">{result.rejected}</dd>
          </div>
        </dl>
        <div className="mt-5 flex gap-4 text-sm">
          <a href="/importar" className="text-[#4050CD] underline">Nova importação</a>
          <a href="/importacoes" className="text-[#4050CD] underline">Ver histórico</a>
        </div>
        {result.scoring && (
          <p className={`mt-3 rounded-lg px-3 py-2 text-sm ${result.scoring.error ? "bg-amber-50 text-amber-800" : "bg-slate-50 text-slate-700"}`}>
            {result.scoring.error
              ? "Dados gravados. A pontuação não foi concluída; você poderá recalculá-la depois."
              : `Pontuação: ${result.scoring.scored} alunos avaliados · ${result.scoring.indeterminate_count ?? 0} indeterminados por falta de dados.`}
          </p>
        )}
        {result.row_errors.length > 0 && (
          <details className="mt-4 text-sm text-slate-600">
            <summary className="cursor-pointer">{result.row_errors.length} linhas com alerta</summary>
            <ul className="mt-2 max-h-48 space-y-1 overflow-auto">
              {result.row_errors.slice(0, 20).map((item, i) => (
                <li key={i}>Linha {item.row}: {item.message}</li>
              ))}
            </ul>
          </details>
        )}
      </section>
    )
  }

  if (!preview) return null

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Revise o mapeamento</h2>
          <p className="text-sm text-slate-500">
            {preview.filename} · {preview.total_rows} linhas ·{" "}
            {preview.key_stats.existing} alunos existentes · {preview.key_stats.new} novos
          </p>
        </div>
        <button
          type="button"
          disabled={busy || !confirmed || !mappingValidated || preview.key_stats.valid < 1 || Object.values(draft).filter((field) => field === "matricula").length !== 1}
          onClick={() => void confirmImport()}
          className="rounded-lg bg-[#4050CD] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Importando…" : "Confirmar importação"}
        </button>
      </header>

      {preview.key_stats.invalid > 0 && (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {preview.key_stats.invalid} linhas inválidas (incluindo {preview.key_stats.duplicates} duplicadas) serão rejeitadas.
        </p>
      )}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2 pr-4">Coluna do arquivo</th>
              <th className="py-2 pr-4">Campo na MIRA</th>
              <th className="py-2">Confiança</th>
            </tr>
          </thead>
          <tbody>
            {allHeaders.map((header) => {
              const confidence = preview.mapping[header]?.confidence
              const isKey = header === preview.key_header
              return (
                <tr key={header} className="border-b border-slate-100">
                  <td className="py-2 pr-4 font-medium text-slate-800">
                    {header}
                    {isKey && (
                      <span className="ml-2 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-[#4050CD]">
                        chave
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-4">
                    <select
                      value={draft[header] ?? ""}
                      onChange={(event) => {
                        setDraft((current) => ({ ...current, [header]: event.target.value }))
                        setMappingValidated(false)
                        setConfirmed(false)
                      }}
                      className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
                    >
                      <option value="">— ignorar coluna —</option>
                      {preview.fields.map((entry) => (
                        <option key={entry.field} value={entry.field}>
                          {entry.label} {entry.source === "custom" ? "(custom)" : ""}
                        </option>
                      ))}
                    </select>
                    {creatingFor === header ? (
                      <CreateFieldInline
                        header={header}
                        onCancel={() => setCreatingFor(null)}
                        onCreate={(input) => void handleCreateField(header, input)}
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => setCreatingFor(header)}
                        className="mt-1 text-xs font-medium text-[#4050CD]"
                      >
                        + criar campo customizado
                      </button>
                    )}
                  </td>
                  <td className="py-2">
                    {confidence != null && (
                      <span
                        className={
                          confidence >= 0.85
                            ? "text-emerald-600"
                            : confidence >= 0.55
                              ? "text-amber-600"
                              : "text-slate-400"
                        }
                      >
                        {Math.round(confidence * 100)}%
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {preview.row_errors.length > 0 && (
        <details className="mt-4 text-sm text-amber-800">
          <summary className="cursor-pointer">Ver erros de validação ({preview.row_errors.length} exibidos)</summary>
          <ul className="mt-2 max-h-44 space-y-1 overflow-y-auto">
            {preview.row_errors.map((item, i) => (
              <li key={i}>Linha {item.row}, {item.field}: {item.message}</li>
            ))}
          </ul>
        </details>
      )}
      {!mappingValidated && file && (
        <button type="button" disabled={busy}
          onClick={() => void runPreview(file, draft)}
          className="mt-4 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium">
          {busy ? "Validando…" : "Validar mapeamento ajustado"}
        </button>
      )}
      <label className="mt-5 flex items-start gap-2 text-sm text-slate-600">
        <input type="checkbox" checked={confirmed} disabled={!mappingValidated || busy}
          onChange={(event) => setConfirmed(event.target.checked)} />
        Confirmo que posso importar estes dados para a instituição e revisei os campos e alertas.
      </label>
      <div className="mt-4 flex flex-wrap gap-4 text-xs">
        <a href="/importar/multiplos" className="text-[#4050CD] underline">Importar múltiplas bases</a>
        <a href="/importacoes" className="text-[#4050CD] underline">Histórico de importações</a>
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </section>
  )
}

function CreateFieldInline({
  header,
  onCreate,
  onCancel,
}: {
  header: string
  onCreate: (input: { label: string; data_type: string; options?: string[]; is_pii?: boolean }) => void
  onCancel: () => void
}) {
  const [label, setLabel] = useState(header)
  const [dataType, setDataType] = useState("text")
  const [options, setOptions] = useState("")
  const [isPii, setIsPii] = useState(false)

  return (
    <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
      <label className="block text-xs font-medium text-slate-600">
        Nome do campo
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
      </label>
      <label className="mt-2 block text-xs font-medium text-slate-600">
        Tipo
        <select
          value={dataType}
          onChange={(e) => setDataType(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
        >
          {Object.entries(TYPE_LABELS).map(([value, text]) => (
            <option key={value} value={value}>{text}</option>
          ))}
        </select>
      </label>
      {dataType === "enum" && (
        <label className="mt-2 block text-xs font-medium text-slate-600">
          Opções (separadas por vírgula)
          <input
            value={options}
            onChange={(e) => setOptions(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          />
        </label>
      )}
      <label className="mt-2 flex items-center gap-2 text-xs text-slate-600">
        <input type="checkbox" checked={isPii} onChange={(e) => setIsPii(e.target.checked)} />
        Contém dado pessoal (LGPD)
      </label>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() =>
            onCreate({
              label,
              data_type: dataType,
              options: dataType === "enum" ? options.split(",").map((s) => s.trim()).filter(Boolean) : undefined,
              is_pii: isPii,
            })
          }
          className="rounded-md bg-[#4050CD] px-3 py-1.5 text-xs font-medium text-white"
        >
          Criar e mapear
        </button>
        <button type="button" onClick={onCancel} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs">
          Cancelar
        </button>
      </div>
    </div>
  )
}