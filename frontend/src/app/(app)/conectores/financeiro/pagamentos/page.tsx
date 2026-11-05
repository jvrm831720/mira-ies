"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { financeApi, type FinanceProfile, type FinanceConnection } from "@/lib/finance-reconciliation-api";
import {
  studentPaymentsApi, type SandboxProvider, type SandboxDraft,
  type SandboxEvidence, type FinancialObservation,
} from "@/lib/student-payments-api";

const inputClass = "w-full rounded-lg border border-[#D0D5DD] bg-white px-3 py-2.5 text-[12px] outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/10";
const primary = "rounded-lg bg-[#101828] px-4 py-2.5 text-[12px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40";
const secondary = "rounded-lg border border-[#D0D5DD] bg-white px-4 py-2.5 text-[12px] font-semibold text-[#344054] disabled:opacity-40";
const preparedStatuses = new Set(["open", "overdue", "partially_paid"]);

function failure(value: unknown) {
  return value instanceof Error ? value.message : "Operação indisponível.";
}

function Card({ title, explanation, children }: {
  title: string; explanation?: string; children: ReactNode;
}) {
  return <section className="rounded-2xl border border-[#E4E7EC] bg-white p-5">
    <h2 className="text-[15px] font-semibold text-[#101828]">{title}</h2>
    {explanation && <p className="mt-1 text-[12px] leading-5 text-[#667085]">{explanation}</p>}
    <div className="mt-5">{children}</div>
  </section>;
}

