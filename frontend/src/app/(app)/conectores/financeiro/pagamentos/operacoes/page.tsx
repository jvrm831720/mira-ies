"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { asaasApi, type AsaasCharge } from "@/lib/asaas-official-api";
import { financeApi, type FinanceProfile } from "@/lib/finance-reconciliation-api";
import { studentPaymentsApi, type FinancialObservation } from "@/lib/student-payments-api";

const input = "w-full rounded-lg border border-[#D0D5DD] bg-white px-3 py-2 text-[12px] outline-none focus:border-[#2563EB]";
const btn = "rounded-lg bg-[#101828] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-40";
const outline = "rounded-lg border border-[#D0D5DD] px-4 py-2 text-[12px] font-semibold text-[#344054] disabled:opacity-40";
const brl = (value: string) => new Intl.NumberFormat("pt-BR", {style: "currency",currency: "BRL"}).format(Number(value));
const states = (c: AsaasCharge) => c.needs_review ? "Exige revisão"
  : c.split_settled_verified ? "Split liquidado na IES"
  : c.payment_received_verified ? "Pagamento recebido; split pendente"
  : c.creation_state === "created" ? "Cobrança emitida"
  : c.creation_state === "prepared" ? "Preparada, aguardando aprovação"
  : c.creation_state;

