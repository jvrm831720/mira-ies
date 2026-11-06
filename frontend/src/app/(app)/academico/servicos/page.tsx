"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Bell, CheckCircle2, Clock3, FileText, Filter,
  Loader2, MessageCircle, Plus, RefreshCw, ShieldCheck, UploadCloud, Users,
} from "@/components/ui/icons";
import { getAccessToken } from "@/lib/auth";
import { api } from "@/lib/api";

const BASE = "/api/v1/native-academic/services";
type Status = "submitted" | "in_review" | "approved" | "rejected" | "completed" | "cancelled";
type RequestItem = {
  id: string; student_id: string; category: string; subject: string;
  description: string; status: Status; priority: "low" | "normal" | "high" | "urgent";
  created_at: string; updated_at: string; due_at: string | null;
  assigned_membership_id: string | null; generated_document_id: string | null;
  completed_at: string | null;
};
type Comment = { id: string; actor_type: "student" | "staff"; body: string; visibility: "student" | "staff"; created_at: string };
type Evidence = { id: string; filename: string; byte_count: number; visibility: "student" | "staff"; created_at: string };
type Timeline = { id: string; status: string; note: string | null; occurred_at: string; actor_type: string };
type Detail = {
  request: RequestItem; student: { id: string; name: string; registration: string; course?: string | null };
  comments: Comment[]; attachments: Evidence[]; events: Timeline[];
};
type Staff = { membership_id: string; display_name: string };
type Template = { id: string; name: string; category: string; document_kind: string; body_template: string; is_active: boolean };
type Notification = { id: string; request_id: string; title: string; event_key: string; read_at: string | null; created_at: string };
type Tab = "queue" | "templates" | "notifications";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  if (!token) throw new Error("Faça login na conta institucional.");
  const response = await fetch(BASE + path, {
    ...init, cache: "no-store",
    headers: {
      Authorization: "Bearer " + token,
      ...(typeof init.body === "string" ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    const json = await response.json().catch(() => ({}));
    throw new Error(
      typeof json.detail === "string" ? json.detail :
      response.status === 503 ? "Serviços acadêmicos ainda não estão habilitados neste ambiente." :
      response.status === 403 ? "Permissão insuficiente para esta ação." :
      "Não foi possível concluir a operação.",
    );
  }
  return response.json() as Promise<T>;
}
async function download(requestId: string, file: Evidence) {
  const token = getAccessToken();
  if (!token) throw new Error("Sua sessão expirou.");
  const r = await fetch(BASE + "/requests/" + encodeURIComponent(requestId) + "/attachments/" + encodeURIComponent(file.id), {
    headers: { Authorization: "Bearer " + token },
    cache: "no-store",
  });
  if (!r.ok) throw new Error("Não foi possível baixar o anexo.");
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function prettyDate(value: string | null) {
  if (!value) return "Sem prazo";
  return new Date(value).toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
const LABELS: Record<Status, string> = {
  submitted: "Recebida", in_review: "Em análise", approved: "Aprovada",
  rejected: "Rejeitada", completed: "Concluída", cancelled: "Cancelada",
};
const CATEGORY: Record<string, string> = {
  declaration: "Declaração", transcript: "Histórico", enrollment: "Matrícula",
  academic_review: "Revisão acadêmica", other: "Outro",
};
const PRIORITY: Record<RequestItem["priority"], string> = {
  low: "Baixa", normal: "Normal", high: "Alta", urgent: "Urgente",
};
const STATE_NEXT: Record<Status, Status[]> = {
  submitted: ["in_review", "cancelled"], in_review: ["approved", "rejected", "cancelled"],
  approved: ["completed", "cancelled"], rejected: [], completed: [], cancelled: [],
};
const inputStyle = "h-9 w-full rounded-lg border border-[#D9DEE7] bg-white px-3 text-[12px] text-[#344054] outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/10";
const smallButton = "inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-[#D9DEE7] bg-white px-3 text-[12px] font-medium text-[#344054] transition hover:bg-[#F7F9FC] disabled:cursor-not-allowed disabled:opacity-50";
const primaryButton = "inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-[#202124] px-3.5 text-[12px] font-medium text-white transition hover:bg-[#34353A] disabled:cursor-not-allowed disabled:opacity-50";

export default function AcademicServiceDeskPage() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false });
  const canView = me.data?.operation_profile === "institution" &&
    (me.data.permissions ? me.data.permissions.includes("students.sensitive.view")
      : ["admin", "coordinator"].includes(me.data.role || ""));
  const canEdit = !!canView && (me.data?.permissions
    ? me.data.permissions.includes("students.edit")
    : ["admin", "coordinator", "operator"].includes(me.data?.role || ""));
  const canApprove = !!canView && (me.data?.permissions
    ? me.data.permissions.includes("critical.manage") : me.data?.role === "admin");
  const canTemplates = !!canView && (me.data?.permissions
    ? me.data.permissions.includes("settings.manage") : me.data?.role === "admin");
  const [tab, setTab] = useState<Tab>("queue");
  const [filter, setFilter] = useState<Status | "all">("all");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [assignee, setAssignee] = useState("");
  const [priority, setPriority] = useState<RequestItem["priority"]>("normal");
  const [dueAt, setDueAt] = useState("");
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const [privateNote, setPrivateNote] = useState(false);
  const [uploadVisibility, setUploadVisibility] = useState<"student" | "staff">("staff");
  const [templateId, setTemplateId] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [templateCategory, setTemplateCategory] = useState("declaration");
  const [templateKind, setTemplateKind] = useState("declaration");
  const [templateBody, setTemplateBody] = useState("Declaramos, para os devidos fins, que {{student_name}}, matrícula {{registration}}, está vinculado(a) à {{organization_name}}.\n\nData: {{today}}.");
  const [success, setSuccess] = useState("");
  const [failure, setFailure] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const queue = useQuery({
    queryKey: ["academic-service-queue", filter, priorityFilter, offset],
    queryFn: () => request<{ items: RequestItem[]; total: number; has_more: boolean; limit: number }>(
      "/queue?" + new URLSearchParams({
        limit: "50", offset: String(offset),
        ...(filter !== "all" ? { status: filter } : {}),
        ...(priorityFilter !== "all" ? { priority: priorityFilter } : {}),
      }).toString(),
    ),
    enabled: !!canView, retry: false,
  });
  const activeId = selectedId && queue.data?.items.some((x) => x.id === selectedId)
    ? selectedId : queue.data?.items[0]?.id || null;
  const detail = useQuery({
    queryKey: ["academic-service-detail", activeId],
    queryFn: () => request<Detail>("/requests/" + activeId + "/detail"),
    enabled: !!canView && !!activeId && tab === "queue", retry: false,
  });
  const members = useQuery({
    queryKey: ["academic-service-staff"], queryFn: () => request<{ items: Staff[] }>("/staff"),
    enabled: !!canView, retry: false,
  });
  const templates = useQuery({
    queryKey: ["academic-service-templates"], queryFn: () => request<{ items: Template[]; variables: string[] }>("/templates"),
    enabled: !!canView && (tab === "templates" || tab === "queue"), retry: false,
  });
  const notifications = useQuery({
    queryKey: ["academic-service-notifications"], queryFn: () => request<{ items: Notification[] }>("/notifications"),
    enabled: !!canView && tab === "notifications", retry: false,
  });

  useEffect(() => {
    if (!detail.data) return;
    const row = detail.data.request;
    setAssignee(row.assigned_membership_id || "");
    setPriority(row.priority);
    setDueAt(row.due_at ? new Date(row.due_at).toISOString().slice(0, 16) : "");
    setTemplateId("");
    setMessage("");
    setNote("");
    setPrivateNote(false);
    setFile(null);
    setFailure("");
  }, [detail.data?.request.id, detail.data?.request.updated_at, detail.data?.request.assigned_membership_id, detail.data?.request.due_at, detail.data?.request.priority]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["academic-service-queue"] });
    void qc.invalidateQueries({ queryKey: ["academic-service-detail"] });
    void qc.invalidateQueries({ queryKey: ["academic-service-notifications"] });
    void qc.invalidateQueries({ queryKey: ["academic-service-templates"] });
  }

  const action = useMutation({
    mutationFn: async ({ path, body, method = "POST" }: { path: string; body?: unknown; method?: string }) =>
      request<unknown>(path, { method, ...(body ? { body: JSON.stringify(body) } : {}) }),
    onSuccess: () => { setFailure(""); setSuccess("Alteração salva com sucesso."); refresh(); },
    onError: (err: Error) => { setSuccess(""); setFailure(err.message); },
  });
  const upload = useMutation({
    mutationFn: async () => {
      if (!activeId || !file) throw new Error("Escolha um arquivo.");
      if (file.size > 262144) throw new Error("O limite é de 256 KiB por arquivo.");
      const body = new FormData();
      body.set("file", file);
      body.set("visibility", uploadVisibility);
      await request("/requests/" + activeId + "/attachments", { method: "POST", body });
    },
    onSuccess: () => { setFile(null); setFailure(""); setSuccess("Anexo adicionado."); refresh(); },
    onError: (err: Error) => setFailure(err.message),
  });

  function changeFilter(value: Status | "all") { setFilter(value); setOffset(0); setSelectedId(null); }
  function changePriority(value: string) { setPriorityFilter(value); setOffset(0); setSelectedId(null); }
  const row = detail.data?.request;
  const availableTemplates = useMemo(() => (templates.data?.items || []).filter(
    t => t.is_active && t.category === row?.category,
  ), [row?.category, templates.data?.items]);
  const notificationsUnread = notifications.data?.items.filter(n => !n.read_at).length || 0;

  function assign(event: FormEvent) {
    event.preventDefault();
    if (!activeId || !assignee) { setFailure("Selecione um responsável."); return; }
    const date = dueAt ? new Date(dueAt).toISOString() : null;
    action.mutate({ path: "/requests/" + activeId + "/assign", body: {
      membership_id: assignee, priority, due_at: date,
    } });
  }

  function createTemplate(event: FormEvent) {
    event.preventDefault();
    if (!canTemplates) return;
    action.mutate({ path: "/templates", body: {
      name: templateName, category: templateCategory, document_kind: templateKind,
      body_template: templateBody, is_active: true,
    } });
  }

  if (me.isLoading) return <main className="px-8 py-12 text-sm text-[#667085]">Verificando permissões…</main>;
  if (!canView) return <main className="px-8 py-12 text-sm text-[#667085]">
    A Central de Serviços Acadêmicos está disponível apenas para equipes institucionais autorizadas.
  </main>;

  return <main className="min-h-screen bg-[#FCFCFD] px-4 py-7 text-[#202124] sm:px-8 xl:px-10">
    <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.11em] text-[#667085]">Acadêmico / Atendimento</p>
        <h1 className="mt-2 text-[26px] font-semibold tracking-[-0.035em]">Central de Serviços Acadêmicos</h1>
        <p className="mt-1.5 text-[13px] text-[#667085]">Receba, organize e resolva as solicitações do Portal do Aluno.</p>
      </div>
      <button type="button" className={smallButton} onClick={refresh}>
        <RefreshCw className="h-4 w-4" /> Atualizar
      </button>
    </header>
    <div className="mb-5 flex flex-wrap gap-1 rounded-xl border border-[#EAECF0] bg-white p-1.5">
      {([
        ["queue", "Solicitações", FileText],
        ["templates", "Modelos de documento", ShieldCheck],
        ["notifications", "Notificações internas", Bell],
      ] as const).map(([id, label, Icon]) => (
        <button key={id} type="button" onClick={() => setTab(id)} aria-current={tab === id ? "page" : undefined}
          className={"flex items-center gap-2 rounded-lg px-3 py-2 text-[12px] font-medium transition " +
            (tab === id ? "bg-[#F1F5FF] text-[#2563EB]" : "text-[#667085] hover:bg-[#F9FAFB]")}>
          <Icon className="h-4 w-4" /> {label}
        </button>
      ))}
    </div>
    {success && <p role="status" className="mb-4 rounded-lg border border-[#D6EADF] bg-[#F3FCF7] px-4 py-3 text-[12px] text-[#167047]">{success}</p>}
    {failure && <p role="alert" className="mb-4 rounded-lg border border-[#F5D8D8] bg-[#FFF7F7] px-4 py-3 text-[12px] text-[#B42318]">{failure}</p>}

    {tab === "queue" && <>
      <div className="mb-4 grid gap-3 md:grid-cols-4">
        {([
          ["Recebidas", "submitted"], ["Em análise", "in_review"],
          ["Aprovadas", "approved"], ["Concluídas", "completed"],
        ] as const).map(([label, state]) => (
          <button key={state} type="button" onClick={() => changeFilter(state)}
            className={"rounded-xl border bg-white px-4 py-3 text-left " +
              (filter === state ? "border-[#2563EB] shadow-sm" : "border-[#EAECF0] hover:border-[#C4D3EF]")}>
            <p className="text-[11px] text-[#667085]">{label}</p>
            <p className="mt-1 text-[16px] font-semibold">{queue.data?.items.filter(x => x.status === state).length || 0}<span className="ml-1 text-[10px] font-normal text-[#98A2B3]">na página atual</span></p>
          </button>
        ))}
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-[#98A2B3]" />
        <select aria-label="Filtrar por status" value={filter} onChange={e => changeFilter(e.target.value as Status | "all")} className={inputStyle + " max-w-[184px]"}>
          <option value="all">Todos os status</option>
          {Object.entries(LABELS).map(([key, text]) => <option key={key} value={key}>{text}</option>)}
        </select>
        <select aria-label="Filtrar por prioridade" value={priorityFilter} onChange={e => changePriority(e.target.value)} className={inputStyle + " max-w-[172px]"}>
          <option value="all">Todas as prioridades</option>
          {Object.entries(PRIORITY).map(([key, text]) => <option key={key} value={key}>{text}</option>)}
        </select>
        <span className="ml-auto text-[11px] text-[#85858B]">{queue.data?.total || 0} solicitações no filtro</span>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(290px,0.83fr)_minmax(420px,1.17fr)]">
        <section className="overflow-hidden rounded-xl border border-[#E6E8EB] bg-white" aria-label="Fila de solicitações">
          <div className="border-b border-[#EEF0F2] px-4 py-3.5"><h2 className="text-[13px] font-semibold">Fila de atendimento</h2></div>
          {queue.isLoading && <p className="px-4 py-12 text-center text-[12px] text-[#85858B]">Carregando solicitações…</p>}
          {queue.isError && <p role="alert" className="px-4 py-5 text-[12px] text-[#B42318]">{(queue.error as Error).message}</p>}
          {!queue.isLoading && !queue.data?.items.length && <div className="px-6 py-14 text-center">
            <CheckCircle2 className="mx-auto h-7 w-7 text-[#D0D5DD]" />
            <p className="mt-3 text-[13px] font-medium">Nenhuma solicitação neste filtro</p>
            <p className="mt-1 text-[11px] text-[#98A2B3]">As solicitações enviadas pelo Portal do Aluno aparecerão aqui.</p>
          </div>}
          <div className="max-h-[72vh] overflow-y-auto divide-y divide-[#F0F1F2]">
            {queue.data?.items.map(item => {
              const overdue = item.due_at && new Date(item.due_at).getTime() < Date.now() && !["completed","cancelled","rejected"].includes(item.status);
              return <button type="button" key={item.id} onClick={() => { setSelectedId(item.id); setFailure(""); setSuccess(""); }}
                className={"block w-full px-4 py-3.5 text-left transition " + (activeId === item.id ? "bg-[#F5F8FF]" : "hover:bg-[#FAFBFC]")}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-medium text-[#667085]">{CATEGORY[item.category] || item.category}</span>
                  <span className={"rounded-md px-2 py-1 text-[10px] font-semibold " +
                    (item.status === "completed" ? "bg-[#ECFDF3] text-[#027A48]" :
                     item.status === "rejected" ? "bg-[#FEF3F2] text-[#B42318]" : "bg-[#EFF4FF] text-[#175CD3]")}>{LABELS[item.status]}</span>
                </div>
                <p className="mt-2 line-clamp-2 text-[12px] font-semibold text-[#202124]">{item.subject}</p>
                <div className="mt-2 flex items-center justify-between gap-2 text-[10px] text-[#85858B]">
                  <span className={overdue ? "font-semibold text-[#D92D20]" : ""}><Clock3 className="mr-1 inline h-3 w-3" /> {overdue ? "Vencida · " : ""}{prettyDate(item.due_at)}</span>
                  <span>{PRIORITY[item.priority]}</span>
                </div>
              </button>;
            })}
          </div>
          {queue.data && <div className="flex items-center justify-between border-t border-[#EFF0F2] px-4 py-3">
            <span className="text-[11px] text-[#98A2B3]">{offset + 1}–{offset + queue.data.items.length} de {queue.data.total}</span>
            <div className="flex gap-2">
              <button type="button" disabled={offset === 0} className={smallButton} onClick={() => {setOffset(v=>Math.max(v-50,0));setSelectedId(null);}}>Anterior</button>
              <button type="button" disabled={!queue.data.has_more} className={smallButton} onClick={() => {setOffset(v=>v+50);setSelectedId(null);}}>Próxima</button>
            </div>
          </div>}
        </section>

        <section className="min-w-0 overflow-hidden rounded-xl border border-[#E6E8EB] bg-white" aria-label="Detalhe da solicitação">
          {!activeId && <div className="px-6 py-16 text-center text-[12px] text-[#98A2B3]">Selecione uma solicitação para começar.</div>}
          {detail.isLoading && activeId && <div className="px-6 py-16 text-center text-[12px] text-[#667085]">Abrindo solicitação…</div>}
          {detail.isError && <p role="alert" className="p-5 text-[12px] text-[#B42318]">{(detail.error as Error).message}</p>}
          {row && <>
            <div className="border-b border-[#EAECF0] p-5">
              <p className="text-[10px] uppercase tracking-[0.1em] text-[#85858B]">{CATEGORY[row.category] || row.category} · {LABELS[row.status]}</p>
              <h2 className="mt-1 text-[17px] font-semibold tracking-[-0.02em]">{row.subject}</h2>
              <p className="mt-2 text-[12px] leading-5 text-[#667085]">{row.description}</p>
              {detail.data?.student && <div className="mt-4 flex flex-wrap items-center gap-3 text-[11px] text-[#475467]">
                <span className="flex items-center gap-1.5"><Users className="h-3.5 w-3.5" /> {detail.data.student.name}</span>
                <span>Matrícula {detail.data.student.registration}</span>
                {detail.data.student.course && <span>{detail.data.student.course}</span>}
              </div>}
            </div>
            <div className="max-h-[72vh] space-y-6 overflow-y-auto p-5">
              <section>
                <h3 className="mb-3 text-[12px] font-semibold">Responsável e prazo</h3>
                <form onSubmit={assign} className="grid gap-3 sm:grid-cols-2">
                  <label className="text-[11px] text-[#667085]">Responsável
                    <select disabled={!canEdit || action.isPending} required value={assignee} onChange={e=>setAssignee(e.target.value)} className={inputStyle + " mt-1"}><option value="">Atribuir membro</option>
                      {members.data?.items.map(user=><option key={user.membership_id} value={user.membership_id}>{user.display_name}</option>)}
                    </select>
                  </label>
                  <label className="text-[11px] text-[#667085]">Prioridade
                    <select disabled={!canEdit || action.isPending} value={priority} onChange={e=>setPriority(e.target.value as RequestItem["priority"])} className={inputStyle + " mt-1"}>
                      {Object.entries(PRIORITY).map(([key,label])=><option key={key} value={key}>{label}</option>)}
                    </select>
                  </label>
                  <label className="text-[11px] text-[#667085]">Prazo (horário local)
                    <input disabled={!canEdit || action.isPending} type="datetime-local" value={dueAt} onChange={e=>setDueAt(e.target.value)} className={inputStyle + " mt-1"} />
                  </label>
                  {canEdit && <button type="submit" disabled={!assignee || action.isPending || ["completed","rejected","cancelled"].includes(row.status)} className={primaryButton + " self-end"}>Salvar atribuição</button>}
                </form>
              </section>
              <section>
                <h3 className="mb-2 text-[12px] font-semibold">Aprovação e resolução</h3>
                {!canApprove ? <p className="text-[11px] text-[#85858B]">Aprovações e encerramentos exigem permissão institucional específica.</p> :
                  <div className="space-y-3">
                    <label className="block text-[11px] text-[#667085]">Justificativa / observação da decisão
                      <textarea value={note} onChange={e=>setNote(e.target.value)} rows={2} maxLength={500} className={inputStyle + " mt-1 h-auto py-2"} placeholder="Registre o motivo da decisão" />
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {STATE_NEXT[row.status].map(state => <button type="button" key={state}
                        disabled={action.isPending || note.trim().length < 3}
                        onClick={() => action.mutate({ path: "/requests/" + row.id + "/review", body: {status:state,note} })}
                        className={state === "completed" ? primaryButton : smallButton}>
                        {LABELS[state]} <ArrowRight className="h-3 w-3" />
                      </button>)}
                      {!STATE_NEXT[row.status].length && <span className="text-[11px] text-[#85858B]">Esta solicitação já foi encerrada.</span>}
                    </div>
                  </div>}
              </section>
              <section>
                <h3 className="mb-3 text-[12px] font-semibold">Conversa e observações</h3>
                {detail.data?.comments.length ? <div className="space-y-2">
                  {detail.data.comments.map(comment => <article key={comment.id} className={"rounded-lg border p-3 " +
                    (comment.visibility === "staff" ? "border-[#F2E5C9] bg-[#FFFCF5]" : "border-[#E7E9ED] bg-[#FAFBFC]")}>
                    <div className="flex flex-wrap justify-between gap-2">
                      <p className="text-[11px] font-semibold text-[#344054]">{comment.actor_type === "student" ? "Aluno" : "Equipe institucional"}</p>
                      <span className="text-[10px] text-[#85858B]">{comment.visibility === "staff" ? "Interno · " : ""}{prettyDate(comment.created_at)}</span>
                    </div>
                    <p className="mt-1.5 whitespace-pre-wrap break-words text-[12px] text-[#475467]">{comment.body}</p>
                  </article>)}
                </div> : <p className="text-[11px] text-[#98A2B3]">Nenhum comentário até agora.</p>}
                {canEdit && !["completed","rejected","cancelled"].includes(row.status) && <form className="mt-3 space-y-2" onSubmit={event=>{
                  event.preventDefault();
                  if (message.trim()) action.mutate({path:"/requests/"+row.id+"/comments",body:{body:message,visibility:privateNote?"staff":"student"}}, {onSuccess:()=>setMessage("")});
                }}>
                  <textarea required minLength={1} maxLength={2000} value={message} onChange={e=>setMessage(e.target.value)} rows={3} placeholder="Escreva uma atualização…" className={inputStyle + " h-auto py-2"} />
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label className="flex items-center gap-2 text-[11px] text-[#667085]">
                      <input type="checkbox" checked={privateNote} onChange={e=>setPrivateNote(e.target.checked)} /> Nota interna — não visível ao aluno
                    </label>
                    <button type="submit" className={primaryButton} disabled={action.isPending || !message.trim()}><MessageCircle className="h-3.5 w-3.5" /> Comentar</button>
                  </div>
                </form>}
              </section>
              <section>
                <h3 className="mb-3 text-[12px] font-semibold">Anexos <span className="font-normal text-[#98A2B3]">({detail.data?.attachments.length || 0}/5)</span></h3>
                <div className="space-y-2">{detail.data?.attachments.map(att=>(
                  <button key={att.id} type="button" onClick={()=>void download(row.id,att).catch(err=>setFailure(err.message))}
                    className="flex w-full items-center justify-between gap-2 rounded-lg border border-[#EAECF0] p-3 text-left text-[11px] hover:bg-[#FAFBFC]">
                    <span className="flex items-center gap-2"><FileText className="h-4 w-4 text-[#85858B]" />{att.filename}</span>
                    <span className="text-[10px] text-[#85858B]">{att.visibility === "staff" ? "Interno" : "Aluno"} · {(att.byte_count/1024).toFixed(0)} KB</span>
                  </button>
                ))}</div>
                {canEdit && !["completed","rejected","cancelled"].includes(row.status) && <div className="mt-3 space-y-2">
                  <input type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" onChange={e=>setFile(e.target.files?.[0] || null)} aria-label="Selecionar anexo" className="block w-full text-[11px] text-[#667085]" />
                  <div className="flex flex-wrap justify-between gap-2">
                    <select aria-label="Visibilidade do anexo" className={inputStyle + " max-w-[164px]"} value={uploadVisibility} onChange={e=>setUploadVisibility(e.target.value as "student"|"staff")}>
                      <option value="staff">Somente equipe</option><option value="student">Visível ao aluno</option>
                    </select>
                    <button type="button" className={smallButton} disabled={!file || upload.isPending} onClick={()=>upload.mutate()}><UploadCloud className="h-3.5 w-3.5" /> Enviar anexo</button>
                  </div>
                  <p className="text-[10px] text-[#85858B]">PDF, PNG ou JPG, até 256 KiB; limite de 5 arquivos. Download protegido.</p>
                </div>}
              </section>
              <section>
                <h3 className="mb-2 text-[12px] font-semibold">Documento solicitado</h3>
                {row.generated_document_id ? <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#EAECF0] bg-[#FAFBFC] p-3">
                  <p className="break-all text-[11px] text-[#667085]">Documento vinculado: {row.generated_document_id}</p>
                  {canApprove && <button className={smallButton} type="button" disabled={action.isPending}
                    onClick={()=>action.mutate({path:"/documents/"+row.generated_document_id+"/publish"})}>
                    <CheckCircle2 className="h-3.5 w-3.5"/> Publicar documento
                  </button>}
                </div> : <>
                  <p className="mb-3 text-[11px] text-[#85858B]">Gere um rascunho a partir de um modelo aprovado para a categoria. A publicação é uma ação separada.</p>
                  <div className="flex flex-wrap gap-2">
                    <select className={inputStyle + " min-w-[180px] flex-1"} aria-label="Selecionar modelo" value={templateId} onChange={e=>setTemplateId(e.target.value)}>
                      <option value="">Selecione um modelo</option>
                      {availableTemplates.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                    {canEdit && <button type="button" disabled={action.isPending || !templateId || row.status !== "approved"} className={primaryButton}
                      onClick={()=>action.mutate({path:"/requests/"+row.id+"/document-draft",body:{template_id:templateId}})}>
                      Gerar rascunho
                    </button>}
                  </div>
                </>}
                <p className="mt-2 text-[10px] text-[#85858B]">Declarações, históricos e comprovantes exigem documento publicado para serem concluídos.</p>
              </section>
              <section>
                <h3 className="mb-3 text-[12px] font-semibold">Histórico auditável</h3>
                <ol className="space-y-3 border-l border-[#E7E9ED] pl-4">
                  {detail.data?.events.map(e=><li key={e.id} className="relative text-[11px] text-[#667085]">
                    <span className="absolute -left-[20px] top-1 h-2 w-2 rounded-full border-2 border-white bg-[#2563EB]" />
                    <p className="font-medium text-[#344054]">{LABELS[e.status as Status] || e.status} · {e.actor_type === "student" ? "Aluno" : "Equipe"}</p>
                    <p className="mt-0.5">{prettyDate(e.occurred_at)}</p>
                    {e.note && <p className="mt-1 whitespace-pre-wrap break-words">{e.note}</p>}
                  </li>)}
                </ol>
              </section>
            </div>
          </>}
        </section>
      </div>
    </>}

    {tab === "templates" && <div className="grid gap-5 lg:grid-cols-2">
      <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <h2 className="text-[14px] font-semibold">Modelos da instituição</h2>
        <p className="mt-1 text-[11px] text-[#85858B]">Os modelos são usados para gerar rascunhos, nunca documentos publicados automaticamente.</p>
        <div className="mt-4 space-y-2">
          {templates.data?.items.map(t=><article key={t.id} className="rounded-lg border border-[#EAECF0] p-3">
            <div className="flex justify-between gap-2">
              <strong className="text-[12px]">{t.name}</strong>
              <span className={"text-[10px] " + (t.is_active ? "text-[#027A48]" : "text-[#98A2B3]")}>{t.is_active ? "Ativo" : "Inativo"}</span>
            </div>
            <p className="mt-1 text-[11px] text-[#667085]">{CATEGORY[t.category] || t.category} · {t.document_kind}</p>
            <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-[11px] text-[#85858B]">{t.body_template}</p>
          </article>)}
          {templates.data?.items.length === 0 && <p className="py-12 text-center text-[12px] text-[#98A2B3]">Ainda não há modelos de documentos.</p>}
        </div>
      </section>
      <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <h2 className="text-[14px] font-semibold">Novo modelo</h2>
        {!canTemplates && <p className="mt-3 text-[12px] text-[#85858B]">Sua conta não tem permissão para gerenciar modelos.</p>}
        {canTemplates && <form onSubmit={createTemplate} className="mt-4 space-y-3">
          <label className="block text-[11px] text-[#667085]">Nome do modelo
            <input className={inputStyle + " mt-1"} required minLength={3} maxLength={120} value={templateName} onChange={e=>setTemplateName(e.target.value)} placeholder="Declaração de matrícula" />
          </label>
          <label className="block text-[11px] text-[#667085]">Categoria de solicitação
            <select className={inputStyle + " mt-1"} value={templateCategory} onChange={e=>setTemplateCategory(e.target.value)}>
              {Object.entries(CATEGORY).map(([id,label])=><option key={id} value={id}>{label}</option>)}
            </select>
          </label>
          <label className="block text-[11px] text-[#667085]">Tipo do documento
            <select className={inputStyle + " mt-1"} value={templateKind} onChange={e=>setTemplateKind(e.target.value)}>
              <option value="declaration">Declaração</option><option value="enrollment_proof">Comprovante</option>
              <option value="transcript">Histórico</option><option value="other">Outro</option>
            </select>
          </label>
          <label className="block text-[11px] text-[#667085]">Corpo do modelo
            <textarea required minLength={10} maxLength={10000} className={inputStyle + " mt-1 h-auto py-3 font-mono leading-5"} rows={8}
              value={templateBody} onChange={e=>setTemplateBody(e.target.value)} />
          </label>
          <p className="text-[11px] leading-5 text-[#85858B]">Variáveis permitidas: {templates.data?.variables.map(v=>"{{"+v+"}}").join(", ") || "student_name, registration, organization_name, today"}.</p>
          <button type="submit" className={primaryButton} disabled={action.isPending}><Plus className="h-3.5 w-3.5" /> Criar modelo</button>
        </form>}
      </section>
    </div>}

    {tab === "notifications" && <section className="max-w-3xl rounded-xl border border-[#EAECF0] bg-white">
      <div className="border-b border-[#EAECF0] p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold">Suas notificações</h2>
          <span className="text-[11px] text-[#667085]">{notificationsUnread} não lidas</span>
        </div>
        <p className="mt-1 text-[11px] text-[#85858B]">Avisos internos da plataforma, sem envio automático de mensagens externas.</p>
      </div>
      {notifications.data?.items.map(n=><button key={n.id} type="button" className={"flex w-full items-center justify-between gap-3 border-b border-[#F0F1F2] px-5 py-4 text-left hover:bg-[#FAFBFC] " + (!n.read_at ? "bg-[#F8FBFF]" : "")}
        onClick={async()=>{
          try {
            if (!n.read_at) await request("/notifications/"+n.id+"/read",{method:"POST"});
            setTab("queue");setFilter("all");setOffset(0);setSelectedId(n.request_id);refresh();
          } catch(err){setFailure((err as Error).message);}
        }}>
        <span><strong className="block text-[12px] font-semibold">{n.title}</strong><span className="mt-1 block text-[10px] text-[#85858B]">{prettyDate(n.created_at)}</span></span>
        {!n.read_at && <span className="h-2 w-2 shrink-0 rounded-full bg-[#2563EB]" />}
      </button>)}
      {!notifications.isLoading && !notifications.data?.items.length && <p className="py-16 text-center text-[12px] text-[#98A2B3]">Nenhuma notificação registrada.</p>}
    </section>}
  </main>;
}
