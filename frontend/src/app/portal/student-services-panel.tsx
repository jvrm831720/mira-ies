"use client";

import { useEffect, useState, type FormEvent } from "react";
import { serviceStatusLabel, serviceStatusTone } from "./lib/service-status";

type ServiceRequest = {
  id: string; category: string; subject: string; description: string;
  status: string; created_at: string; due_at?: string | null; priority?: string;
};
type PortalRequestDetail = {
  request: ServiceRequest;
  comments: {id:string; actor_type:string; body:string; created_at:string}[];
  attachments: {id:string;filename:string;byte_count:number;created_at:string}[];
  events: {id:string;status:string;note:string|null;occurred_at:string}[];
};
type PortalNotification = {id:string;request_id:string;title:string;read_at:string|null;created_at:string};
type Document = { id: string; title: string; kind: string; published_at: string | null };
type Financial = { id: string; label: string; amount: string; currency: string; status: string; observed_at: string };
type StudentAsaasCharge = {
  id: string; method: "pix" | "boleto"; amount: string; currency: string;
  payment_received_verified: boolean; split_settled_verified: boolean;
  environment: "sandbox" | "production";
};
type PaymentInstructions = {
  method: "pix" | "boleto";
  copy_and_paste?: string;
  expiration_date?: string | null;
  identification_field?: string;
};
type View = "requests" | "documents" | "financial";
type ServiceHistory = { subject: string; events: Array<{ status: string; occurred_at: string }> };

async function serviceFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api/v1/student-portal/services" + path, {
    ...init, credentials: "same-origin", cache: "no-store",
    headers: {
      ...(typeof init?.body === "string" ? { "Content-Type": "application/json" } : {}),
      ...(init?.method && init.method !== "GET" ? { "X-Mira-Portal-Action": "1" } : {}),
    },
  });
  if (!response.ok) {
    const error = new Error(response.status === 503
      ? "Serviços ainda em homologação pela instituição."
      : response.status === 401 ? "Sua sessão expirou." : "Operação indisponível.");
    throw error;
  }
  return response.json() as Promise<T>;
}

const choices: { id: View; label: string }[] = [
  { id: "requests", label: "Solicitações" }, { id: "documents", label: "Documentos" },
  { id: "financial", label: "Financeiro" },
];
const categories = [
  { value: "declaration", label: "Declaração" },
  { value: "transcript", label: "Histórico acadêmico" },
  { value: "enrollment", label: "Matrícula" },
  { value: "academic_review", label: "Revisão acadêmica" },
  { value: "other", label: "Outro assunto" },
];
const financeStates: Record<string, string> = {
  open: "Em aberto", overdue: "Vencido", partially_paid: "Pagamento parcial informado",
  reported_paid: "Pagamento informado (não confirmado)", cancelled: "Cancelado",
  disputed: "Em disputa", unknown: "Situação não verificada",
};
function brazilMoney(raw: Financial) {
  const n = Number(raw.amount);
  return raw.currency === "BRL" && Number.isFinite(n)
    ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(n)
    : "Valor não disponível";
}

