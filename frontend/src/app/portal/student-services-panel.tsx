"use client";

import { useEffect, useState, type FormEvent } from "react";

type ServiceRequest = {
  id: string; category: string; subject: string; description: string;
  status: string; created_at: string;
};
type Document = { id: string; title: string; kind: string; published_at: string | null };
type Financial = { id: string; label: string; amount: string; currency: string; status: string; observed_at: string };
type View = "requests" | "documents" | "financial";

async function serviceFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api/v1/student-portal/services" + path, {
    ...init, credentials: "same-origin", cache: "no-store",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
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
function brazilMoney(raw: Financial) {
  const n = Number(raw.amount);
  return raw.currency === "BRL" && Number.isFinite(n)
    ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(n)
    : "Valor não disponível";
}

export function StudentServicesPanel() {
  const [view, setView] = useState<View>("requests");
  const [requests, setRequests] = useState<ServiceRequest[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [financial, setFinancial] = useState<Financial[]>([]);
  const [category, setCategory] = useState("declaration");
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [documentText, setDocumentText] = useState<string | null>(null);
  const [documentTitle, setDocumentTitle] = useState("");
  const [history, setHistory] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true); setMessage(null); setDocumentText(null); setHistory(null);
    const endpoint = view === "requests" ? "/requests" : view === "documents" ? "/documents" : "/financial";
    serviceFetch<{ items: ServiceRequest[] | Document[] | Financial[] }>(endpoint)
      .then((data) => {
        if (!active) return;
        if (view === "requests") setRequests(data.items as ServiceRequest[]);
        if (view === "documents") setDocuments(data.items as Document[]);
        if (view === "financial") setFinancial(data.items as Financial[]);
      })
      .catch((err: Error) => { if (active) setMessage(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [view]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSending(true); setMessage(null);
    try {
      const created = await serviceFetch<ServiceRequest>("/requests", {
        method: "POST", body: JSON.stringify({ category, subject, description }),
      });
      setRequests((items) => [created, ...items]);
      setSubject(""); setDescription(""); setMessage("Solicitação registrada com sucesso.");
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
  async function openHistory(item: ServiceRequest) {
    try {
      const result = await serviceFetch<{ events: { status: string; note: string | null; occurred_at: string }[] }>(
        "/requests/" + encodeURIComponent(item.id) + "/history"
      );
      setHistory(item.subject + "\n" + result.events.map((event) =>
        event.status + (event.note ? " — " + event.note : "") + " · " +
        new Date(event.occurred_at).toLocaleDateString("pt-BR")).join("\n"));
    } catch (err) { setMessage(err instanceof Error ? err.message : "Histórico indisponível."); }
  }

  return (
    <section aria-label="Serviços do Aluno" className="overflow-hidden rounded-xl border border-[#E4E7EC] bg-white">
      <div className="border-b border-[#EAECF0] px-6 py-5">
        <h2 className="text-[17px] font-semibold text-[#101828]">Serviços do aluno</h2>
        <p className="mt-1 text-[12px] text-[#667085]">Acompanhe seus pedidos, consulte documentos liberados e informações financeiras.</p>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-[#EAECF0] px-6 py-3" role="tablist" aria-label="Tipos de serviço">
        {choices.map((choice) => (
          <button key={choice.id} type="button" role="tab" aria-selected={view === choice.id}
            className={"rounded-lg px-4 py-2 text-[12px] font-medium " +
              (view === choice.id ? "bg-[#EFF4FF] text-[#2563EB]" : "text-[#667085] hover:bg-[#F9FAFB]")}
            onClick={() => setView(choice.id)}>{choice.label}</button>
        ))}
      </div>
      <div className="space-y-5 p-6">
        {message && <p role="status" className="rounded-lg bg-[#F9FAFB] p-3 text-[12px] text-[#475467]">{message}</p>}
        {loading && <p className="text-[12px] text-[#667085]">Consultando registros…</p>}
        {!loading && !message?.includes("homologação") && view === "requests" && <>
          <form onSubmit={submit} className="grid gap-3 rounded-xl border border-[#EAECF0] p-4">
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
          </form>
          <ul className="divide-y divide-[#EAECF0]">
            {requests.map((item) => <li key={item.id} className="flex items-center justify-between gap-3 py-3 text-[12px]">
              <div><p className="font-semibold text-[#344054]">{item.subject}</p><p className="text-[#667085]">{item.status}</p></div>
              <button type="button" onClick={() => openHistory(item)} className="text-[#2563EB]">Histórico</button>
            </li>)}
          </ul>
          {history && <pre className="whitespace-pre-wrap rounded-lg bg-[#F9FAFB] p-3 text-[12px] text-[#475467]">{history}</pre>}
          {requests.length === 0 && <p className="text-[12px] text-[#667085]">Nenhuma solicitação registrada.</p>}
        </>}
        {!loading && view === "documents" && <>
          {documents.length === 0 && <p className="text-[12px] text-[#667085]">Nenhum documento liberado.</p>}
          <ul className="divide-y divide-[#EAECF0]">
            {documents.map((item) => <li key={item.id} className="flex items-center justify-between gap-3 py-3 text-[12px]">
              <span>{item.title}</span><button type="button" className="text-[#2563EB]" onClick={() => openDocument(item)}>Visualizar</button>
            </li>)}
          </ul>
          {documentText !== null && <div className="rounded-lg border border-[#EAECF0] p-4">
            <h3 className="mb-3 text-[13px] font-semibold">{documentTitle}</h3>
            <p className="whitespace-pre-wrap text-[12px] leading-6 text-[#475467]">{documentText}</p>
            <p className="mt-3 text-[11px] text-[#98A2B3]">Pré-visualização textual. Documento oficial assinado ainda não disponível.</p>
          </div>}
        </>}
        {!loading && view === "financial" && <>
          <p className="text-[12px] text-[#667085]">Dados informativos sincronizados de fontes homologadas. Nenhum pagamento é iniciado aqui.</p>
          <ul className="divide-y divide-[#EAECF0]">
            {financial.map((item) => <li key={item.id} className="flex justify-between gap-3 py-3 text-[12px]">
              <div><p className="font-medium">{item.label}</p><p className="text-[#667085]">{item.status}</p></div>
              <strong>{brazilMoney(item)}</strong>
            </li>)}
          </ul>
          {financial.length === 0 && <p className="text-[12px] text-[#667085]">Nenhuma informação financeira disponível.</p>}
        </>}
      </div>
    </section>
  );
}
