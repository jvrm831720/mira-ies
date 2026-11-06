"use client";

import { useEffect, useMemo, useState } from "react";
import { BookOpen, CheckCircle2, Clock3, FileText, GraduationCap, Loader2, RefreshCw } from "@/components/ui/icons";

const ROOT = "/api/v1/student-portal/academic-operations";
type Program = { id: string; program_name: string; curriculum_label: string; status: string };
type Term = { id: string; code: string; label: string; starts_on: string; ends_on: string };
type Offer = { id: string; code: string; subject_name: string; period_number: number; capacity: number | null; occupied: number; available: boolean };
type Enrollment = { id: string; kind: string; status: string; submitted_at: string; decision_note: string | null; class_ids: string[] };
type Transcript = { subject_name: string; term_label: string; grade_percent: string; attendance_percent: string; result: string; policy_version: number };
type ApiError = Error & { status?: number };

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(ROOT + path, {
    ...init, cache: "no-store", credentials: "same-origin",
    headers: {
      ...(typeof init.body === "string" ? { "Content-Type": "application/json" } : {}),
      ...(init.method && init.method !== "GET" ? { "X-Mira-Portal-Action": "1" } : {}),
    },
  });
  if (!r.ok) {
    const json = await r.json().catch(() => ({}));
    const e = new Error(
      typeof json.detail === "string" ? json.detail :
      r.status === 503 ? "A rematrícula digital ainda não foi habilitada pela sua instituição." :
      r.status === 401 ? "Sua sessão expirou. Entre novamente no portal." :
      "Não foi possível carregar esta informação.",
    ) as ApiError;
    e.status = r.status;
    throw e;
  }
  return r.json() as Promise<T>;
}
const statusLabel: Record<string, string> = {
  approved: "Aprovada", rejected: "Rejeitada", submitted: "Aguardando análise",
  enrollment: "Matrícula", reenrollment: "Rematrícula",
  passed: "Aprovado", failed: "Reprovado",
};
const date = (value: string) => new Date(value).toLocaleDateString("pt-BR");
const fieldStyle = "h-10 w-full rounded-lg border border-[var(--color-legacy-d0d5dd)] bg-white px-3 text-xs text-[var(--color-legacy-344054)] outline-none focus:border-[var(--color-legacy-2563eb)]";