export function StudentServicesPanel({ initialView = "requests", standalone = false }: { initialView?: View; standalone?: boolean }) {
  const [view, setView] = useState<View>(initialView);
  const [requests, setRequests] = useState<ServiceRequest[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [financial, setFinancial] = useState<Financial[]>([]);
  const [asaasCharges, setAsaasCharges] = useState<StudentAsaasCharge[]>([]);
  const [paymentInstructions, setPaymentInstructions] = useState<PaymentInstructions | null>(null);
  const [category, setCategory] = useState("declaration");
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [documentText, setDocumentText] = useState<string | null>(null);
  const [documentTitle, setDocumentTitle] = useState("");
  const [documentProof, setDocumentProof] = useState<string | null>(null);
  const [documentProofValid, setDocumentProofValid] = useState<boolean | null>(null);
  const [history, setHistory] = useState<ServiceHistory | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadIndex, setReloadIndex] = useState(0);
  const [composeOpen, setComposeOpen] = useState(false);
  const [detail, setDetail] = useState<PortalRequestDetail | null>(null);
  const [notifications, setNotifications] = useState<PortalNotification[]>([]);
  const [reply, setReply] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [replySending, setReplySending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true); setMessage(null); setLoadError(null); setDocumentText(null); setHistory(null);
    setDocumentProof(null); setDocumentProofValid(null);
    setDetail(null);
    if (view === "requests") {
      void serviceFetch<{items:PortalNotification[]}>("/notifications")
        .then(data => { if (active) setNotifications(data.items); })
        .catch(() => { if (active) setNotifications([]); });
    }
    const endpoint = view === "requests" ? "/requests" : view === "documents" ? "/documents" : "/financial";
    serviceFetch<{ items: ServiceRequest[] | Document[] | Financial[] }>(endpoint)
      .then((data) => {
        if (!active) return;
        if (view === "requests") setRequests(data.items as ServiceRequest[]);
        if (view === "documents") setDocuments(data.items as Document[]);
        if (view === "financial") setFinancial(data.items as Financial[]);
      })
      .catch((err: Error) => { if (active) setLoadError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [view, reloadIndex]);

  useEffect(() => {
    if (view !== "financial") return;
    let active = true;
    setPaymentInstructions(null);
    fetch("/api/v1/student-portal/services/asaas/charges", {
      cache: "no-store", credentials: "same-origin",
    }).then((r) => r.ok ? r.json() as Promise<{ items: StudentAsaasCharge[] }> : { items: [] })
      .then((value) => { if (active) setAsaasCharges(value.items); })
      .catch(() => { if (active) setAsaasCharges([]); });
    return () => { active = false; };
  }, [view]);

  async function showPayment(charge: StudentAsaasCharge) {
    setMessage(null); setPaymentInstructions(null);
    try {
      const result = await fetch(
        "/api/v1/student-portal/services/asaas/charges/" + encodeURIComponent(charge.id) + "/instructions",
        { cache: "no-store", credentials: "same-origin" },
      );
      if (!result.ok) throw new Error("Instruções de pagamento indisponíveis.");
      setPaymentInstructions(await result.json() as PaymentInstructions);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Não foi possível consultar as instruções.");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSending(true); setMessage(null);
    try {
      const created = await serviceFetch<ServiceRequest>("/requests", {
        method: "POST", body: JSON.stringify({ category, subject, description }),
      });
      setRequests((items) => [created, ...items]);
      setSubject(""); setDescription(""); setComposeOpen(false); setMessage("Solicitação registrada com sucesso.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Não foi possível criar solicitação.");
    } finally { setSending(false); }
  }

  async function openDocument(item: Document) {
    try {
      const data = await serviceFetch<{ content_text: string }>("/documents/" + encodeURIComponent(item.id));
      setDocumentTitle(item.title); setDocumentText(data.content_text);
    } catch (err) { setMessage(err instanceof Error ? err.message : "Documento indisponível."); }
  }
  async function verifyDocument(item: Document) {
    setDocumentProof(null);
    setDocumentProofValid(null);
    try {
      const proof = await serviceFetch<{ verification_code: string }>(
        "/documents/" + encodeURIComponent(item.id) + "/proof"
      );
      const result = await fetch("/api/v1/public/academic-documents/verify", {
        method: "POST",
        credentials: "omit",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: proof.verification_code }),
      });
      if (!result.ok) throw new Error("Não foi possível verificar a integridade.");
      const status = await result.json() as { valid: boolean };
      setDocumentProof(proof.verification_code);
      setDocumentProofValid(status.valid);
    } catch {
      setMessage("Comprovante verificável indisponível para este documento.");
    }
  }

  async function openRequest(item: ServiceRequest) {
    try {
      const result = await serviceFetch<PortalRequestDetail>("/requests/" + encodeURIComponent(item.id) + "/detail");
      setDetail(result);
      setMessage(null);
    } catch(err) {
      setMessage(err instanceof Error ? err.message : "Não foi possível abrir a solicitação.");
    }
  }

  async function sendReply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail || !reply.trim()) return;
    setReplySending(true);
    try {
      await serviceFetch("/requests/" + encodeURIComponent(detail.request.id) + "/comments", {
        method: "POST", body: JSON.stringify({body:reply.trim(),visibility:"student"}),
      });
      setReply("");
      await openRequest(detail.request);
      setMessage("Resposta enviada à equipe.");
    } catch(err) {
      setMessage(err instanceof Error ? err.message : "Não foi possível responder.");
    } finally { setReplySending(false); }
  }

  async function uploadAttachment() {
    if (!detail || !attachment) return;
    if (attachment.size > 262144) { setMessage("O arquivo deve ter no máximo 256 KiB."); return; }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.set("file", attachment);
      await serviceFetch("/requests/" + encodeURIComponent(detail.request.id) + "/attachments", {
        method: "POST", body: formData,
      });
      setAttachment(null);
      await openRequest(detail.request);
      setMessage("Anexo recebido pela instituição.");
    } catch(err) {
      setMessage(err instanceof Error ? err.message : "Não foi possível enviar o arquivo.");
    } finally { setUploading(false); }
  }

  async function downloadAttachment(id: string, filename: string) {
    if (!detail) return;
    try {
      const response = await fetch("/api/v1/student-portal/services/requests/" +
        encodeURIComponent(detail.request.id) + "/attachments/" + encodeURIComponent(id), {
        cache: "no-store", credentials: "same-origin",
      });
      if (!response.ok) throw new Error("Anexo indisponível.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url; link.download = filename;
      document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch(err) { setMessage(err instanceof Error ? err.message : "Download indisponível."); }
  }

  async function openNotification(n: PortalNotification) {
    try {
      if (!n.read_at) await serviceFetch("/notifications/"+encodeURIComponent(n.id)+"/read",{method:"POST"});
      setNotifications(v=>v.map(item=>item.id===n.id?{...item,read_at:new Date().toISOString()}:item));
      const request = requests.find(r=>r.id===n.request_id);
      if(request) await openRequest(request);
    } catch(err) { setMessage(err instanceof Error ? err.message : "Notificação indisponível."); }
  }

  async function openHistory(item: ServiceRequest) {
    try {
      const result = await serviceFetch<{ events: { status: string; note: string | null; occurred_at: string }[] }>(
        "/requests/" + encodeURIComponent(item.id) + "/history"
      );
      // Staff-only notes are not a public contract. Show status and dates only.
      setHistory({ subject: item.subject, events: result.events.map(({status,occurred_at}) => ({ status, occurred_at })) });
    } catch (err) { setMessage(err instanceof Error ? err.message : "Histórico indisponível."); }
  }

  return (
    <section aria-label="Serviços do Aluno" className="overflow-hidden rounded-xl border border-[#E4E7EC] bg-white">
      <div className="border-b border-[#EAECF0] px-6 py-5">
        <h2 className="text-[17px] font-semibold text-[#101112]">{view === "requests" ? "Solicitações" : view === "documents" ? "Documentos" : "Financeiro"}</h2>
        <p className="mt-1 text-[12px] text-[#505967]">{view === "requests" ? "Abra e acompanhe seus requerimentos junto à instituição." : view === "documents" ? "Consulte documentos disponibilizados pela sua instituição." : "Consulte seus registros e cobranças confirmadas pelas fontes oficiais."}</p>
      </div>
      {!standalone && <div className="flex flex-wrap gap-2 border-b border-[#EAECF0] px-6 py-3" role="tablist" aria-label="Tipos de serviço">
        {choices.map((choice) => (
          <button key={choice.id} type="button" role="tab" aria-selected={view === choice.id}
            className={"rounded-lg px-4 py-2 text-[12px] font-medium " +
              (view === choice.id ? "bg-[#EFF4FF] text-[#2563EB]" : "text-[#667085] hover:bg-[#F9FAFB]")}
            onClick={() => setView(choice.id)}>{choice.label}</button>
        ))}
      </div>}
      <div className="space-y-5 p-4 sm:p-6">
        {loadError && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#FEE7E7] bg-[#FFF7F7] px-4 py-3 text-[12px] text-[#772322]"><span>{loadError}</span><button type="button" className="underline" onClick={() => setReloadIndex(n => n + 1)}>Tentar novamente</button></div>}
        {message && <p role="status" className="rounded-lg bg-[#F9FAFB] p-3 text-[12px] text-[#475467]">{message}</p>}
        {loading && <p className="text-[12px] text-[#667085]">Consultando registros…</p>}
        {!loading && !loadError && view === "requests" && <>
          <div className="flex items-center justify-between gap-3"><p className="text-[12px] text-[#505967]">{requests.length} solicitação(ões) nesta consulta</p><button type="button" aria-expanded={composeOpen} onClick={() => setComposeOpen(v => !v)} className="rounded-lg bg-[#101112] px-3.5 py-2.5 text-[12px] font-semibold text-white hover:bg-[#232529] focus-visible:ring-2 focus-visible:ring-[#266DF0]">{composeOpen ? "Fechar formulário" : "+ Nova solicitação"}</button></div>
          {composeOpen && <form onSubmit={submit} className="grid gap-3 rounded-xl border border-[#EAECF0] p-4">
            <h3 className="text-[13px] font-semibold">Nova solicitação</h3>
            <label className="text-[12px] text-[#475467]">Tipo de pedido
              <select value={category} onChange={(e) => setCategory(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[#D0D5DD] bg-white p-2">
                {categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
            <label className="text-[12px] text-[#475467]">Assunto
              <input required minLength={3} maxLength={180} value={subject} onChange={(e) => setSubject(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[#D0D5DD] p-2" />
            </label>
            <label className="text-[12px] text-[#475467]">Descrição
              <textarea required minLength={5} maxLength={2000} rows={3}
                value={description} onChange={(e) => setDescription(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[#D0D5DD] p-2" />
            </label>
            <button disabled={sending} type="submit" className="rounded-lg bg-[#101828] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-60">
              {sending ? "Enviando…" : "Enviar solicitação"}
            </button>
          </form>}
          {notifications.some(n=>!n.read_at) && <div className="rounded-lg border border-[#D6E4FF] bg-[#F5F8FF] p-3">
            <p className="text-[12px] font-semibold text-[#175CD3]">Novas atualizações das suas solicitações</p>
            {notifications.filter(n=>!n.read_at).slice(0,5).map(n=><button key={n.id} type="button"
              onClick={()=>void openNotification(n)} className="mt-2 block text-left text-[11px] text-[#2563EB] underline">{n.title}</button>)}
          </div>}
          <ul className="divide-y divide-[#EAECF0]">
            {requests.map((item) => <li key={item.id} className="flex items-center justify-between gap-3 py-3 text-[12px]">
              <div><p className="font-semibold text-[#344054]">{item.subject}</p><p className="mt-1 text-[#667085]">{item.due_at ? "Prazo: "+new Date(item.due_at).toLocaleDateString("pt-BR") : "Prazo ainda não informado"}</p><span className={"mt-1 inline-flex rounded-md border px-2 py-0.5 text-[10px] " + serviceStatusTone(item.status)}>{serviceStatusLabel(item.status)}</span></div>
              <div className="flex shrink-0 gap-3">
                <button type="button" onClick={() => void openRequest(item)} className="text-[#2563EB]">Acompanhar</button>
                <button type="button" onClick={() => void openHistory(item)} className="text-[#667085]">Histórico</button>
              </div>
            </li>)}
          </ul>
          {detail && <section aria-label="Acompanhamento da solicitação" className="space-y-4 rounded-xl border border-[#DDE5F0] bg-[#FCFDFF] p-4">
            <div className="flex justify-end"><button type="button" className="text-[12px] font-semibold text-[#505967] hover:text-[#101112]" onClick={() => setDetail(null)}>Fechar detalhes</button></div>
            <div><h3 className="text-[13px] font-semibold">{detail.request.subject}</h3>
              <p className="mt-1 text-[11px] text-[#667085]">Acompanhe as respostas e os arquivos liberados pela instituição.</p>
            </div>
            {detail.comments.length > 0 && <div className="space-y-2">
              {detail.comments.map(c=><div key={c.id} className="rounded-lg border border-[#EAECF0] bg-white p-3">
                <p className="text-[11px] font-semibold text-[#475467]">{c.actor_type==="student"?"Você":"Equipe institucional"} · {new Date(c.created_at).toLocaleDateString("pt-BR")}</p>
                <p className="mt-1 whitespace-pre-wrap break-words text-[12px] text-[#475467]">{c.body}</p>
              </div>)}
            </div>}
            {detail.attachments.length > 0 && <div className="space-y-2">
              <p className="text-[11px] font-semibold">Anexos disponíveis</p>
              {detail.attachments.map(a=><button type="button" key={a.id}
                onClick={()=>void downloadAttachment(a.id,a.filename)} className="block text-left text-[12px] text-[#2563EB] underline">{a.filename} · {(a.byte_count/1024).toFixed(0)} KB</button>)}
            </div>}
            {!["completed","rejected","cancelled"].includes(detail.request.status) && <>
              <form onSubmit={sendReply} className="space-y-2">
                <label htmlFor="portal-service-reply" className="block text-[11px] font-semibold">Responder à instituição</label>
                <textarea id="portal-service-reply" rows={3} minLength={1} maxLength={2000} required
                  value={reply} onChange={e=>setReply(e.target.value)}
                  className="w-full rounded-lg border border-[#D0D5DD] p-3 text-[12px]" placeholder="Escreva sua mensagem…" />
                <button type="submit" disabled={replySending || !reply.trim()} className="rounded-lg bg-[#202124] px-4 py-2 text-[12px] text-white disabled:opacity-50">
                  {replySending?"Enviando…":"Enviar resposta"}
                </button>
              </form>
              <div className="space-y-2 border-t border-[#EAECF0] pt-3">
                <p className="text-[11px] font-semibold">Enviar documento ou imagem</p>
                <input type="file" accept=".pdf,.jpg,.jpeg,.png" aria-label="Selecionar anexo da solicitação"
                  onChange={e=>setAttachment(e.target.files?.[0]||null)} className="block text-[11px]" />
                <p className="text-[10px] text-[#85858B]">PDF, PNG ou JPG; até 256 KiB. A instituição poderá consultar o arquivo.</p>
                <button type="button" disabled={!attachment || uploading}
                  onClick={()=>void uploadAttachment()} className="rounded-lg border border-[#D0D5DD] px-4 py-2 text-[12px] disabled:opacity-50">
                  {uploading?"Enviando…":"Anexar arquivo"}
                </button>
              </div>
            </>}
          </section>}
          {history && <section aria-label="Linha do tempo da solicitação" className="rounded-xl border border-[#E6E7EA] p-4">
            <div className="flex items-center justify-between gap-3"><h3 className="text-[13px] font-semibold">Histórico · {history.subject}</h3><button type="button" onClick={() => setHistory(null)} className="text-[12px] text-[#505967] underline">Fechar</button></div>
            {history.events.length === 0 ? <p className="mt-3 text-[12px] text-[#75777C]">Nenhuma movimentação disponível.</p>
              : <ol className="mt-4 space-y-0 border-l border-[#E6E7EA] pl-4">
                {history.events.map((item, index) => <li key={item.occurred_at + "-" + index} className="relative pb-5 last:pb-0">
                  <span aria-hidden="true" className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-white bg-[#266DF0]" />
                  <p className="text-[12px] font-medium text-[#101112]">{serviceStatusLabel(item.status)}</p>
                  <time dateTime={item.occurred_at} className="mt-0.5 block text-[11px] text-[#75777C]">{new Date(item.occurred_at).toLocaleString("pt-BR")}</time>
                </li>)}
              </ol>}
          </section>}
          {requests.length === 0 && <p className="text-[12px] text-[#667085]">Nenhuma solicitação registrada.</p>}
        </>}
        {!loading && !loadError && view === "documents" && <>
          {documents.length === 0 && <p className="text-[12px] text-[#667085]">Nenhum documento liberado.</p>}
          <ul className="divide-y divide-[#EAECF0]">
            {documents.map((item) => <li key={item.id} className="flex items-center justify-between gap-3 py-3 text-[12px]">
              <span>{item.title}</span>
              <div className="flex flex-wrap gap-3">
                <button type="button" className="text-[#2563EB]" onClick={() => openDocument(item)}>Visualizar</button>
                <button type="button" className="text-[#2563EB]" onClick={() => verifyDocument(item)}>Verificar</button>
              </div>
            </li>)}
          </ul>
          {documentProof !== null && <div className="rounded-lg border border-[#EAECF0] bg-[#F9FAFB] p-4">
            <p className="text-[12px] font-semibold text-[#344054]">
              {documentProofValid ? "Integridade confirmada pela MIRA" : "Integridade não confirmada"}
            </p>
            <p className="mt-2 break-all font-mono text-[11px] text-[#667085]">{documentProof}</p>
            <p className="mt-2 text-[11px] text-[#98A2B3]">
              Código de verificação de conteúdo. Não substitui assinatura eletrônica qualificada.
            </p>
          </div>}
          {documentText !== null && <div className="rounded-lg border border-[#EAECF0] p-4">
            <h3 className="mb-3 text-[13px] font-semibold">{documentTitle}</h3>
            <p className="whitespace-pre-wrap text-[12px] leading-6 text-[#475467]">{documentText}</p>
            <p className="mt-3 text-[11px] text-[#98A2B3]">Pré-visualização textual. Documento oficial assinado ainda não disponível.</p>
          </div>}
        </>}
        {!loading && !loadError && view === "financial" && <>
          <p className="text-[12px] text-[#667085]">Dados importados são informativos. Cobranças oficiais da Asaas aparecem separadamente, somente após emissão autorizada.</p>
          <ul className="divide-y divide-[#EAECF0]">
            {financial.map((item) => <li key={item.id} className="flex justify-between gap-3 py-3 text-[12px]">
              <div><p className="font-medium">{item.label}</p><p className="text-[#667085]">{item.status}</p></div>
              <strong>{brazilMoney(item)}</strong>
            </li>)}
          </ul>
          {financial.length === 0 && <p className="text-[12px] text-[#667085]">Nenhuma informação financeira disponível.</p>}
          {asaasCharges.length > 0 && <div className="mt-5 border-t border-[#EAECF0] pt-4">
            <h3 className="text-[13px] font-semibold text-[#344054]">Cobranças oficiais Asaas</h3>
            <p className="mt-1 text-[11px] text-[#667085]">Pagamento recebido e repasse para a instituição são confirmações distintas.</p>
            <ul className="mt-2 divide-y divide-[#EAECF0]">
              {asaasCharges.map((charge) => <li key={charge.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-[12px] font-medium text-[#344054]">
                    {new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(Number(charge.amount))} · {charge.method === "pix" ? "Pix" : "Boleto"}
                  </p>
                  <p className="mt-1 text-[11px] text-[#667085]">
                    {charge.split_settled_verified ? "Repasse à instituição confirmado" :
                      charge.payment_received_verified ? "Pagamento recebido; repasse pendente" :
                      "Aguardando pagamento"}
                  </p>
                  {charge.environment === "sandbox" && <p className="text-[11px] text-[#B54708]">Ambiente de teste</p>}
                </div>
                {!charge.payment_received_verified && <button className="text-[12px] font-semibold text-[#2563EB]"
                  onClick={() => void showPayment(charge)}>Consultar {charge.method === "pix" ? "Pix" : "boleto"}</button>}
              </li>)}
            </ul>
            {paymentInstructions && <div className="rounded-lg border border-[#EAECF0] bg-[#F9FAFB] p-3">
              <p className="text-[12px] font-medium text-[#344054]">{paymentInstructions.method === "pix" ? "Pix copia e cola" : "Linha digitável"}</p>
              <p className="mt-2 break-all font-mono text-[11px] text-[#667085]">
                {paymentInstructions.copy_and_paste || paymentInstructions.identification_field || "Indisponível"}
              </p>
              {paymentInstructions.copy_and_paste && <button className="mt-2 text-[12px] font-semibold text-[#2563EB]"
                onClick={() => void navigator.clipboard?.writeText(paymentInstructions.copy_and_paste || "")}>Copiar código Pix</button>}
            </div>}
          </div>}
        </>}
      </div>
    </section>
  );
}
