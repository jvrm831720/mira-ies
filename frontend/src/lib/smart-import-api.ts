import { getAccessToken, getApiKey } from "./auth"

// Cliente da API de importação inteligente e campos customizados.
// Os caminhos são relativos ao app Next.js, que faz proxy via
// src/app/api/v1/[...path]/route.ts para o backend (mesmo padrão do api.ts).

export interface MappingEntry {
  field: string
  label: string
  source: "standard" | "custom"
  confidence: number
}

export interface ImportPreview {
  filename: string
  total_rows: number
  key_field: string
  headers: string[]
  fields: Array<{ field: string; label: string; source: "standard" | "custom"; data_type: string; is_pii: boolean }>
  key_header: string | null
  mapping: Record<string, MappingEntry>
  suggestions: Record<string, MappingEntry[]>
  unmapped_columns: string[]
  row_errors: Array<{ row: number; field: string; message: string }>
  key_stats: { valid: number; invalid: number; duplicates: number; existing: number; new: number }
  sample_rows: Array<Record<string, string>>
}

export interface ImportApplyResult {
  batch_id: string
  idempotent_replay: boolean
  created: number
  updated: number
  rejected: number
  rejected_rows: Array<{ row: number; key: string; message: string }>
  row_errors: Array<{ row: number; field: string; message: string }>
}

export interface CustomFieldDefinition {
  id: string
  target: string
  name: string
  label: string
  data_type: "text" | "integer" | "number" | "boolean" | "date" | "enum"
  options: string[]
  required: boolean
  is_pii: boolean
  aliases: string[]
  active: boolean
}

const BASE = process.env.NODE_ENV === "development"
  ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  : ""

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const token = getAccessToken()
  const key = getApiKey()
  if (token) headers.set("Authorization", `Bearer ${token}`)
  else if (key) headers.set("X-API-Key", key)
  const response = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!response.ok) {
    let detail: unknown = response.statusText
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      /* mantém statusText */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail))
  }
  return response.json() as Promise<T>
}

export function previewSmartImport(file: File, mapping?: Record<string, string>): Promise<ImportPreview> {
  const form = new FormData()
  form.append("file", file)
  if (mapping) form.append("mapping_payload", JSON.stringify({ mapping, key_field: "matricula" }))
  return request<ImportPreview>("/api/v1/import/preview", { method: "POST", body: form })
}

export function applySmartImport(
  file: File,
  mapping: Record<string, string>,
  idempotencyKey: string,
  keyField = "matricula",
): Promise<ImportApplyResult> {
  const form = new FormData()
  form.append("file", file)
  form.append("payload", JSON.stringify({ mapping, key_field: keyField }))
  return request<ImportApplyResult>("/api/v1/import/apply", {
    method: "POST",
    body: form,
    headers: { "Idempotency-Key": idempotencyKey },
  })
}

export function listCustomFields(): Promise<{ items: CustomFieldDefinition[] }> {
  return request("/api/v1/custom-fields?target=student")
}

export function createCustomField(input: {
  label: string
  data_type: CustomFieldDefinition["data_type"]
  options?: string[]
  is_pii?: boolean
  aliases?: string[]
}): Promise<CustomFieldDefinition> {
  return request("/api/v1/custom-fields", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  })
}