export default function AsaasOperationsPage() {
  const [environment,setEnvironment] = useState("desabilitado");
  const [enabled,setEnabled] = useState(false);
  const [sources,setSources] = useState<FinanceProfile[]>([]);
  const [sourceId,setSourceId] = useState("");
  const [observations,setObservations] = useState<FinancialObservation[]>([]);
  const [observationId,setObservationId] = useState("");
  const [dueDate,setDueDate] = useState("");
  const [method,setMethod] = useState<"pix"|"boleto">("pix");
  const [charges,setCharges] = useState<AsaasCharge[]>([]);
  const [events,setEvents] = useState<Array<{event_id:string;event_type:string}>>([]);
  const [ticket,setTicket] = useState("");
  const [confirmId,setConfirmId] = useState<string|null>(null);
  const [busy,setBusy] = useState(false);
  const [notice,setNotice] = useState("");
  const [error,setError] = useState("");

  const load = useCallback(async()=>{
    const [health,catalog,history,webhooks] = await Promise.allSettled([
      asaasApi.readiness(),financeApi.profiles(),asaasApi.charges(),asaasApi.events(),
    ]);
    if(health.status==="fulfilled"){
      setEnabled(health.value.enabled);setEnvironment(health.value.environment);
    }
    if(catalog.status==="fulfilled"){
      const items=catalog.value.items;setSources(items);setSourceId(id=>id||items[0]?.id||"");
    }
    if(history.status==="fulfilled")setCharges(history.value.items);
    if(webhooks.status==="fulfilled")setEvents(webhooks.value.items);
  },[]);
  useEffect(()=>{void load();},[load]);
  useEffect(()=>{
    if(!sourceId){setObservations([]);return;}
    let mounted=true;
    studentPaymentsApi.observations(sourceId).then(result=>{
      if(mounted)setObservations(result.items);
    }).catch(()=>{if(mounted)setObservations([]);});
    return()=>{mounted=false;};
  },[sourceId]);

  async function execute(action:()=>Promise<unknown>,message:string){
    setBusy(true);setError("");setNotice("");
    try{await action();setNotice(message);await load();}
    catch(e){setError(e instanceof Error?e.message:"Operação indisponível.");}
    finally{setBusy(false);setConfirmId(null);}
  }
  async function prepare(e:FormEvent<HTMLFormElement>){
    e.preventDefault();
    await execute(()=>asaasApi.prepare(observationId,method,dueDate),
      "Preparação gravada. A emissão exige outra confirmação.");
  }
  return <div className="min-h-screen bg-[#F9FAFB]">
    <Header title="Operações Asaas" subtitle="Emissão autorizada e conciliação do Split Payment da IES"/>
    <main className="mx-auto max-w-[1140px] space-y-5 px-5 py-7 md:px-8">
      <Link href="/conectores/financeiro/pagamentos" className="text-[12px] text-[#667085]">Recebimentos / Operações</Link>
      <div className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <div className="flex justify-between gap-3">
          <strong className="text-[14px] text-[#101828]">Integração oficial Asaas</strong>
          <span className="text-[11px] text-[#667085]">Ambiente: {environment}</span>
        </div>
        <p className="mt-2 text-[12px] leading-5 text-[#667085]">
          A IES recebe 100% do líquido. O envio exige autorização institucional e não é repetido após timeout.
          Um pagamento recebido não significa que o Split foi liquidado.
        </p>
      </div>
      {error&&<p role="alert" className="rounded-lg border border-red-200 bg-white p-3 text-[12px] text-red-700">{error}</p>}
      {notice&&<p role="status" className="rounded-lg border border-[#EAECF0] bg-white p-3 text-[12px]">{notice}</p>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["Cobranças",charges.length],
          ["Aguardam aprovação",charges.filter(c=>c.creation_state==="prepared").length],
          ["Pagamentos recebidos",charges.filter(c=>c.payment_received_verified).length],
          ["Splits liquidados",charges.filter(c=>c.split_settled_verified).length],
        ].map(([name,value])=><div key={name} className="rounded-xl border border-[#EAECF0] bg-white p-4">
          <p className="text-[11px] text-[#667085]">{name}</p>
          <p className="mt-1 text-[24px] font-semibold tabular-nums">{value}</p>
        </div>)}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
          <h2 className="text-[15px] font-semibold">Preparar cobrança</h2>
          <p className="mt-1 text-[12px] text-[#667085]">O valor vem da obrigação, nunca do formulário.</p>
          <form onSubmit={prepare} className="mt-4 space-y-3">
            <label className="block text-[12px]">Origem financeira
              <select className={"mt-1 "+input} value={sourceId} onChange={e=>{setSourceId(e.target.value);setObservationId("");}}>
                <option value="">Selecione</option>
                {sources.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
            <label className="block text-[12px]">Obrigação
              <select className={"mt-1 "+input} value={observationId} onChange={e=>setObservationId(e.target.value)}>
                <option value="">Selecione</option>
                {observations.filter(o=>["open","overdue","partially_paid"].includes(o.canonical_state)).map(o=>
                  <option key={o.id} value={o.id}>{o.external_id} · {brl(o.amount)}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-[12px]">Método
                <select className={"mt-1 "+input} value={method} onChange={e=>setMethod(e.target.value as "pix"|"boleto")}>
                  <option value="pix">Pix</option><option value="boleto">Boleto</option>
                </select>
              </label>
              <label className="text-[12px]">Vencimento
                <input className={"mt-1 "+input} type="date" value={dueDate} onChange={e=>setDueDate(e.target.value)} required />
              </label>
            </div>
            <button className={btn} disabled={busy||!enabled||!observationId||!dueDate}>Preparar sem emitir</button>
          </form>
        </section>
        <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
          <h2 className="text-[15px] font-semibold">Homologação da carteira recebedora</h2>
          <p className="mt-1 text-[12px] leading-5 text-[#667085]">
            Após conferência externa da titularidade na Asaas, outro operador registra a referência de aprovação.
            A instituição só configura sua carteira na tela anterior.
          </p>
          <input className={"mt-4 "+input} placeholder="Referência comprovada na Asaas"
            value={ticket} maxLength={120} onChange={e=>setTicket(e.target.value)}/>
          <button className={"mt-3 "+outline} disabled={busy||!enabled||ticket.length<8}
            onClick={()=>void execute(()=>asaasApi.verifyWallet(ticket),"Homologação registrada em auditoria.")}>
            Registrar revisão independente
          </button>
        </section>
      </div>
      <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <h2 className="text-[15px] font-semibold">Cobranças</h2>
        {charges.length===0&&<p className="mt-3 text-[12px] text-[#667085]">Nenhuma cobrança preparada.</p>}
        <div className="mt-3 divide-y divide-[#EAECF0]">{charges.map(charge=>
          <div key={charge.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <p className="text-[13px] font-semibold">{brl(charge.amount)} · {charge.method.toUpperCase()}</p>
              <p className="mt-1 text-[11px] text-[#667085]">{states(charge)} · {charge.environment}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {charge.creation_state==="prepared"?<>
                <label className="flex gap-2 text-[11px]"><input type="checkbox"
                  checked={confirmId===charge.id} onChange={e=>setConfirmId(e.target.checked?charge.id:null)}/>Confirmar emissão</label>
                <button className={btn} disabled={busy||!enabled||confirmId!==charge.id}
                  onClick={()=>void execute(()=>asaasApi.issue(charge.id),"Cobrança emitida; confirme o estado na Asaas.")}>Autorizar emissão</button>
              </>:<button className={outline} disabled={busy||!enabled}
                onClick={()=>void execute(()=>asaasApi.reconcile(charge.id),"Situação consultada na Asaas.")}>Reconciliar</button>}
            </div>
          </div>)}</div>
      </section>
      <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <h2 className="text-[15px] font-semibold">Eventos da Asaas</h2>
        {events.slice(0,25).map(e=><p key={e.event_id} className="mt-2 text-[11px] text-[#667085]">{e.event_type} · {e.event_id.slice(0,10)}</p>)}
        {events.length===0&&<p className="mt-3 text-[12px] text-[#667085]">Sem eventos recebidos.</p>}
      </section>
    </main>
  </div>;
}
