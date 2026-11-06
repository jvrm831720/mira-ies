"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import {
  financeApi, type Discrepancy, type FinanceConnection,
  type FinanceProfile, type FinanceComposioTool, type ProfilePayload,
  type ReviewWorkflow,
} from "@/lib/finance-reconciliation-api";

type SourceKind = "import" | "composio";
const COLUMNS = [
  { key: "external_id", name: "Identificador da obrigação", mandatory: true, placeholder: "Numero parcela" },
  { key: "student_reference", name: "Identificador do aluno", mandatory: true, placeholder: "Matricula" },
  { key: "amount", name: "Valor total (BRL)", mandatory: true, placeholder: "Valor" },
  { key: "currency", name: "Moeda", mandatory: true, placeholder: "Moeda" },
  { key: "status", name: "Situação na origem", mandatory: true, placeholder: "Situacao" },
  { key: "label", name: "Descrição", mandatory: false, placeholder: "Descricao" },
  { key: "paid_amount", name: "Valor informado como pago", mandatory: false, placeholder: "Valor pago" },
  { key: "due_at", name: "Vencimento ISO com fuso", mandatory: false, placeholder: "Vencimento" },
  { key: "correlation_key", name: "Chave de conciliação entre fontes", mandatory: false, placeholder: "Contrato" },
  { key: "source_updated_at", name: "Atualização da fonte com fuso", mandatory: false, placeholder: "Atualizado em" },
] as const;

const REQUIRED_DEFAULT: Record<string, string> = {
  external_id: "Numero parcela", student_reference: "Matricula",
  amount: "Valor", currency: "Moeda", status: "Situacao",
};
const DEFAULT_WORKFLOW: ReviewWorkflow = {
  transitions: {
    open: ["triage"], triage: ["awaiting_source", "reviewed"],
    awaiting_source: ["triage"], reviewed: [],
  },
  labels: {
    open: "Pendente", triage: "Em análise",
    awaiting_source: "Aguardando fonte", reviewed: "Revisado (não confirma quitação)",
  },
};
const CANONICAL = [
  ["open", "Em aberto"], ["overdue", "Vencido"], ["partially_paid", "Pagamento parcial informado"],
  ["reported_paid", "Pagamento informado (não confirmado)"],
  ["cancelled", "Cancelado"], ["disputed", "Em disputa"], ["unknown", "Sem correspondência"],
] as const;

function safeError(error: unknown) {
  return error instanceof Error ? error.message : "Não foi possível concluir a operação.";
}
function formatState(state: string) {
  return CANONICAL.find((entry) => entry[0] === state)?.[1] ?? state;
}
function parseStatusMap(raw: string) {
  const out: Record<string, string> = {};
  for (const line of raw.split("\n")) {
    if (!line.trim()) continue;
    const i = line.indexOf("=");
    if (i < 1) throw new Error("Use uma situação por linha: STATUS_ORIGEM=estado_mira.");
    const key = line.slice(0, i).trim(), value = line.slice(i + 1).trim();
    if (!CANONICAL.some((e) => e[0] === value)) throw new Error(`Estado inválido: ${value}`);
    if (!key) throw new Error("Não deixe situação de origem vazia.");
    out[key] = value;
  }
  return out;
}

function Panel({ title, subtitle, children }: {
  title: string; subtitle?: string; children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[var(--color-line)] bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.03)]">
      <h2 className="text-[length:var(--type-body-comfort)] font-semibold text-[var(--color-legacy-101828)]">{title}</h2>
      {subtitle ? <p className="mt-1 text-xs leading-5 text-[var(--color-legacy-667085)]">{subtitle}</p> : null}
      <div className="mt-5">{children}</div>
    </section>
  );
}

const fieldClass = "w-full rounded-lg border border-[var(--color-legacy-d0d5dd)] bg-white px-3 py-2.5 text-xs text-[var(--color-legacy-344054)] outline-none focus:border-[var(--color-legacy-2563eb)] focus:ring-2 focus:ring-[var(--color-legacy-2563eb)]/10";
const primary = "rounded-lg bg-[var(--color-legacy-101828)] px-4 py-2.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40";
const secondary = "rounded-lg border border-[var(--color-legacy-d0d5dd)] bg-white px-4 py-2.5 text-xs font-semibold text-[var(--color-legacy-344054)] hover:bg-[var(--color-source-f9fafb)] disabled:opacity-40";