export default function SandboxPaymentsPage() {
  const [profiles, setProfiles] = useState<FinanceProfile[]>([]);
  const [connections, setConnections] = useState<FinanceConnection[]>([]);
  const [providers, setProviders] = useState<SandboxProvider[]>([]);
  const [drafts, setDrafts] = useState<SandboxDraft[]>([]);
  const [observations, setObservations] = useState<FinancialObservation[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("");
  const [selectedDraft, setSelectedDraft] = useState("");
  const [evidence, setEvidence] = useState<SandboxEvidence[]>([]);
  const [observationId, setObservationId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [providerName, setProviderName] = useState("");
  const [custom, setCustom] = useState(false);
  const [customSlug, setCustomSlug] = useState("omie");
  const [usePix, setUsePix] = useState(true);
  const [useBoleto, setUseBoleto] = useState(false);
  const [method, setMethod] = useState<"pix" | "boleto">("pix");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const result = await Promise.allSettled([
      studentPaymentsApi.providers(), studentPaymentsApi.drafts(),
      financeApi.profiles(), financeApi.connections(),
    ]);
    if (result[0].status === "fulfilled") {
      const items = result[0].value.items;
      setProviders(items);
      setSelectedProvider((current) => current || items[0]?.id || "");
      setError(null);
    } else {
      setError(failure(result[0].reason));
    }
    if (result[1].status === "fulfilled") setDrafts(result[1].value.items);
    if (result[2].status === "fulfilled") setProfiles(result[2].value.items);
    if (result[3].status === "fulfilled") setConnections(result[3].value.items);
    setLoading(false);
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  const source = useMemo(() => profiles.find((p) => p.id === sourceId), [profiles, sourceId]);
  const provider = useMemo(() => providers.find((p) => p.id === selectedProvider), [providers, selectedProvider]);
  const matchingAccount = source?.connected_account_id
    ? connections.find((a) => a.connected_account_id === source.connected_account_id)
    : undefined;
  const eligibleSources = profiles.filter((p) => p.enabled && (custom || p.source_kind === "composio"));
  const payable = observations.filter((o) => preparedStatuses.has(o.canonical_state));

  useEffect(() => {
    if (!provider) { setObservations([]); return; }
    let valid = true;
    studentPaymentsApi.observations(provider.finance_profile_id)
      .then((result) => { if (valid) setObservations(result.items); })
      .catch(() => { if (valid) setObservations([]); });
    return () => { valid = false; };
  }, [provider]);

  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null); setMessage(null);
    try {
      if (!source) throw new Error("Escolha uma fonte financeira.");
      if (!usePix && !useBoleto) throw new Error("Selecione pelo menos um método de teste.");
      if (!custom && (!matchingAccount || matchingAccount.status !== "active")) {
        throw new Error("A fonte precisa de uma conexão Composio ativa.");
      }
      setBusy(true);
      const created = await studentPaymentsApi.register({
        finance_profile_id: source.id, name: providerName.trim(),
        connection_kind: custom ? "custom_pending" : "composio",
        provider_slug: custom ? customSlug.trim() : (matchingAccount?.toolkit_slug || ""),
        methods: [...(usePix ? ["pix" as const] : []), ...(useBoleto ? ["boleto" as const] : [])],
      });
      await reload();
      setSelectedProvider(created.id);
      setProviderName("");
      setMessage("Perfil criado desabilitado. Nenhuma cobrança foi iniciada.");
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  async function toggle(current: SandboxProvider) {
    setBusy(true); setMessage(null); setError(null);
    try {
      await studentPaymentsApi.enable(current, !current.enabled);
      await reload();
      setMessage("Configuração atualizada apenas para sandbox. Pagamentos reais permanecem bloqueados.");
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  async function draft() {
    if (!provider || !observationId) return;
    setBusy(true); setMessage(null); setError(null);
    try {
      const result = await studentPaymentsApi.prepareDraft(provider.id, observationId, method);
      await reload();
      setSelectedDraft(result.id);
      setMessage("Rascunho preparado. Não existe Pix, boleto ou link de pagamento disponível.");
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }

  async function inspect(draftId: string) {
    setSelectedDraft(draftId); setEvidence([]); setError(null);
    try {
      const result = await studentPaymentsApi.evidence(draftId);
      setEvidence(result.items);
    } catch (reason) { setError(failure(reason)); }
  }

  return (
    <div className="min-h-screen bg-[#F9FAFB]">
      <Header title="Pagamentos em homologação" subtitle="Wave 4D — provedores por workspace, rascunhos e evidências sem movimentação real" />
      <main className="mx-auto max-w-[1250px] space-y-5 px-5 py-7 md:px-8 xl:px-10">
        <Link href="/conectores/financeiro" className="text-[12px] font-medium text-[#667085] hover:text-[#2563EB]">
          Fontes financeiras / Pagamentos em homologação
        </Link>
        <div className="rounded-xl border border-[#D0D5DD] bg-white p-5">
          <p className="text-[13px] font-semibold text-[#101828]">Ambiente de laboratório, não um checkout</p>
          <p className="mt-1 text-[12px] leading-6 text-[#667085]">
            Esta tela não cria cobranças, não gera códigos Pix ou boletos e não confirma liquidação.
            Eventos assinados aqui registram apenas evidências de sandbox. Pagamentos reais dependem
            de homologação do provedor, webhooks oficiais e autorização operacional.
          </p>
        </div>
        {error && <div role="alert" className="rounded-lg border border-[#FDA29B] bg-[#FFFBFA] p-4 text-[12px] text-[#B42318]">{error}</div>}
        {message && <div role="status" className="rounded-lg border border-[#D0D5DD] bg-white p-4 text-[12px] text-[#344054]">{message}</div>}

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ["Provedores cadastrados", providers.length],
            ["Perfis ativos em sandbox", providers.filter((p) => p.enabled).length],
            ["Rascunhos preparados", drafts.length],
            ["Transações reais", 0],
          ].map(([label,value]) => (
            <div key={label} className="rounded-xl border border-[#EAECF0] bg-white p-4">
              <p className="text-[11px] text-[#667085]">{label}</p>
              <p className="mt-2 text-[25px] font-semibold tabular-nums text-[#101828]">{value}</p>
            </div>
          ))}
        </div>

        <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
          <Card title="Configurar provedor por workspace" explanation="Várias conexões permitidas. Cada provedor fica isolado por origem, conta e instituição.">
            <form className="space-y-3" onSubmit={register}>
              <label className="block text-[12px] font-medium text-[#344054]">Nome do perfil
                <input className={"mt-1 " + inputClass} placeholder="Ex.: Financeiro Campus Norte" required
                  minLength={3} maxLength={100} value={providerName} onChange={(e) => setProviderName(e.target.value)}/>
              </label>
              <label className="block text-[12px] font-medium text-[#344054]">Tipo de conexão
                <select className={"mt-1 " + inputClass} value={custom ? "custom_pending" : "composio"}
                  onChange={(e) => { setCustom(e.target.value === "custom_pending"); setSourceId(""); }}>
                  <option value="composio">Composio — conta financeira conectada</option>
                  <option value="custom_pending">Conector nativo em homologação (desabilitado)</option>
                </select>
              </label>
              <label className="block text-[12px] font-medium text-[#344054]">Fonte financeira
                <select className={"mt-1 " + inputClass} value={sourceId} onChange={(e) => setSourceId(e.target.value)} required>
                  <option value="">Selecione uma fonte</option>
                  {eligibleSources.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </label>
              {!custom && source && (
                <p className="rounded-lg bg-[#F9FAFB] px-3 py-2 text-[11px] text-[#667085]">
                  Conta: {matchingAccount?.display_name || matchingAccount?.toolkit_slug || "Indisponível"} ·
                  {matchingAccount?.status === "active" ? " Conectada" : " Não autorizada"}
                </p>
              )}
              {custom && (
                <label className="block text-[12px] font-medium text-[#344054]">Identificador do conector
                  <input className={"mt-1 " + inputClass} value={customSlug} maxLength={80}
                    onChange={(e) => setCustomSlug(e.target.value)} />
                </label>
              )}
              <div>
                <p className="text-[12px] font-medium text-[#344054]">Métodos a homologar</p>
                <div className="mt-2 flex gap-5 text-[12px] text-[#475467]">
                  <label><input className="mr-2" type="checkbox" checked={usePix} onChange={(e) => setUsePix(e.target.checked)} />Pix</label>
                  <label><input className="mr-2" type="checkbox" checked={useBoleto} onChange={(e) => setUseBoleto(e.target.checked)} />Boleto</label>
                </div>
              </div>
              <button className={primary} type="submit" disabled={busy || !sourceId || !providerName.trim()}>
                Criar perfil desabilitado
              </button>
            </form>
          </Card>
          <Card title="Provedores cadastrados" explanation="Habilitar aqui libera somente rascunhos e testes de eventos. Não habilita pagamentos reais.">
            {loading && <p className="text-[12px] text-[#667085]">Consultando provedores…</p>}
            {!loading && !providers.length && <p className="text-[12px] text-[#667085]">Nenhum provedor de laboratório cadastrado.</p>}
            <div className="space-y-2">
              {providers.map((p) => (
                <div key={p.id} className={"rounded-xl border p-3 " +
                  (selectedProvider === p.id ? "border-[#2563EB] bg-[#EFF4FF]" : "border-[#E4E7EC] bg-white")}>
                  <button type="button" className="w-full text-left" onClick={() => { setSelectedProvider(p.id); setObservationId(""); }}>
                    <span className="text-[13px] font-semibold text-[#344054]">{p.name}</span>
                    <span className="ml-2 text-[11px] text-[#667085]">{p.provider_slug} · v{p.revision}</span>
                    <p className="mt-1 text-[11px] text-[#667085]">{p.methods.join(", ")} · {p.connection_kind === "custom_pending" ? "Aguardando conector" : "Composio"}</p>
                  </button>
                  <div className="mt-3 flex items-center justify-between">
                    <span className={"rounded-full px-2.5 py-1 text-[11px] " +
                      (p.enabled ? "bg-[#ECFDF3] text-[#027A48]" : "bg-[#F2F4F7] text-[#667085]")}>
                      {p.enabled ? "Ativo somente em sandbox" : "Desabilitado"}
                    </span>
                    <button type="button" className={secondary} disabled={busy || (p.connection_kind === "custom_pending" && !p.enabled)}
                      onClick={() => void toggle(p)}>{p.enabled ? "Desabilitar" : "Habilitar sandbox"}</button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="grid gap-5 xl:grid-cols-2">
          <Card title="Preparar rascunho" explanation="O valor é calculado pelo servidor usando o saldo da obrigação mais recente. Não é possível informá-lo manualmente.">
            <div className="space-y-3">
              <label className="block text-[12px] font-medium text-[#344054]">Provedor habilitado
                <select className={"mt-1 " + inputClass} value={selectedProvider} onChange={(e) => { setSelectedProvider(e.target.value); setObservationId(""); }}>
                  <option value="">Selecione</option>
                  {providers.map((p) => <option value={p.id} key={p.id}>{p.name}</option>)}
                </select>
              </label>
              <label className="block text-[12px] font-medium text-[#344054]">Obrigação financeira
                <select className={"mt-1 " + inputClass} value={observationId} onChange={(e) => setObservationId(e.target.value)}>
                  <option value="">Escolha um registro elegível</option>
                  {payable.map((o) => (
                    <option value={o.id} key={o.id}>{o.external_id} · {o.canonical_state} · {o.amount} BRL</option>
                  ))}
                </select>
              </label>
              <label className="block text-[12px] font-medium text-[#344054]">Método de laboratório
                <select className={"mt-1 " + inputClass} value={method} onChange={(e) => setMethod(e.target.value as "pix" | "boleto")}>
                  {provider?.methods.map((m) => <option key={m} value={m}>{m === "pix" ? "Pix (rascunho)" : "Boleto (rascunho)"}</option>)}
                </select>
              </label>
              <button className={primary} type="button" disabled={busy || !provider?.enabled || !observationId || !provider.methods.includes(method)}
                onClick={() => void draft()}>Preparar rascunho sem cobrança</button>
            </div>
          </Card>
          <Card title="Rascunhos e evidências" explanation="Eventos HMAC são provas de um emissor de laboratório, não confirmação de liquidação bancária.">
            {drafts.length === 0 ? (
              <p className="text-[12px] text-[#667085]">Nenhum rascunho registrado no workspace.</p>
            ) : <div className="space-y-2">
              {drafts.map((d) => (
                <button type="button" key={d.id} onClick={() => void inspect(d.id)}
                  className={"w-full rounded-lg border p-3 text-left " +
                    (selectedDraft === d.id ? "border-[#2563EB] bg-[#EFF4FF]" : "border-[#EAECF0]")}>
                  <p className="text-[12px] font-semibold text-[#344054]">{d.amount} BRL · {d.method.toUpperCase()} · Rascunho</p>
                  <p className="mt-1 text-[11px] text-[#667085]">{d.id.slice(0,8)}… · sem Pix, boleto ou pagamento real</p>
                </button>
              ))}
            </div>}
            {selectedDraft && <div className="mt-4 rounded-lg border border-[#EAECF0] bg-[#F9FAFB] p-3">
              <p className="text-[12px] font-semibold text-[#344054]">Histórico de sandbox</p>
              {evidence.length === 0 && <p className="mt-2 text-[11px] text-[#667085]">Nenhum evento disponível ou ainda não consultado.</p>}
              {evidence.map((e) => <div className="mt-2 text-[11px] text-[#667085]" key={e.event_id}>
                {e.state_reported} · {e.amount_reported} BRL · {new Date(e.occurred_at).toLocaleString("pt-BR")}
              </div>)}
            </div>}
          </Card>
        </div>
      </main>
    </div>
  );
}
