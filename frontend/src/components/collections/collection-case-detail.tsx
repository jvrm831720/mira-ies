"use client";

import type { CollectionCaseDetail } from "@/lib/collections-api";

export function Currency({ value }: { value: string | null }) {
  if (value === null) return <span className="text-[#9299A4]">Não informado</span>;
  const amount = Number(value);
  if (!Number.isFinite(amount)) return <span>{value}</span>;
  return <span className="tabular-nums">{new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(amount)}</span>;
}

export function Time({ value }: { value: string | null }) {
  if (!value) return <span className="text-[#9299A4]">Sem registro</span>;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return <span>{value}</span>;
  return <time dateTime={value}>{new Intl.DateTimeFormat("pt-BR", {dateStyle:"short",timeStyle:"short"}).format(date)}</time>;
}

export function CaseDetail({ record, loading, error, onClose }: {
  record: CollectionCaseDetail | undefined;
  loading: boolean;
  error: boolean;
  onClose: () => void;
}) {
  return <aside aria-label="Detalhes do caso" className="rounded-xl border border-[#E6E7EA] bg-white p-5 lg:sticky lg:top-6 lg:self-start">
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold">Caso financeiro</h2>
      <button type="button" onClick={onClose} className="rounded-md border px-2 py-1 text-xs hover:bg-[#F8F9FA]">Fechar</button>
    </div>
    {loading && <p role="status" className="mt-5 text-xs text-[#667085]">Carregando detalhes…</p>}
    {error && <p role="alert" className="mt-5 text-xs text-[#B42318]">Não foi possível consultar este caso.</p>}
    {record && <>
      <dl className="mt-5 space-y-3 text-xs">
        {([
          ["Referência", record.case.external_ref],
          ["Estado da fonte", labels[record.case.status] ?? record.case.status],
          ["Identificador relacionado", record.case.subject_ref],
          ["Origem", record.case.source],
          ["Versão da origem", String(record.case.source_version)],
          ["Evidência", record.case.evidence_ref],
        ] as const).map(([label, value]) => <div key={label} className="grid grid-cols-[110px_1fr] gap-2 border-b border-[#F0F1F3] pb-2">
          <dt className="text-[#858C96]">{label}</dt><dd className="break-all text-[#101112]">{value}</dd>
        </div>)}
        <div className="flex justify-between gap-2"><dt className="text-[#858C96]">Saldo informado</dt><dd><Currency value={record.case.balance}/></dd></div>
        <div className="flex justify-between gap-2"><dt className="text-[#858C96]">Verificado em</dt><dd><Time value={record.case.verified_at}/></dd></div>
      </dl>
      <h3 className="mb-2 mt-7 text-xs font-semibold">Eventos financeiros confirmados pela origem</h3>
      {record.payment_events.length === 0
        ? <p className="rounded-lg bg-[#F8F9FA] p-3 text-xs text-[#667085]">Nenhum evento financeiro confirmado nesta consulta.</p>
        : <ol className="space-y-2">{record.payment_events.map(event=><li key={event.id} className="rounded-lg border border-[#E6E7EA] p-3 text-xs">
          <div className="flex justify-between gap-3"><strong><Currency value={event.amount_paid}/></strong><Time value={event.paid_at}/></div>
          <p className="mt-1 text-[#667085]">Fonte: {event.source} · {event.obligation_status}</p>
          <p className="mt-1 text-[#667085]">Saldo após evento: <Currency value={event.remaining_balance}/></p>
        </li>)}</ol>}
      {record.payment_events_limited && <p className="mt-2 text-xs text-[#946200]">Somente os 100 eventos mais recentes são apresentados.</p>}
      <p className="mt-5 border-t pt-3 text-[11px] text-[#858C96]">Registros de origem não são comprovantes bancários nem garantem conciliação externa.</p>
    </>}
  </aside>;
}