export default function FinancialSourcesPage() {
  const [profiles, setProfiles] = useState<FinanceProfile[]>([]);
  const [accounts, setAccounts] = useState<FinanceConnection[]>([]);
  const [financialToolkits, setFinancialToolkits] = useState<string[]>([]);
  const [tools, setTools] = useState<FinanceComposioTool[]>([]);
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [step, setStep] = useState(1);
  const [sourceKind, setSourceKind] = useState<SourceKind>("import");
  const [name, setName] = useState("");
  const [accountId, setAccountId] = useState("");
  const [toolSlug, setToolSlug] = useState("");
  const [rowsPath, setRowsPath] = useState("items");
  const [studentLookup, setStudentLookup] = useState<"mira_id" | "verified_external">("mira_id");
  const [mapping, setMapping] = useState<Record<string, string>>(REQUIRED_DEFAULT);
  const [statusText, setStatusText] = useState("ABERTO=open\nVENCIDO=overdue\nPAGO=reported_paid");
  const [workflowText, setWorkflowText] = useState(JSON.stringify(DEFAULT_WORKFLOW, null, 2));
  const [showWorkflow, setShowWorkflow] = useState(false);
  const [sourceArgs, setSourceArgs] = useState("{}");
  const [previewText, setPreviewText] = useState("[]");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [mappingFile, setMappingFile] = useState<File | null>(null);
  const [headerSuggestions, setHeaderSuggestions] = useState<Record<string, { suggested_header: string; confidence: number }>>({});
  const [confirmed, setConfirmed] = useState(false);
  const [linkRef, setLinkRef] = useState("");
  const [linkStudent, setLinkStudent] = useState("");
  const [reviewNote, setReviewNote] = useState("Conferir divergência com a fonte de origem.");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showCreator, setShowCreator] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const result = await Promise.allSettled([
      financeApi.profiles(), financeApi.discrepancies(),
      financeApi.connections(), financeApi.financialCatalog(),
    ]);
    if (result[0].status === "fulfilled") {
      const loadedProfiles = result[0].value.items;
      setProfiles(loadedProfiles);
      setSelectedId((current) => current || loadedProfiles[0]?.id || "");
      setError(null);
    } else {
      setError(safeError(result[0].reason));
    }
    if (result[1].status === "fulfilled") setDiscrepancies(result[1].value.items);
    if (result[2].status === "fulfilled") setAccounts(result[2].value.items);
    if (result[3].status === "fulfilled") {
      const finance = result[3].value.items.find((item) => item.slug === "finance");
      setFinancialToolkits((finance?.composio_toolkits ?? []).map((item) => item.slug));
    }
    setLoading(false);
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const selected = useMemo(() => profiles.find((p) => p.id === selectedId), [profiles, selectedId]);
  const eligibleAccounts = accounts.filter((item) =>
    item.status === "active" && !item.disconnected_at && financialToolkits.includes(item.toolkit_slug)
  );
  const accountToolkit = eligibleAccounts.find((item) => item.connected_account_id === accountId)?.toolkit_slug;

  useEffect(() => {
    if (!accountToolkit) { setTools([]); return; }
    let active = true;
    financeApi.tools(accountToolkit)
      .then((data) => {
        if (!active) return;
        setTools(data.items.filter((item) =>
          /(?:^|_)(?:GET|LIST|READ|SEARCH|FETCH|QUERY|LOOKUP|RETRIEVE)(?:_|$)/.test(item.slug)
          && !/(?:^|_)(?:PAY|CHARGE|TRANSFER|SEND|POST|CREATE|DELETE|UPDATE|WRITE)(?:_|$)/.test(item.slug)
        ));
      })
      .catch(() => { if (active) setTools([]); });
    return () => { active = false; };
  }, [accountToolkit]);

  function resetCreate() {
    setEditingId(null);
    setName(""); setSourceKind("import"); setAccountId(""); setToolSlug("");
    setRowsPath("items"); setMapping(REQUIRED_DEFAULT);
    setStatusText("ABERTO=open\nVENCIDO=overdue\nPAGO=reported_paid");
    setWorkflowText(JSON.stringify(DEFAULT_WORKFLOW, null, 2)); setStudentLookup("mira_id");
    setStep(1); setShowCreator(true); setError(null); setMessage(null);
    setMappingFile(null); setHeaderSuggestions({});
  }

  function startEdit(profile: FinanceProfile) {
    setEditingId(profile.id);
    setName(profile.name);
    setSourceKind(profile.source_kind);
    setAccountId(profile.connected_account_id || "");
    setToolSlug(profile.tool_slug || "");
    setRowsPath(profile.rows_path || "items");
    setStudentLookup(profile.student_lookup);
    setMapping({ ...profile.field_map });
    setStatusText(Object.entries(profile.status_map).map(([raw, state]) => `${raw}=${state}`).join("\n"));
    setWorkflowText(JSON.stringify(profile.review_workflow, null, 2));
    setStep(1);
    setShowCreator(true);
    setError(null); setMessage(null);
    setHeaderSuggestions({});
  }

  async function inspectHeaders() {
    if (!mappingFile) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const result = await financeApi.csvHeaders(mappingFile);
      setHeaderSuggestions(result.suggestions);
      setMessage(`Foram encontrados ${result.headers.length} cabeçalhos. Confirme as sugestões antes de aplicá-las.`);
    } catch (reason) { setError(safeError(reason)); }
    finally { setBusy(false); }
  }

  function applySuggestions() {
    const mapped = Object.fromEntries(
      Object.entries(headerSuggestions).map(([name, value]) => [name, value.suggested_header]),
    );
    setMapping((old) => ({ ...old, ...mapped }));
    setMessage("Sugestões aplicadas ao formulário. Confira cada coluna antes de salvar.");
    setHeaderSuggestions({});
  }

  async function previewCsvFile() {
    if (!selected || !csvFile) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const result = await financeApi.csvPreview(selected.id, csvFile);
      setMessage(`CSV: ${result.total} registros; vínculos de alunos ${result.students_linked ? "validados" : "pendentes"}. Nada foi gravado.`);
    } catch (reason) { setError(safeError(reason)); }
    finally { setBusy(false); }
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null); setMessage(null);
    try {
      let workflow: ReviewWorkflow;
      try { workflow = JSON.parse(workflowText) as ReviewWorkflow; }
      catch { throw new Error("Workflow deve ser um JSON válido."); }
      const configured = Object.fromEntries(Object.entries(mapping).filter(([,value]) => value.trim()));
      const payload: ProfilePayload = {
        name: name.trim(), source_kind: sourceKind,
        connected_account_id: sourceKind === "composio" ? accountId : null,
        tool_slug: sourceKind === "composio" ? toolSlug : null,
        rows_path: sourceKind === "composio" ? rowsPath : "",
        field_map: configured,
        status_map: parseStatusMap(statusText), review_workflow: workflow,
        student_lookup: studentLookup,
      };
      setBusy(true);
      const previous = editingId ? profiles.find((p) => p.id === editingId) : null;
      if (editingId && !previous) throw new Error("Origem não encontrada. Atualize os dados.");
      const saved = previous ? await financeApi.configure(previous, payload) : await financeApi.create(payload);
      await refresh();
      setSelectedId(saved.id); setShowCreator(false); setEditingId(null);
      setMessage(previous
        ? "Metadados atualizados com nova versão. Revise o mapeamento antes da próxima importação."
        : "Origem criada desabilitada. Revise os vínculos e habilite somente em homologação.");
    } catch (reason) { setError(safeError(reason)); }
    finally { setBusy(false); }
  }

  async function switchEnabled(profile: FinanceProfile) {
    setBusy(true); setError(null); setMessage(null);
    try {
      const updated = await financeApi.update(profile, !profile.enabled);
      setProfiles((list) => list.map((item) => item.id === profile.id ? updated : item));
      setMessage(updated.enabled ? "Origem habilitada para leituras autorizadas." : "Origem desabilitada.");
    } catch (reason) { setError(safeError(reason)); }
    finally { setBusy(false); }
  }

  async function submitCsv() {
    if (!selected || !csvFile || !confirmed) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const result = await financeApi.csvImport(selected.id, csvFile);
      setCsvFile(null); setConfirmed(false);
      setMessage(`Importação registrada: ${result.imported} observações novas, ${result.unchanged} inalteradas. Nenhum pagamento confirmado.`);
      await refresh();
    } catch (reason) { setError(safeError(reason)); }
    finally { setBusy(false); }
  }

  async function runSync() {
    if (!selected || !confirmed) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const raw: unknown = JSON.parse(sourceArgs);
      if (!raw || Array.isArray(raw) || typeof raw !== "object") throw new Error("Argumentos devem ser um objeto JSON.");
      const result = await financeApi.composioSync(selected.id, raw as Record<string, unknown>);
      setMessage(`Leitura Composio concluída: ${result.imported} observações novas. Sem quitação automática.`);
      setConfirmed(false);
      await refresh();
    } catch (reason) { setError(safeError(reason)); }
    finally { setBusy(false); }
  }

  async function runPreview() {
    if (!selected || selected.source_kind !== "import") return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const raw: unknown = JSON.parse(previewText);
      if (!Array.isArray(raw)) throw new Error("Preview exige uma lista JSON de registros.");
      const items = raw as Record<string, unknown>[];
      const result = await financeApi.preview(selected.id, items);
      setMessage(`Pré-visualização: ${result.total} registros; vínculos com alunos ${result.students_linked ? "validados" : "pendentes"}. Nada foi gravado.`);
    } catch (reason) { setError(safeError(reason)); }
    finally { setBusy(false); }
  }

  async function saveLink() {
    if (!selected) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      await financeApi.linkStudent(selected.id, linkRef.trim(), linkStudent.trim());
      setMessage("Vínculo registrado para esta origem. Não será reutilizado em outras integrações.");
      setLinkRef(""); setLinkStudent("");
    } catch (reason) { setError(safeError(reason)); }
    finally { setBusy(false); }
  }

  async function openReview(item: Discrepancy) {
    const source = item.items[0];
    if (!source) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const result = await financeApi.review(source.profile_id, source.external_id, reviewNote.trim());
      setMessage(`Caso ${result.id} criado em ${result.step}. Revisão não altera o status financeiro.`);
    } catch (reason) { setError(safeError(reason)); }
    finally { setBusy(false); }
  }

  return (
    <div className="min-h-screen bg-[var(--color-source-f9fafb)]">
      <Header title="Fontes financeiras" subtitle="Várias integrações, mapeamentos por workspace e conciliação orientada por metadados" />
      <main className="mx-auto max-w-[1230px] space-y-5 px-5 py-7 md:px-8 xl:px-10">
        <Link href="/conectores" className="text-xs font-medium text-[var(--color-legacy-667085)] hover:text-[var(--color-legacy-2563eb)]">
          Integrações / Fontes financeiras
        </Link>
        <div className="flex justify-end"><Link href="/conectores/financeiro/pagamentos" className="text-xs font-semibold text-[var(--color-legacy-2563eb)] hover:underline">Pagamentos em homologação</Link></div>
        <div className="rounded-xl border border-[var(--color-legacy-eaecf0)] bg-white px-5 py-4">
          <p className="text-xs font-semibold text-[var(--color-legacy-344054)]">Homologação e proveniência</p>
          <p className="mt-1 text-xs leading-5 text-[var(--color-legacy-667085)]">
            As informações refletem o que cada sistema declara. Uma situação “paga” é apenas informada pela fonte:
            não há conciliação bancária, iniciação de Pix, boleto ou quitação automática nesta etapa.
          </p>
        </div>
        {error && <div role="alert" className="rounded-xl border border-[var(--color-legacy-fda29b)] bg-[var(--color-legacy-fffbfa)] p-4 text-xs text-[var(--color-legacy-b42318)]">{error}</div>}
        {message && <div role="status" className="rounded-xl border border-[var(--color-legacy-d0d5dd)] bg-white p-4 text-xs text-[var(--color-legacy-344054)]">{message}</div>}

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ["Perfis de origem", profiles.length],
            ["Conexões financeiras", eligibleAccounts.length],
            ["Fontes ativas", profiles.filter((item) => item.enabled).length],
            ["Divergências", discrepancies.filter((item) => item.result === "conflict").length],
          ].map(([label,value]) => (
            <div key={label} className="rounded-xl border border-[var(--color-line)] bg-white p-4">
              <p className="text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">{label}</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums tracking-[-0.04em] text-[var(--color-legacy-101828)]">{value}</p>
            </div>
          ))}
        </div>

        <div className="grid gap-5 xl:grid-cols-[340px_minmax(0,1fr)]">
          <Panel title="Origens do workspace" subtitle="Adicione quantos perfis forem necessários. Cada um mantém sua própria configuração.">
            <div className="space-y-2">
              {profiles.map((item) => (
                <button key={item.id} type="button" onClick={() => { setSelectedId(item.id); setShowCreator(false); setConfirmed(false); }}
                  className={"w-full rounded-xl border p-3 text-left transition-colors " +
                    (selectedId === item.id && !showCreator ? "border-[var(--color-legacy-2563eb)] bg-[var(--color-source-eff4ff)]" : "border-[var(--color-legacy-eaecf0)] hover:border-[var(--color-legacy-d0d5dd)]")}>
                  <p className="flex items-center justify-between gap-2">
                    <span className="truncate text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-344054)]">{item.name}</span>
                    <span className={"rounded-full px-2 py-0.5 text-[length:var(--type-overline)] " +
                      (item.enabled ? "bg-[var(--color-source-ecfdf3)] text-[var(--color-source-027a48)]" : "bg-[var(--color-legacy-f2f4f7)] text-[var(--color-legacy-667085)]")}>
                      {item.enabled ? "Ativa" : "Desabilitada"}
                    </span>
                  </p>
                  <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">
                    {item.source_kind === "composio" ? "Composio" : "CSV / Importação"} · mapeamento v{item.mapping_version}
                  </p>
                </button>
              ))}
              {loading && <p className="text-xs text-[var(--color-legacy-667085)]">Carregando origens…</p>}
              {!loading && profiles.length === 0 && <p className="py-3 text-xs text-[var(--color-legacy-667085)]">Nenhuma origem configurada.</p>}
              <button type="button" className={"mt-2 w-full " + secondary} onClick={resetCreate}>+ Nova origem</button>
            </div>
          </Panel>

          {showCreator ? (
            <Panel title={editingId ? "Editar origem e metadados" : "Criar origem configurável"} subtitle="Os campos e o workflow são metadados do workspace. Nenhum código por cliente.">
              <div className="mb-5 flex items-center gap-2">
                {["Origem", "Mapeamento", "Revisar"].map((label,i) => (
                  <span key={label} className={"rounded-md px-3 py-1.5 text-[length:var(--type-caption)] font-medium " +
                    (step === i + 1 ? "bg-[var(--color-legacy-101828)] text-white" : "bg-[var(--color-legacy-f2f4f7)] text-[var(--color-legacy-667085)]")}>
                    {i + 1}. {label}
                  </span>
                ))}
              </div>
              <form onSubmit={saveProfile} className="space-y-4">
                {step === 1 && <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="space-y-1 text-xs font-medium text-[var(--color-legacy-344054)]">Nome da origem
                      <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} className={fieldClass} placeholder="Ex.: ERP do Campus Norte" />
                    </label>
                    <label className="space-y-1 text-xs font-medium text-[var(--color-legacy-344054)]">Tipo
                      <select className={fieldClass} disabled={Boolean(editingId)} value={sourceKind} onChange={(e) => setSourceKind(e.target.value as SourceKind)}>
                        <option value="import">Arquivo CSV</option><option value="composio">Composio</option>
                      </select>
                    </label>
                  </div>
                  {sourceKind === "composio" && <>
                    <label className="block space-y-1 text-xs font-medium text-[var(--color-legacy-344054)]">Conexão financeira existente
                      <select className={fieldClass} disabled={Boolean(editingId)} value={accountId} onChange={(e) => { setAccountId(e.target.value); setToolSlug(""); }}>
                        <option value="">Selecione uma conta conectada</option>
                        {eligibleAccounts.map((a) => (
                          <option key={a.connected_account_id} value={a.connected_account_id}>
                            {a.display_name || a.toolkit_slug} · {a.toolkit_slug}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block space-y-1 text-xs font-medium text-[var(--color-legacy-344054)]">Ferramenta de leitura autorizada
                      <select className={fieldClass} disabled={Boolean(editingId)} value={toolSlug} onChange={(e) => setToolSlug(e.target.value)}>
                        <option value="">Selecione uma ferramenta</option>
                        {tools.map((t) => <option key={t.slug} value={t.slug}>{t.slug}</option>)}
                      </select>
                    </label>
                    <label className="block space-y-1 text-xs font-medium text-[var(--color-legacy-344054)]">Caminho da lista de registros (JSON)
                      <input className={fieldClass} value={rowsPath} onChange={(e) => setRowsPath(e.target.value)} placeholder="items" />
                    </label>
                    {eligibleAccounts.length === 0 && <p className="text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">Conecte primeiro um sistema financeiro em Integrações → Composio.</p>}
                  </>}
                  <label className="block space-y-1 text-xs font-medium text-[var(--color-legacy-344054)]">Como vincular cada registro ao aluno?
                    <select className={fieldClass} value={studentLookup} onChange={(e) => setStudentLookup(e.target.value as "mira_id" | "verified_external")}>
                      <option value="mira_id">UUID MIRA informado na origem</option>
                      <option value="verified_external">Identificador externo com vínculo humano verificado</option>
                    </select>
                  </label>
                  <p className="text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">Não usamos nome, CPF aproximado ou semelhança textual para vincular obrigações a alunos.</p>
                </>}
                {step === 2 && <>
                  <p className="text-xs text-[var(--color-legacy-667085)]">Indique a coluna de CSV ou o caminho JSON de cada campo. Campos com * são obrigatórios.</p>
                  {sourceKind === "import" && <div className="rounded-xl border border-[var(--color-legacy-eaecf0)] bg-[var(--color-source-f9fafb)] p-3">
                    <p className="text-xs font-semibold text-[var(--color-legacy-344054)]">Sugerir mapeamento a partir de um CSV</p>
                    <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">As sugestões não são aplicadas automaticamente. Confirme antes de salvar.</p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <input aria-label="Arquivo CSV para analisar cabeçalhos" type="file" accept=".csv,text/csv"
                        onChange={(e) => setMappingFile(e.target.files?.[0] || null)}
                        className="max-w-full text-[length:var(--type-caption)]" />
                      <button type="button" className={secondary} disabled={!mappingFile || busy}
                        onClick={() => void inspectHeaders()}>Analisar cabeçalhos</button>
                    </div>
                    {Object.keys(headerSuggestions).length > 0 && <div className="mt-3">
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(headerSuggestions).map(([key,value]) => (
                          <span key={key} className="rounded-md bg-white px-2 py-1 text-[length:var(--type-caption)] text-[var(--color-legacy-475467)]">
                            {value.suggested_header} → {key} ({Math.round(value.confidence * 100)}%)
                          </span>
                        ))}
                      </div>
                      <button type="button" className={"mt-3 " + secondary} onClick={applySuggestions}>
                        Confirmar e aplicar sugestões
                      </button>
                    </div>}
                  </div>}
                  <div className="grid gap-3 md:grid-cols-2">
                    {COLUMNS.map((field) => (
                      <label key={field.key} className="space-y-1 text-xs font-medium text-[var(--color-legacy-344054)]">
                        {field.name}{field.mandatory ? " *" : ""}
                        <input className={fieldClass} value={mapping[field.key] ?? ""}
                          onChange={(e) => setMapping((old) => ({ ...old, [field.key]: e.target.value }))}
                          placeholder={sourceKind === "import" ? field.placeholder : field.key} />
                      </label>
                    ))}
                  </div>
                  <div>
                    <p className="mb-1 text-xs font-medium text-[var(--color-legacy-344054)]">Situações da origem → estados MIRA</p>
                    <textarea className={fieldClass} rows={4} spellCheck={false} value={statusText}
                      onChange={(e) => setStatusText(e.target.value)} />
                    <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">Não reconhecido → desconhecido. “PAGO” → pagamento informado, nunca comprovado.</p>
                  </div>
                </>}
                {step === 3 && <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-lg bg-[var(--color-source-f9fafb)] p-4 text-xs">
                      <p className="font-semibold text-[var(--color-legacy-101828)]">Origem</p>
                      <p className="mt-1 text-[var(--color-legacy-667085)]">{name || "Sem nome"} · {sourceKind === "composio" ? "Composio" : "Importação"}</p>
                    </div>
                    <div className="rounded-lg bg-[var(--color-source-f9fafb)] p-4 text-xs">
                      <p className="font-semibold text-[var(--color-legacy-101828)]">Mapeamento</p>
                      <p className="mt-1 text-[var(--color-legacy-667085)]">{Object.values(mapping).filter((value) => value.trim()).length} campos · vínculo {studentLookup === "mira_id" ? "UUID" : "externo verificado"}</p>
                    </div>
                  </div>
                  <button type="button" onClick={() => setShowWorkflow((value) => !value)} className="text-xs font-medium text-[var(--color-legacy-2563eb)]">
                    {showWorkflow ? "Ocultar" : "Personalizar"} workflow de revisão
                  </button>
                  {showWorkflow && <>
                    <textarea className={fieldClass} rows={12} spellCheck={false} value={workflowText}
                      onChange={(e) => setWorkflowText(e.target.value)} aria-label="Metadados do workflow de revisão" />
                    <p className="text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">Estados e transições de revisão. Esse workflow nunca altera um pagamento.</p>
                  </>}
                  <div className="rounded-lg border border-[var(--color-legacy-eaecf0)] p-3 text-xs text-[var(--color-legacy-667085)]">
                    Este perfil será salvo desabilitado. Sua ativação exige uma ação posterior explícita.
                  </div>
                </>}
                <div className="flex items-center justify-between gap-2 border-t border-[var(--color-legacy-eaecf0)] pt-4">
                  <button type="button" className={secondary} onClick={() => step === 1 ? setShowCreator(false) : setStep(step - 1)}>
                    {step === 1 ? "Cancelar" : "Voltar"}
                  </button>
                  {step < 3 ? (
                    <button type="button" className={primary} disabled={step === 1 && (!name.trim() || (sourceKind === "composio" && (!accountId || !toolSlug)))}
                      onClick={() => setStep(step + 1)}>Continuar</button>
                  ) : <button type="submit" disabled={busy} className={primary}>{editingId ? "Salvar nova versão" : "Criar perfil desabilitado"}</button>}
                </div>
              </form>
            </Panel>
          ) : selected ? (
            <div className="space-y-5">
              <Panel title={selected.name} subtitle="Configuração independente e versionada — sem sobrescrever outras fontes.">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="text-xs text-[var(--color-legacy-667085)]">
                    <p>{selected.source_kind === "composio" ? "Conta Composio" : "CSV / importação manual"} · versão {selected.mapping_version}</p>
                    <p className="mt-1">Vínculo: {selected.student_lookup === "mira_id" ? "UUID MIRA" : "Identificador externo verificado"}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className={secondary} type="button" disabled={busy} onClick={() => startEdit(selected)}>
                      Editar metadados
                    </button>
                    <button className={secondary} type="button" disabled={busy} onClick={() => void switchEnabled(selected)}>
                      {selected.enabled ? "Desabilitar origem" : "Habilitar origem"}
                    </button>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 border-t border-[var(--color-legacy-eaecf0)] pt-4 sm:grid-cols-2">
                  {Object.entries(selected.field_map).map(([field,path]) => (
                    <div key={field} className="flex justify-between gap-3 text-[length:var(--type-caption)]">
                      <span className="text-[var(--color-legacy-667085)]">{field}</span><strong className="truncate text-[var(--color-legacy-344054)]">{path}</strong>
                    </div>
                  ))}
                </div>
              </Panel>
              <Panel title={selected.source_kind === "composio" ? "Consultar sistema conectado" : "Importar registros financeiros"}
                subtitle="Até 100 registros por lote, importação idempotente e histórico de observações.">
                {selected.source_kind === "import" ? <>
                  <input type="file" accept=".csv,text/csv" className={fieldClass} onChange={(e) => setCsvFile(e.target.files?.[0] || null)} />
                  <p className="mt-2 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">CSV UTF-8 de até 512 KB. Cabeçalhos devem coincidir com o mapeamento aprovado.</p>
                  <button className={"mt-3 " + secondary} disabled={busy || !csvFile}
                    onClick={() => void previewCsvFile()}>Pré-visualizar CSV sem gravar</button>
                  <details className="mt-3 rounded-lg border border-[var(--color-legacy-eaecf0)] px-3 py-2">
                    <summary className="cursor-pointer text-xs font-medium text-[var(--color-legacy-344054)]">Testar dados de exemplo (sem gravar)</summary>
                    <textarea className={"mt-3 " + fieldClass} rows={4} spellCheck={false}
                      value={previewText} onChange={(e) => setPreviewText(e.target.value)}
                      aria-label="Amostra JSON para pré-visualização" />
                    <button className={"mt-2 " + secondary} disabled={busy} onClick={() => void runPreview()}>Pré-visualizar</button>
                  </details>
                </> : <>
                  <p className="text-xs text-[var(--color-legacy-667085)]">{selected.tool_slug || "Ferramenta não definida"}</p>
                  <label className="mt-3 block text-xs font-medium text-[var(--color-legacy-344054)]">Argumentos de consulta (JSON)
                    <textarea className={"mt-1 " + fieldClass} rows={4} spellCheck={false}
                      value={sourceArgs} onChange={(e) => setSourceArgs(e.target.value)} />
                  </label>
                </>}
                <label className="mt-4 flex cursor-pointer items-start gap-2 text-xs text-[var(--color-legacy-475467)]">
                  <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5" />
                  Confirmo a origem e o mapeamento. Os estados são informativos e não autorizam pagamentos.
                </label>
                <button type="button" className={"mt-4 " + primary}
                  disabled={busy || !confirmed || !selected.enabled || (selected.source_kind === "import" && !csvFile)}
                  onClick={() => void (selected.source_kind === "import" ? submitCsv() : runSync())}>
                  {busy ? "Processando…" : selected.source_kind === "import" ? "Importar arquivo" : "Sincronizar via Composio"}
                </button>
              </Panel>
              {selected.student_lookup === "verified_external" && (
                <Panel title="Vincular aluno à origem" subtitle="O vínculo é exclusivo deste perfil e exige confirmação do operador.">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <input className={fieldClass} placeholder="Identificador no ERP" value={linkRef} onChange={(e) => setLinkRef(e.target.value)} />
                    <input className={fieldClass} placeholder="UUID do aluno na MIRA" value={linkStudent} onChange={(e) => setLinkStudent(e.target.value)} />
                  </div>
                  <button type="button" className={"mt-3 " + secondary} disabled={busy || !linkRef.trim() || !linkStudent.trim()}
                    onClick={() => void saveLink()}>Confirmar vínculo</button>
                </Panel>
              )}
            </div>
          ) : (
            <Panel title="Comece com uma fonte" subtitle="Conecte um ERP financeiro ou crie um perfil de importação CSV.">
              <button type="button" className={primary} onClick={resetCreate}>Criar primeira origem</button>
            </Panel>
          )}
        </div>

        <Panel title="Conciliação entre fontes" subtitle="Só agrupamos registros vinculados ao mesmo aluno e com chave de correlação explicitamente fornecida.">
          {discrepancies.length === 0 ? (
            <p className="py-4 text-xs text-[var(--color-legacy-667085)]">Ainda não existem observações correlacionadas em fontes homologadas.</p>
          ) : <div className="divide-y divide-[var(--color-legacy-eaecf0)]">
            {discrepancies.map((item) => (
              <div key={item.student_id + ":" + item.correlation_key} className="flex flex-wrap items-center justify-between gap-3 py-4">
                <div>
                  <p className="text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-344054)]">{item.correlation_key}</p>
                  <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">{item.sources} fonte(s) · aluno {item.student_id.slice(0, 8)}…</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {item.items.map((source) => (
                      <span key={source.profile_id + source.external_id} className="rounded-lg bg-[var(--color-legacy-f2f4f7)] px-2 py-1 text-[length:var(--type-caption)] text-[var(--color-legacy-475467)]">
                        {formatState(source.state)} · {source.amount} BRL
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={"rounded-full px-2.5 py-1 text-[length:var(--type-caption)] font-medium " +
                    (item.result === "conflict" ? "bg-[var(--color-red-tint)] text-[var(--color-legacy-b42318)]" : "bg-[var(--color-legacy-f2f4f7)] text-[var(--color-legacy-475467)]")}>
                    {item.result === "conflict" ? "Divergência" :
                      item.result === "multi_source_consistent" ? "Fontes consistentes" : "Fonte única"}
                  </span>
                  {item.result === "conflict" && <button type="button" className={secondary} disabled={busy}
                    onClick={() => void openReview(item)}>Abrir revisão</button>}
                </div>
              </div>
            ))}
          </div>}
          <label className="mt-4 block text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">
            Nota para abrir revisão
            <input className={"mt-1 " + fieldClass} value={reviewNote} maxLength={500}
              onChange={(e) => setReviewNote(e.target.value)} />
          </label>
          <p className="mt-3 text-[length:var(--type-caption)] text-[var(--color-legacy-98a2b3)]">Consistência entre fontes não confirma liquidação. A análise usa as observações recentes disponíveis.</p>
        </Panel>
      </main>
    </div>
  );
}
