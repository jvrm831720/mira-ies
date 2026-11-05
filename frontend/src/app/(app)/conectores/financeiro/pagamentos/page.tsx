"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { financeApi, type FinanceProfile } from "@/lib/finance-reconciliation-api";
import { paymentPreparationApi, type PaymentConnector, type PaymentObservation, type PaymentProposal } from "@/lib/student-payment-preparation-api";

const field = "w-full rounded-lg border border-[#D0D5DD] bg-white px-3 py-2.5 text-[12px] text-[#344054] outline-none focus:border-[#2563EB]";
const button = "rounded-lg bg-[#101828] px-4 py-2.5 text-[12px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40";
const light = "rounded-lg border border-[#D0D5DD] bg-white px-3 py-2 text-[12px] font-semibold text-[#344054] disabled:opacity-40";
const legal = "Aprovação institucional em sandbox. Nenhuma cobrança, boleto, Pix, cartão ou liquidação está habilitada.";
function errorMessage(e: unknown) { return e instanceof Error ? e.message : "Operação indisponível."; }

export default function PaymentPreparationPage() {
  const [sources, setSources] = useState<FinanceProfile[]>([]);
  const [connectors, setConnectors] = useState<PaymentConnector[]>([]);
  const [orders, setOrders] = useState<PaymentProposal[]>([]);
  const [observations, setObservations] = useState<PaymentObservation[]>([]);
  const [selected, setSelected] = useState("");
  const [destinationWalletId, setDestinationWalletId] = useState("");
  const [financeSourceId, setFinanceSourceId] = useState("");
  const [observationId, setObservationId] = useState("");
  const [reason, setReason] = useState("Revisão e autorização institucional em sandbox.");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [finance, profiles, prepared] = await Promise.allSettled([
      financeApi.profiles(), paymentPreparationApi.connectors(),
      paymentPreparationApi.orders(),
    ]);
    if (finance.status === "fulfilled") {
      const loadedSources = finance.value.items;
      setSources(loadedSources);
      setFinanceSourceId((current) => current || loadedSources[0]?.id || "");
    }
    if (profiles.status === "fulfilled") {
      setConnectors(profiles.value.items);
      setSelected((id) => id || profiles.value.items[0]?.id || "");
    }
    if (prepared.status === "fulfilled") setOrders(prepared.value.items);
    if (profiles.status === "rejected") setError(errorMessage(profiles.reason));
    setLoading(false);
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const connector = useMemo(() => connectors.find((p) => p.id === selected), [selected, connectors]);
  const myOrders = orders.filter((item) => item.connector_id === selected);

  useEffect(() => {
    if (!connector || !financeSourceId) { setObservations([]); return; }
    let live = true;
    paymentPreparationApi.observations(financeSourceId)
      .then((response) => { if (live) setObservations(response.items); })
      .catch(() => { if (live) setObservations([]); });
    return () => { live = false; };
  }, [connector, financeSourceId]);

  async function act(work: () => Promise<unknown>, success: string) {
    setBusy(true); setError(null); setMessage(null);
    try {
      await work();
      setMessage(success);
      await refresh();
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  const payable = observations.filter((item) => (
    ["open", "overdue", "partially_paid"].includes(item.canonical_state)
    && Number(item.amount) > Number(item.paid_amount)
  ));
  return (
    <div className="min-h-screen bg-[#F9FAFB]">
      <Header title="Asaas • Repasse para a IES" subtitle="Carteira de destino · 100% do líquido · aprovação segura" />
      <main className="mx-auto max-w-[1180px] space-y-5 px-5 py-7 md:px-8">
        <Link href="/conectores/financeiro" className="text-[12px] font-medium text-[#2563EB]">
          Fontes financeiras / Preparação
        </Link>
        <section className="rounded-xl border border-[#EAECF0] bg-white p-4">
          <h2 className="text-[13px] font-semibold text-[#101828]">Sandbox — nenhuma movimentação de dinheiro</h2>
          <p className="mt-1 text-[12px] text-[#667085]">{legal} O split é de 100% do valor líquido (após taxas do Asaas), para a carteira validada da IES. Um walletId informado não é prova de titularidade; nenhum repasse real será executado.</p>
        </section>
        {error && <p role="alert" className="rounded-lg border border-[#FDA29B] bg-[#FFFBFA] p-3 text-[12px] text-[#B42318]">{error}</p>}
        {message && <p role="status" className="rounded-lg border border-[#EAECF0] bg-white p-3 text-[12px] text-[#344054]">{message}</p>}
        <div className="grid gap-5 lg:grid-cols-[380px_minmax(0,1fr)]">
          <div className="space-y-5">
            <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
              <h2 className="text-[14px] font-semibold text-[#101828]">Destinos Asaas</h2>
              <p className="mt-1 text-[11px] text-[#667085]">Um destino institucional Asaas por workspace, compartilhado por todas as fontes financeiras.</p>
              <div className="mt-4 space-y-2">
                {connectors.map((item) => <button key={item.id} type="button" onClick={() => setSelected(item.id)}
                  className={"w-full rounded-lg border p-3 text-left " + (selected === item.id ? "border-[#2563EB] bg-[#EFF4FF]" : "border-[#EAECF0]")}>
                  <span className="flex items-center justify-between text-[12px] font-semibold text-[#344054]">
                    {item.name}<span className="text-[10px] font-normal">{item.enabled ? "Preparação ativa" : "Desabilitada"}</span>
                  </span>
                  <p className="mt-1 text-[11px] text-[#667085]">Asaas • carteira {item.destination_wallet_id.slice(0, 8)}… • {item.destination_verification_status === "pending" ? "aguardando validação" : item.destination_verification_status}</p>
                </button>)}
                {loading && <p className="text-[11px] text-[#667085]">Carregando...</p>}
                {!loading && connectors.length === 0 && <p className="text-[11px] text-[#667085]">Nenhum PSP preparado.</p>}
              </div>
              {connector && <button type="button" className={"mt-4 " + light} disabled={busy}
                onClick={() => void act(() => paymentPreparationApi.toggleConnector(connector, !connector.enabled),
                connector.enabled ? "Preparação desabilitada." : "Apenas a preparação de propostas foi habilitada.")}>
                {connector.enabled ? "Desabilitar perfil" : "Habilitar preparação sandbox"}
              </button>}
            </section>
            <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
              <h2 className="text-[14px] font-semibold text-[#101828]">Conta de destino da IES</h2>
              <p className="mt-1 text-[11px] text-[#667085]">Informe somente o walletId da conta Asaas que receberá os pagamentos. A MIRA fixa o split em 100% do valor líquido.</p>
              <div className="mt-3 space-y-3">
                <label className="block text-[12px] font-medium text-[#344054]">Carteira de destino Asaas (walletId)
                  <input className={"mt-1 " + field} value={destinationWalletId} onChange={(e) => setDestinationWalletId(e.target.value.trim())} placeholder="00000000-0000-4000-8000-000000000000" maxLength={36} />
                </label>
              </div>
              <button type="button" className={"mt-4 " + button} disabled={busy || Boolean(connector) || !destinationWalletId}
                onClick={() => void act(
                  () => paymentPreparationApi.createConnector({ destination_wallet_id: destinationWalletId }),
                  "Destino Asaas salvo como pendente de validação. Ainda não foi conectado nem habilitado para cobranças reais.",
                )}>Criar perfil sandbox</button>
            </section>
          </div>
          <div className="space-y-5">
            <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
              <h2 className="text-[14px] font-semibold text-[#101828]">Preparar proposta Asaas</h2>
              <p className="mt-1 text-[12px] text-[#667085]">O valor vem da fonte financeira. A regra futura será 100% do líquido para a IES; o split permanece não executado.</p>
              <label className="mt-4 block text-[12px] font-medium text-[#344054]">Fonte financeira (qualquer integração do workspace)
                <select className={"mt-1 " + field} value={financeSourceId}
                  onChange={(e) => { setFinanceSourceId(e.target.value); setObservationId(""); }}>
                  <option value="">Selecione a origem</option>
                  {sources.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.source_kind})</option>)}
                </select>
              </label>
              <label className="mt-4 block text-[12px] font-medium text-[#344054]">Obrigação financeira
                <select className={"mt-1 " + field} value={observationId} onChange={(e) => setObservationId(e.target.value)}>
                  <option value="">Selecione uma obrigação elegível</option>
                  {payable.map((x) => <option key={x.id} value={x.id}>
                    {x.external_id} · R$ {x.amount} (relato: {x.canonical_state})
                  </option>)}
                </select>
              </label>
              <button className={"mt-4 " + button} type="button" disabled={busy || !connector?.enabled || !observationId}
                onClick={() => void act(
                  () => paymentPreparationApi.prepare(selected, observationId),
                  "Proposta criada sem qualquer cobrança ou pagamento.",
                )}>Criar proposta sem pagamento</button>
            </section>
            <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
              <h2 className="text-[14px] font-semibold text-[#101828]">Aprovações</h2>
              <p className="mt-1 text-[12px] text-[#667085]">Uma segunda pessoa deve aprovar. Aprovar não inicia checkout.</p>
              <label className="mt-4 block text-[12px] font-medium text-[#344054]">Justificativa
                <input className={"mt-1 " + field} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <div className="mt-4 divide-y divide-[#EAECF0]">
                {myOrders.length === 0 && <p className="py-4 text-[12px] text-[#667085]">Nenhuma proposta deste perfil.</p>}
                {myOrders.map((o) => <div key={o.id} className="space-y-2 py-4">
                  <div className="flex justify-between gap-3 text-[12px] text-[#344054]">
                    <span className="font-semibold">R$ {o.amount}</span><span>{o.status.replaceAll("_", " ")}</span>
                  </div>
                  <p className="text-[11px] text-[#667085]">Aluno {o.student_id.slice(0, 8)}… · sem liquidação confirmada</p>
                  <div className="flex flex-wrap gap-2">
                    {o.status === "draft" && <button className={light} disabled={busy || reason.length < 5}
                      onClick={() => void act(() => paymentPreparationApi.review(o, "awaiting_approval", reason),
                        "Proposta enviada à aprovação.")}>Enviar à aprovação</button>}
                    {o.status === "awaiting_approval" && <button className={light} disabled={busy || reason.length < 5}
                      onClick={() => void act(() => paymentPreparationApi.review(o, "approved", reason),
                        "Proposta aprovada em sandbox; nenhuma cobrança foi criada.")}>Aprovar</button>}
                    {o.status !== "cancelled" && <button className={light} disabled={busy || reason.length < 5}
                      onClick={() => void act(() => paymentPreparationApi.review(o, "cancelled", reason),
                        "Proposta cancelada.")}>Cancelar</button>}
                  </div>
                </div>)}
              </div>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