export function AcademicOperationsPanel() {
  const [programs, setPrograms] = useState<Program[]>([]);
  const [terms, setTerms] = useState<Term[]>([]);
  const [requests, setRequests] = useState<Enrollment[]>([]);
  const [transcript, setTranscript] = useState<Transcript[]>([]);
  const [programId, setProgramId] = useState("");
  const [termId, setTermId] = useState("");
  const [offers, setOffers] = useState<Offer[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [active, setActive] = useState<"enrollment" | "transcript">("enrollment");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [available, setAvailable] = useState(false);
  const [message, setMessage] = useState("");
  const [failure, setFailure] = useState("");

  async function refresh() {
    try {
      const [p,t,r,h] = await Promise.all([
        api<{items:Program[]}>("/programs"),
        api<{items:Term[]}>("/terms"),
        api<{items:Enrollment[]}>("/enrollment-requests"),
        api<{items:Transcript[]}>("/transcript"),
      ]);
      setPrograms(p.items); setTerms(t.items); setRequests(r.items); setTranscript(h.items);
      setProgramId(current=>p.items.some(x=>x.id===current)?current:p.items[0]?.id||"");
      setTermId(current=>t.items.some(x=>x.id===current)?current:t.items[0]?.id||"");
      setAvailable(true);
      setFailure("");
    } catch(error) {
      setAvailable(false);
      setFailure(error instanceof Error ? error.message : "Serviço acadêmico indisponível.");
    } finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);

  useEffect(() => {
    let alive=true;
    setOffers([]);setSelected([]);
    if(!programId||!termId||!available) return;
    api<{items:Offer[]}>("/programs/"+encodeURIComponent(programId)+
      "/offers?term_id="+encodeURIComponent(termId))
      .then(v=>{if(alive)setOffers(v.items);})
      .catch(err=>{if(alive)setFailure(err instanceof Error?err.message:"Ofertas indisponíveis.");});
    return ()=>{alive=false;};
  }, [programId,termId,available]);

  const current = useMemo(()=>programs.find(x=>x.id===programId),[programId,programs]);
  const awaiting = requests.some(r=>r.status==="submitted");
  const hasSubmittedForTerm = requests.some(r=>r.status!=="rejected" && r.class_ids.some(id=>offers.some(o=>o.id===id)));
  async function submit() {
    if(!programId||!termId||!selected.length)return;
    setBusy(true);setFailure("");setMessage("");
    try {
      await api("/enrollment-requests",{
        method:"POST",
        body:JSON.stringify({student_program_id:programId,term_id:termId,class_ids:selected}),
      });
      setSelected([]);
      setMessage("Solicitação registrada. A instituição precisa aprovar sua matrícula.");
      await refresh();
    }catch(err){setFailure(err instanceof Error?err.message:"Não foi possível enviar o pedido.");}
    finally{setBusy(false);}
  }

  return <section aria-label="Matrícula e histórico acadêmico" className="overflow-hidden rounded-xl border border-[var(--color-line)] bg-white">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-legacy-eaecf0)] px-6 py-5">
      <div>
        <h2 className="text-[length:var(--type-heading-compact)] font-semibold">Sua jornada acadêmica</h2>
        <p className="mt-1 text-xs text-[var(--color-legacy-667085)]">Matrículas por período, ofertas de disciplinas e histórico finalizado.</p>
      </div>
      <button type="button" onClick={()=>void refresh()} className="flex items-center gap-1.5 rounded-lg border border-[var(--color-legacy-eaecf0)] px-3 py-2 text-[length:var(--type-caption)] text-[var(--color-legacy-475467)] hover:bg-[var(--color-source-f9fafb)]">
        <RefreshCw className="h-3.5 w-3.5" /> Atualizar
      </button>
    </div>
    <div className="flex gap-1.5 border-b border-[var(--color-legacy-eaecf0)] px-5 pt-2">
      {([["enrollment","Matrícula e rematrícula",GraduationCap],["transcript","Histórico acadêmico",FileText]] as const).map(([id,label,Icon])=>
        <button type="button" key={id} onClick={()=>setActive(id)}
          className={"flex items-center gap-2 border-b-2 px-3 py-3 text-xs font-semibold " +
            (active===id?"border-[var(--color-legacy-2563eb)] text-[var(--color-legacy-2563eb)]":"border-transparent text-[var(--color-legacy-667085)]")}>
          <Icon className="h-4 w-4"/>{label}
        </button>)}
    </div>
    <div className="space-y-5 p-6">
      {loading && <p className="flex items-center gap-2 text-xs text-[var(--color-legacy-667085)]"><Loader2 className="h-4 w-4 animate-spin"/> Consultando informações…</p>}
      {failure && <p role="alert" className="rounded-lg bg-[var(--color-legacy-fff4f3)] p-3 text-xs text-[var(--color-legacy-b42318)]">{failure}</p>}
      {message && <p role="status" className="rounded-lg bg-[var(--color-legacy-eef7f1)] p-3 text-xs text-[var(--color-source-027a48)]">{message}</p>}
      {!loading&&!available&&<p className="text-xs text-[var(--color-legacy-667085)]">
        Essa etapa depende da habilitação institucional. Outros serviços do portal continuam disponíveis.
      </p>}
      {!loading&&available&&active==="enrollment"&&<>
        {!programs.length&&<div className="rounded-lg bg-[var(--color-legacy-f8fafc)] px-4 py-5 text-xs text-[var(--color-legacy-667085)]">
          Sua instituição ainda não registrou um vínculo com curso e currículo publicado. Entre em contato com a secretaria.
        </div>}
        {!!programs.length&&<div className="grid gap-3 md:grid-cols-2">
          <label className="text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-475467)]">Curso
            <select className={fieldStyle+" mt-1"} value={programId} onChange={e=>setProgramId(e.target.value)}>
              {programs.map(p=><option key={p.id} value={p.id}>{p.program_name} · {p.curriculum_label}</option>)}
            </select>
          </label>
          <label className="text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-475467)]">Período acadêmico
            <select className={fieldStyle+" mt-1"} value={termId} onChange={e=>setTermId(e.target.value)}>
              <option value="">Selecionar período</option>
              {terms.map(t=><option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
        </div>}
        {current?.status!=="active"&&current&&<p className="rounded-lg bg-[var(--color-source-fffaeb)] p-3 text-[length:var(--type-caption)] text-[var(--color-legacy-92400e)]">
          Vínculo não ativo. Solicite regularização acadêmica à secretaria.
        </p>}
        {programs.length>0&&termId&&current?.status==="active"&&<div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold">Disciplinas ofertadas</h3>
            <span className="text-[length:var(--type-caption)] text-[var(--color-legacy-98a2b3)]">{selected.length} selecionadas</span>
          </div>
          {!offers.length&&<p className="rounded-lg border border-[var(--color-legacy-eaecf0)] p-5 text-xs text-[var(--color-legacy-667085)]">Nenhuma oferta aberta para este período.</p>}
          <div className="divide-y divide-[var(--color-legacy-eaecf0)] overflow-hidden rounded-lg border border-[var(--color-legacy-eaecf0)]">
            {offers.map(o=><label key={o.id} className="flex cursor-pointer items-center gap-3 p-3 hover:bg-[var(--color-source-f9fafb)]">
              <input type="checkbox" checked={selected.includes(o.id)} disabled={!o.available}
                onChange={e=>setSelected(v=>e.target.checked?[...v,o.id]:v.filter(x=>x!==o.id))}
                className="h-4 w-4 accent-[var(--color-legacy-2563eb)]" />
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-semibold text-[var(--color-legacy-344054)]">{o.subject_name}</span>
                <span className="mt-1 block text-[length:var(--type-caption)] text-[var(--color-legacy-85858b)]">{o.code} · Etapa {o.period_number}</span>
              </span>
              <span className={"text-[length:var(--type-caption)] "+(o.available?"text-[var(--color-legacy-667085)]":"text-[var(--color-legacy-b42318)]")}>
                {o.capacity===null?"Vagas sem limite informado":o.available?o.capacity-o.occupied+" vagas":"Lotada"}
              </span>
            </label>)}
          </div>
          <button type="button" onClick={()=>void submit()} disabled={busy||!selected.length||hasSubmittedForTerm}
            className="rounded-lg bg-[var(--color-legacy-202124)] px-4 py-2.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
            {busy?"Registrando…":"Solicitar matrícula nas disciplinas"}
          </button>
          <p className="text-[length:var(--type-caption)] leading-5 text-[var(--color-legacy-85858b)]">
            A seleção não reserva vaga automaticamente. A instituição valida currículo, pré-requisitos, disponibilidade e regras antes da aprovação.
          </p>
        </div>}
        <div className="border-t border-[var(--color-legacy-eaecf0)] pt-4">
          <h3 className="mb-3 text-xs font-semibold">Acompanhar solicitações{awaiting?" · pendentes":""}</h3>
          {requests.length===0&&<p className="text-xs text-[var(--color-legacy-98a2b3)]">Nenhuma matrícula solicitada ainda.</p>}
          {requests.map(r=><article key={r.id} className="mb-2 flex flex-wrap items-start justify-between gap-3 rounded-lg border border-[var(--color-legacy-eaecf0)] p-3">
            <div><p className="text-xs font-semibold">{statusLabel[r.kind]||r.kind} · {date(r.submitted_at)}</p>
              <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">{r.class_ids.length} disciplina(s) solicitada(s)</p>
              {r.decision_note&&<p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-475467)]">Decisão: {r.decision_note}</p>}
            </div>
            <span className={"rounded-lg px-2 py-1 text-[length:var(--type-caption)] font-medium "+
              (r.status==="approved"?"bg-[var(--color-source-ecfdf3)] text-[var(--color-source-027a48)]":r.status==="rejected"?"bg-[var(--color-red-tint)] text-[var(--color-legacy-b42318)]":"bg-[var(--color-source-eff4ff)] text-[var(--color-legacy-175cd3)]")}>
              {statusLabel[r.status]||r.status}
            </span>
          </article>)}
          <p className="mt-3 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]">Para contestar uma decisão ou pedir exceção curricular, abra um requerimento em Serviços do aluno → Revisão acadêmica.</p>
        </div>
      </>}
      {!loading&&available&&active==="transcript"&&<>
        <div className="flex items-center gap-2 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]"><BookOpen className="h-4 w-4"/> Somente disciplinas encerradas com avaliação e chamada verificadas.</div>
        {!transcript.length&&<p className="rounded-lg bg-[var(--color-source-f9fafb)] p-5 text-xs text-[var(--color-legacy-667085)]">Nenhum resultado finalizado disponível.</p>}
        <div className="divide-y divide-[var(--color-legacy-eaecf0)] overflow-hidden rounded-lg border border-[var(--color-legacy-eaecf0)]">
          {transcript.map((item,i)=><div key={i} className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div><p className="text-xs font-semibold text-[var(--color-legacy-344054)]">{item.subject_name}</p>
              <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-667085)]"><Clock3 className="mr-1 inline h-3 w-3"/>{item.term_label} · Nota {item.grade_percent}% · Frequência {item.attendance_percent}%</p>
              <p className="mt-1 text-[length:var(--type-overline)] text-[var(--color-legacy-98a2b3)]">Regra institucional v{item.policy_version}</p>
            </div>
            <span className={item.result==="passed"?"text-xs font-semibold text-[var(--color-source-027a48)]":"text-xs font-semibold text-[var(--color-legacy-b42318)]"}>
              {item.result==="passed"&&<CheckCircle2 className="mr-1 inline h-3.5 w-3.5"/>}{statusLabel[item.result]||item.result}
            </span>
          </div>)}
        </div>
        <p className="text-[length:var(--type-caption)] leading-5 text-[var(--color-legacy-98a2b3)]">Este histórico é uma visualização operacional. Para documentos oficiais, acesse Serviços do aluno e solicite emissão.</p>
      </>}
    </div>
  </section>;
}
