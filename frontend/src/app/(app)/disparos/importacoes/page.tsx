"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Header } from "@/components/layout/header";
import { dispatchApi, type ComposioImportHistory, type DispatchSource } from "@/lib/dispatch-api";

export default function DispatchComposioImportsPage() {
  const [sources, setSources] = useState<DispatchSource[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [toolSlug, setToolSlug] = useState("");
  const [argumentsText, setArgumentsText] = useState("{}");
  const [rowsPath, setRowsPath] = useState("items");
  const [recordField, setRecordField] = useState("id");
  const [subjectField, setSubjectField] = useState("id");
  const [subjectType, setSubjectType] = useState<"student" | "external">("external");
  const [recordType, setRecordType] = useState<"contact" | "obligation" | "generic">("contact");
  const [fieldsText, setFieldsText] = useState('{"name":"name","email":"email"}');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState<ComposioImportHistory[]>([]);
  const [summary, setSummary] = useState<Array<{
    toolkit_slug: string; tool_slug: string; record_type: string;
    records: number; last_observed_at: string;
  }>>([]);
  const [error, setError] = useState<string | null>(null);
  const idempotencyRef = useRef<string>("");

  const refresh = useCallback(async () => {
    const result = await Promise.allSettled([
      dispatchApi.sources(),
      dispatchApi.composioImportHistory(),
      dispatchApi.composioObservationCounts(),
    ]);
    if (result[0].status === "fulfilled") {
      setSources(result[0].value.items.filter(item => item.kind === "composio"));
      setEnabled(Boolean(result[0].value.composio_ingestion_enabled));
    } else {
      setError("Não foi possível consultar as conexões do workspace.");
    }
    if (result[1].status === "fulfilled") setHistory(result[1].value.items);
    if (result[2].status === "fulfilled") setSummary(result[2].value.items);
    setLoading(false);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const selected = sources.find(item => item.reference === accountId);
  const tools = selected?.tools ?? [];

  const resetKey = () => { idempotencyRef.current = ""; };

  async function importData() {
    setError(null);
    let argumentsObject: Record<string, unknown>;
    let fieldMap: Record<string, string>;
    try {
      const parsedArguments: unknown = JSON.parse(argumentsText);
      const parsedFields: unknown = JSON.parse(fieldsText);
      if (!parsedArguments || typeof parsedArguments !== "object" || Array.isArray(parsedArguments))
        throw new Error("Argumentos precisam ser um objeto JSON.");
      if (!parsedFields || typeof parsedFields !== "object" || Array.isArray(parsedFields))
        throw new Error("O mapeamento precisa ser um objeto JSON.");
      if (Object.values(parsedFields).some(value => typeof value !== "string"))
        throw new Error("Cada campo de destino precisa apontar para um caminho de origem.");
      argumentsObject = parsedArguments as Record<string, unknown>;
      fieldMap = parsedFields as Record<string, string>;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "JSON inválido.");
      return;
    }
    if (!accountId || !toolSlug || !enabled) {
      setError("Selecione uma conexão e ferramenta autorizadas. A execução deve estar habilitada.");
      return;
    }
    if (!idempotencyRef.current) idempotencyRef.current = crypto.randomUUID();
    setBusy(true);
    try {
      const result = await dispatchApi.importComposio({
        connected_account_id: accountId, tool_slug: toolSlug,
        arguments: argumentsObject, rows_path: rowsPath.trim(),
        record_id_field: recordField.trim(), subject_ref_field: subjectField.trim(),
        subject_type: subjectType, record_type: recordType,
        field_map: fieldMap,
      }, idempotencyRef.current);
      idempotencyRef.current = "";
      toast.success(`Dados consultados: ${result.total}; novos: ${result.created}; atualizados: ${result.updated}.`);
      await refresh();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Não foi possível importar os dados.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  }

  const fieldClass = "mt-1 w-full rounded-lg border border-[#DADADD] bg-white px-3 py-2.5 text-sm outline-none focus:border-[#2563EB]";

  return <>
    <Header title="Importações e conexões" subtitle="Leia dados de sistemas conectados via Composio, sem copiar credenciais" />
    <main className="mx-auto max-w-[1180px] space-y-6 px-4 pb-16 pt-6 md:px-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#202124]">Conectar dados ao motor de disparos</h1>
          <p className="mt-1 text-sm text-[#74747A]">
            Os dados importados ficam no contexto da organização. Nada é enviado aos contatos automaticamente.
          </p>
        </div>
        <Link href="/disparos" className="rounded-lg border border-[#DADADD] px-3 py-2 text-sm text-[#333]">
          Voltar aos disparos
        </Link>
      </div>

      {!enabled && <div className="rounded-xl border border-[#E8E3D6] bg-[#FFFCF6] p-4 text-sm text-[#6F603B]">
        <p className="font-semibold">Leituras reais Composio ainda não habilitadas neste ambiente</p>
        <p className="mt-1">
          A organização pode configurar suas conexões; executar importações exige as flags do backend,
          allowlist de ferramentas de leitura e chave de criptografia. Nenhuma execução foi disparada.
        </p>
      </div>}
      {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</p>}

      <section className="rounded-2xl border border-[#E7E7EA] bg-white p-5 md:p-6">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-semibold text-[#242428]">1. Selecionar conexão</h2>
          <Link href="/integracoes" className="text-sm text-[#2563EB]">Gerenciar integrações</Link>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm text-[#55555C]">Conta conectada
            <select value={accountId} className={fieldClass} onChange={e => {
              setAccountId(e.target.value); setToolSlug(""); resetKey();
            }}>
              <option value="">Selecione uma conta Composio</option>
              {sources.map(source => (
                <option key={source.reference} value={source.reference || ""} disabled={!source.can_bind}>
                  {source.name} ({source.toolkit}){!source.can_bind ? " · não habilitada" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-[#55555C]">Ferramenta de leitura permitida
            <select value={toolSlug} className={fieldClass} disabled={!selected} onChange={e => {
              setToolSlug(e.target.value); resetKey();
            }}>
              <option value="">Selecione uma ferramenta</option>
              {tools.map(slug => <option key={slug} value={slug}>{slug}</option>)}
            </select>
          </label>
        </div>
        <p className="mt-3 text-xs text-[#85858B]">
          A seleção respeita as políticas do workspace. O backend também exige uma allowlist explícita
          para executar leituras e confirma a titularidade da conta no Composio.
        </p>
      </section>

      <section className="rounded-2xl border border-[#E7E7EA] bg-white p-5 md:p-6">
        <h2 className="mb-1 font-semibold text-[#242428]">2. Consultar e mapear dados</h2>
        <p className="mb-5 text-sm text-[#85858B]">
          Configure os argumentos da ferramenta e diga à MIRA onde estão os registros e seus identificadores.
          Apenas os campos mapeados são guardados, criptografados.
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm text-[#55555C]">Argumentos da ferramenta (JSON)
            <textarea value={argumentsText} onChange={e => { setArgumentsText(e.target.value); resetKey(); }}
              rows={5} spellCheck={false} className={fieldClass + " font-mono"} />
          </label>
          <label className="text-sm text-[#55555C]">Mapeamento de campos (JSON)
            <textarea value={fieldsText} onChange={e => { setFieldsText(e.target.value); resetKey(); }}
              rows={5} spellCheck={false} className={fieldClass + " font-mono"} />
          </label>
          <label className="text-sm text-[#55555C]">Caminho para a lista na resposta
            <input value={rowsPath} onChange={e => { setRowsPath(e.target.value); resetKey(); }}
              className={fieldClass} placeholder="items, data.contacts, records" />
          </label>
          <label className="text-sm text-[#55555C]">Campo de ID estável do registro
            <input value={recordField} onChange={e => { setRecordField(e.target.value); resetKey(); }}
              className={fieldClass} placeholder="id" />
          </label>
          <label className="text-sm text-[#55555C]">Campo de ID do destinatário na MIRA
            <input value={subjectField} onChange={e => { setSubjectField(e.target.value); resetKey(); }}
              className={fieldClass} placeholder="id, student_id, customer.id" />
          </label>
          <label className="text-sm text-[#55555C]">Público dos registros
            <select value={subjectType} onChange={e => { setSubjectType(e.target.value as typeof subjectType); resetKey(); }}
              className={fieldClass}>
              <option value="external">Contatos externos</option>
              <option value="student">Alunos da MIRA (UUID)</option>
            </select>
          </label>
          <label className="text-sm text-[#55555C]">Tipo dos dados
            <select value={recordType} onChange={e => { setRecordType(e.target.value as typeof recordType); resetKey(); }}
              className={fieldClass}>
              <option value="contact">Contatos e CRM</option>
              <option value="obligation">Informações financeiras</option>
              <option value="generic">Outros dados operacionais</option>
            </select>
          </label>
        </div>
        <div className="mt-5 border-t border-[#EEEEF0] pt-5">
          <button disabled={busy || loading || !enabled || !accountId || !toolSlug}
            onClick={() => void importData()}
            className="rounded-lg bg-[#202124] px-5 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40">
            {busy ? "Consultando sistema conectado…" : "Consultar e importar dados"}
          </button>
          <p className="mt-3 text-xs text-[#85858B]">
            Limite: 100 registros e 256 KB por execução. Importação não equivale a consentimento,
            confirmação de pagamento ou autorização para envio. Os contatos elegíveis são verificados
            posteriormente na campanha.
          </p>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-2xl border border-[#E7E7EA] bg-white p-5">
          <h2 className="mb-3 text-sm font-semibold">Histórico de importações</h2>
          {history.length === 0 ? <p className="text-sm text-[#85858B]">Nenhuma importação registrada.</p> :
            <div className="divide-y divide-[#F0F0F2]">{history.map(item =>
              <div key={item.id} className="py-3 text-sm">
                <p className="font-medium">{item.toolkit_slug} · {item.tool_slug}</p>
                <p className="mt-1 text-xs text-[#85858B]">
                  {item.status} · {item.rows_total} registros · {new Date(item.started_at).toLocaleString("pt-BR")}
                </p>
              </div>)}</div>}
        </section>
        <section className="rounded-2xl border border-[#E7E7EA] bg-white p-5">
          <h2 className="mb-3 text-sm font-semibold">Dados armazenados na MIRA</h2>
          {summary.length === 0 ? <p className="text-sm text-[#85858B]">Nenhum registro sincronizado.</p> :
            <div className="divide-y divide-[#F0F0F2]">{summary.map((item, index) =>
              <div key={index} className="py-3 text-sm">
                <p className="font-medium">{item.toolkit_slug} · {item.record_type}</p>
                <p className="mt-1 text-xs text-[#85858B]">{item.records} registros · {item.tool_slug}</p>
              </div>)}</div>}
        </section>
      </div>
    </main>
  </>;
}
