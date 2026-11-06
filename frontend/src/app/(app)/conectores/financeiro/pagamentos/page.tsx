"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { financeApi, type FinanceProfile } from "@/lib/finance-reconciliation-api";
import {
  studentPaymentsApi, type AsaasDestination, type AsaasSplitPreview,
  type FinancialObservation,
} from "@/lib/student-payments-api";

const inputStyle = "w-full rounded-xl border border-[#D0D5DD] bg-white px-3.5 py-3 text-[13px] text-[#344054] outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/10";
const primary = "rounded-lg bg-[#101828] px-4 py-2.5 text-[12px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40";
const secondary = "rounded-lg border border-[#D0D5DD] bg-white px-4 py-2.5 text-[12px] font-semibold text-[#344054] disabled:opacity-40";
const canPrepare = new Set(["open", "overdue", "partially_paid"]);
const accountIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function asMessage(error: unknown) {
  return error instanceof Error ? error.message : "Não foi possível concluir a operação.";
}

export default function AsaasWorkspacePaymentsPage() {
  const [wallet, setWallet] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [destination, setDestination] = useState<AsaasDestination | null>(null);
  const [sources, setSources] = useState<FinanceProfile[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [records, setRecords] = useState<FinancialObservation[]>([]);
  const [observationId, setObservationId] = useState("");
  const [preview, setPreview] = useState<AsaasSplitPreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const results = await Promise.allSettled([
      studentPaymentsApi.asaasDestination(), financeApi.profiles(),
    ]);
    if (results[0].status === "fulfilled") {
      const current = results[0].value;
      setDestination(current);
      setWallet(current.wallet_id || "");
      setError(null);
    } else {
      setError(asMessage(results[0].reason));
    }
    if (results[1].status === "fulfilled") {
      const available = results[1].value.items;
      setSources(available);
      setSourceId((previous) => previous || available[0]?.id || "");
    }
    setLoading(false);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    if (!sourceId) { setRecords([]); setObservationId(""); return; }
    let valid = true;
    studentPaymentsApi.observations(sourceId)
      .then((result) => {
        if (!valid) return;
        setRecords(result.items.filter((record) => canPrepare.has(record.canonical_state)));
        setObservationId("");
        setPreview(null);
      })
      .catch(() => { if (valid) { setRecords([]); setObservationId(""); } });
    return () => { valid = false; };
  }, [sourceId]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null); setError(null);
    if (!confirmed) {
      setError("Confirme que a carteira pertence à instituição antes de salvar.");
      return;
    }
    if (!accountIdPattern.test(wallet.trim())) {
      setError("Informe o walletId da conta Asaas da instituição (UUID).");
      return;
    }
    setBusy(true);
    try {
      const result = await studentPaymentsApi.saveAsaasDestination(wallet.trim(), destination?.version ?? null);
      setDestination(result);
      setWallet(result.wallet_id || "");
      setConfirmed(false);
      setPreview(null);
      setMessage("Carteira salva. A titularidade ainda precisa ser verificada pela MIRA antes de pagamentos reais.");
    } catch (reason) { setError(asMessage(reason)); }
    finally { setBusy(false); }
  }

  async function simulate() {
    if (!observationId) return;
    setBusy(true); setError(null); setMessage(null); setPreview(null);
    try {
      setPreview(await studentPaymentsApi.previewAsaasSplit(observationId));
    } catch (reason) { setError(asMessage(reason)); }
    finally { setBusy(false); }
  }

  const status = destination?.status || "missing";
  const statusLabel = status === "verified" ? "Carteira verificada"
    : status === "pending" ? "Aguardando verificação"
      : status === "rejected" ? "Verificação necessária" : "Não configurada";

  return (
    <div className="min-h-screen bg-[#F9FAFB]">
      <Header title="Recebimentos" subtitle="Asaas Split Payment — destino financeiro único por workspace" />
      <main className="mx-auto max-w-[1000px] space-y-5 px-5 py-7 md:px-8">
        <div className="flex justify-end"><Link href="/conectores/financeiro/pagamentos/operacoes" className="text-[12px] font-semibold text-[#2563EB] hover:underline">Operações de cobrança e conciliação Asaas</Link></div>
        <Link href="/conectores/financeiro" className="text-[12px] font-medium text-[#667085] hover:text-[#2563EB]">
          Fontes financeiras / Recebimentos
        </Link>

        <section className="rounded-2xl border border-[#E4E7EC] bg-white p-6 shadow-[0_1px_2px_rgba(16,24,40,0.03)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Configuração da instituição</p>
              <h1 className="mt-2 text-[22px] font-semibold tracking-[-0.03em] text-[#101828]">Para onde serão enviados os pagamentos?</h1>
              <p className="mt-2 max-w-[650px] text-[13px] leading-6 text-[#667085]">
                Informe uma única carteira Asaas. Ela será o destino padrão de todos os recebimentos dos alunos deste workspace,
                mesmo com várias integrações financeiras ou importações.
              </p>
            </div>
            <span className={"rounded-full px-3 py-1.5 text-[11px] font-medium " +
              (status === "verified" ? "bg-[#ECFDF3] text-[#027A48]" : "bg-[#F2F4F7] text-[#475467]")}>
              {loading ? "Carregando…" : statusLabel}
            </span>
          </div>

          <div className="mt-6 rounded-xl border border-[#EAECF0] bg-[#F9FAFB] p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-[12px] font-medium text-[#344054]">Repasse à IES</p>
                <p className="mt-0.5 text-[11px] text-[#667085]">Percentual sobre o valor líquido da cobrança</p>
              </div>
              <span className="text-[27px] font-semibold tracking-[-0.04em] text-[#101828]">100%</span>
            </div>
            <p className="mt-3 border-t border-[#EAECF0] pt-3 text-[11px] leading-5 text-[#667085]">
              O Asaas desconta as taxas aplicáveis antes do Split. Não há divisão adicional configurável
              pela IES nem transferência automática para contas bancárias externas.
            </p>
          </div>

          <form className="mt-6 space-y-4" onSubmit={(event) => void save(event)}>
            <label className="block space-y-2 text-[12px] font-semibold text-[#344054]">
              Wallet ID da conta Asaas da instituição
              <input
                className={inputStyle} value={wallet} required disabled={busy || loading}
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                autoComplete="off" autoCapitalize="off" spellCheck={false} maxLength={36}
                onChange={(event) => { setWallet(event.target.value); setConfirmed(false); }}
              />
            </label>
            <p className="text-[11px] leading-5 text-[#667085]">
              Este identificador pertence à conta Asaas que receberá o Split.
              Não insira agência, conta, chave Pix, senha ou chave de API.
              A conta da IES precisa existir no Asaas e ser diferente da conta emissora.
            </p>
            <label className="flex items-start gap-2 text-[12px] leading-5 text-[#475467]">
              <input type="checkbox" className="mt-1" checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)} />
              Confirmo que esta carteira pertence à instituição e está autorizada a receber os repasses.
            </label>
            <button type="submit" disabled={busy || loading || !confirmed || !accountIdPattern.test(wallet.trim())}
              className={primary}>{busy ? "Salvando…" : destination?.configured ? "Atualizar destino" : "Salvar destino financeiro"}</button>
          </form>
        </section>

        {error && <div role="alert" className="rounded-xl border border-[#FDA29B] bg-[#FFFBFA] p-4 text-[12px] text-[#B42318]">{error}</div>}
        {message && <div role="status" className="rounded-xl border border-[#D0D5DD] bg-white p-4 text-[12px] text-[#344054]">{message}</div>}

        <section className="rounded-2xl border border-[#EAECF0] bg-white p-5">
          <h2 className="text-[15px] font-semibold text-[#101828]">Simulação de repasse</h2>
          <p className="mt-1 text-[12px] leading-5 text-[#667085]">
            Confira como a configuração seria aplicada a uma obrigação real já importada.
            Esta simulação não gera cobranças, QR Codes, boletos ou movimentações.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="block text-[12px] font-medium text-[#344054]">
              Origem financeira
              <select className={"mt-1 " + inputStyle} value={sourceId}
                onChange={(event) => setSourceId(event.target.value)}>
                <option value="">Selecione uma origem</option>
                {sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
              </select>
            </label>
            <label className="block text-[12px] font-medium text-[#344054]">
              Obrigação financeira
              <select className={"mt-1 " + inputStyle} value={observationId}
                onChange={(event) => { setObservationId(event.target.value); setPreview(null); }}>
                <option value="">Selecione uma obrigação elegível</option>
                {records.map((record) => <option key={record.id} value={record.id}>
                  {record.external_id} · R$ {record.amount} · {record.canonical_state}
                </option>)}
              </select>
            </label>
          </div>
          <button type="button" className={"mt-4 " + secondary}
            disabled={busy || !destination?.configured || !observationId}
            onClick={() => void simulate()}>Simular Split sem cobrar</button>

          {preview && <div className="mt-5 rounded-xl border border-[#EAECF0] bg-[#F9FAFB] p-4">
            <p className="text-[12px] font-semibold text-[#344054]">Prévia calculada pelo servidor</p>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-[12px] text-[#475467]">
              <span>Valor da obrigação: <strong>R$ {preview.gross_charge_value}</strong></span>
              <span>Repasse à IES: <strong>100% do líquido</strong></span>
            </div>
            <p className="mt-3 text-[11px] leading-5 text-[#667085]">
              Carteira destinatária: {preview.split[0]?.walletId}. A MIRA configura o percentual,
              mas o Asaas calcula o repasse sobre o valor efetivamente líquido após taxas.
            </p>
            <p className="mt-2 text-[11px] font-medium text-[#B54708]">
              Verificação do destino: {preview.recipient_verification}. Nenhum pagamento foi criado.
            </p>
          </div>}
        </section>

        <div className="rounded-xl border border-[#EAECF0] bg-white p-4 text-[12px] leading-6 text-[#667085]">
          O recebimento real depende da habilitação do Split na conta Asaas emissora, da verificação
          de titularidade da carteira, da integração oficial de Pix/boleto e de webhooks homologados.
          <strong className="text-[#344054]"> Pagamentos reais permanecem desabilitados nesta Wave.</strong>
        </div>
      </main>
    </div>
  );
}
