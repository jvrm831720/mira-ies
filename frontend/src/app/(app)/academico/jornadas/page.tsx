"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpenCheck, CalendarDays, CheckCircle2, Clock3, FileText,
  GraduationCap, Loader2, Plus, RefreshCw, ShieldCheck, Users,
} from "@/components/ui/icons";
import { api } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

const ROOT = "/api/v1/native-academic/operations";
const field = "h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-[12px] outline-none focus:border-[#2563EB]";
const btn = "inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-[#D0D5DD] px-3 text-[12px] font-medium hover:bg-[#F9FAFB] disabled:opacity-40";
const primary = "inline-flex h-10 items-center justify-center rounded-lg bg-[#202124] px-4 text-[12px] font-semibold text-white disabled:opacity-40";
const labels: Record<string,string> = {submitted:"Recebida",approved:"Aprovada",rejected:"Rejeitada",passed:"Aprovado",failed:"Reprovado"};
type Item = {id:string;code:string;name:string;status:string;program_id?:string};
type Curriculum = {id:string;program_id:string;code:string;label:string;status:string};
type Class = {id:string;code:string;subject_id:string;term_id:string;status:string;capacity:number|null;enrollment_open:boolean};
type Policy = {id:string;version:number;status:string;passing_percent:string;min_attendance_percent:string;max_classes_per_term:number};
type Overview = {counts:{active_students:number;enrollment_requests:number;outcomes:number};policies:Policy[];curricula:Curriculum[];
  programs:Item[];subjects:Item[];terms:{id:string;label:string;status:string}[];classes:Class[]};
type Student = {id:string;name:string;registration:string};
type ProgramLink = {id:string;program_name:string;curriculum_label:string;status:string};
type Offer = {id:string;code:string;subject_name:string;available:boolean;capacity:number|null;occupied:number};
type Request = {id:string;status:string;student_name:string;student_registration:string;program_name:string;term_label:string;kind:string;class_codes:string[]};
type Roster = {class:{id:string;code:string;status:string};
  students:{student_id:string;name:string;registration:string}[];
  assessments:{id:string;title:string;max_score:string;publication_status:string}[];
  lessons:{id:string;topic:string|null;starts_at:string;publication_status:string}[];
  grades:{assessment_id:string;student_id:string;score:string;publication_status:string}[];
  attendance:{lesson_id:string;student_id:string;status:string}[]};
type Preview = {ready:boolean;reason?:string;items:{student_id:string;name:string;ready:boolean;reason?:string;score_percent?:string;attendance_percent?:string;result?:string}[]};
type Transcript = {subject_name:string;term_label:string;grade_percent:string;attendance_percent:string;result:string;policy_version:number};
type Tab = "matriculas"|"curriculos"|"ofertas"|"diario"|"regras"|"historico";
type CurriculumItem = {subject_id:string;period_number:string;prerequisite_subject_id:string;required:boolean};

async function call<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getAccessToken();if(!token)throw new Error("Faça login na instituição.");
  const r=await fetch(ROOT+path,{...init,cache:"no-store",headers:{
    Authorization:"Bearer "+token,...(typeof init.body==="string"?{"Content-Type":"application/json"}:{})}});
  if(!r.ok){const j=await r.json().catch(()=>({}));
    throw new Error(typeof j.detail==="string"?j.detail:r.status===503?"Módulo acadêmico ainda não habilitado.":"Operação indisponível.");
  }
  return r.json() as Promise<T>;
}
const blank:CurriculumItem={subject_id:"",period_number:"1",prerequisite_subject_id:"",required:true};

export default function JourneysPage(){
  const me=useQuery({queryKey:["org-me"],queryFn:api.me,retry:false});
  const canView=me.data?.operation_profile==="institution"&&(me.data.permissions?
    me.data.permissions.includes("students.sensitive.view"):["admin","coordinator"].includes(me.data.role||""));
  const canEdit=!!canView&&(me.data?.permissions?
    me.data.permissions.includes("students.edit"):["admin","coordinator"].includes(me.data?.role||""));
  const canApprove=!!canView&&(me.data?.permissions?
    me.data.permissions.includes("critical.manage"):me.data?.role==="admin");
  const canManage=!!canView&&(me.data?.permissions?
    me.data.permissions.includes("settings.manage"):me.data?.role==="admin");
  const [tab,setTab]=useState<Tab>("matriculas");
  const [overview,setOverview]=useState<Overview|null>(null);
  const [requests,setRequests]=useState<Request[]>([]);
  const [loading,setLoading]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const [note,setNote]=useState("");
  const [studentQuery,setStudentQuery]=useState("");
  const [results,setResults]=useState<Student[]>([]);
  const [student,setStudent]=useState<Student|null>(null);
  const [studentPrograms,setStudentPrograms]=useState<ProgramLink[]>([]);
  const [studentProgram,setStudentProgram]=useState("");
  const [admitProgram,setAdmitProgram]=useState("");
  const [admitCurriculum,setAdmitCurriculum]=useState("");
  const [term,setTerm]=useState("");
  const [offers,setOffers]=useState<Offer[]>([]);
  const [picked,setPicked]=useState<string[]>([]);
  const [curriculumProgram,setCurriculumProgram]=useState("");
  const [curriculumCode,setCurriculumCode]=useState("");
  const [curriculumName,setCurriculumName]=useState("");
  const [curriculumItems,setCurriculumItems]=useState<CurriculumItem[]>([{...blank}]);
  const [offerId,setOfferId]=useState("");
  const [offerCapacity,setOfferCapacity]=useState("");
  const [offerOpen,setOfferOpen]=useState(false);
  const [passing,setPassing]=useState("60");
  const [minAttendance,setMinAttendance]=useState("75");
  const [maxClasses,setMaxClasses]=useState("8");
  const [allowReenroll,setAllowReenroll]=useState(true);
  const [excusedExcluded,setExcusedExcluded]=useState(true);
  const [opens,setOpens]=useState("");
  const [closes,setCloses]=useState("");
  const [classId,setClassId]=useState("");
  const [roster,setRoster]=useState<Roster|null>(null);
  const [assessmentId,setAssessmentId]=useState("");
  const [lessonId,setLessonId]=useState("");
  const [grades,setGrades]=useState<Record<string,string>>({});
  const [presence,setPresence]=useState<Record<string,string>>({});
  const [preview,setPreview]=useState<Preview|null>(null);
  const [transcript,setTranscript]=useState<Transcript[]>([]);

  async function refresh(){
    setLoading(true);
    try{const [data,queue]=await Promise.all([
      call<Overview>("/overview"),call<{items:Request[]}>("/enrollment-requests?status=submitted")]);
      setOverview(data);setRequests(queue.items);setError("");
    }catch(e){setError(e instanceof Error?e.message:"Falha ao carregar módulo.");}
    finally{setLoading(false);}
  }
  useEffect(()=>{if(canView)void refresh();},[canView]);
  async function act<T>(path:string,body?:unknown):Promise<T|undefined>{
    setBusy(true);setError("");setMessage("");
    try{const result=await call<T>(path,{method:"POST",...(body?{body:JSON.stringify(body)}:{})});
      setMessage("Alteração registrada com sucesso.");await refresh();return result;
    }catch(e){setError(e instanceof Error?e.message:"Não foi possível salvar.");return undefined;}
    finally{setBusy(false);}
  }
  async function search(){
    if(studentQuery.trim().length<2)return;
    try{const r=await call<{items:Student[]}>("/students/search?q="+encodeURIComponent(studentQuery));
      setResults(r.items);if(!r.items.length)setError("Nenhum aluno encontrado.");
    }catch(e){setError((e as Error).message);}
  }
  async function chooseStudent(s:Student){
    setStudent(s);setResults([]);setStudentPrograms([]);setTranscript([]);
    try{const [programs,history]=await Promise.all([
      call<{items:ProgramLink[]}>("/students/"+s.id+"/programs"),
      call<{items:Transcript[]}>("/students/"+s.id+"/transcript")]);
      setStudentPrograms(programs.items);setStudentProgram(programs.items[0]?.id||"");
      setTranscript(history.items);
    }catch(e){setError((e as Error).message);}
  }
  async function loadOffers(programId:string,termId:string){
    setPicked([]);setOffers([]);if(!programId||!termId)return;
    try{const r=await call<{items:Offer[]}>("/programs/"+programId+"/offers?term_id="+termId);setOffers(r.items);}
    catch(e){setError((e as Error).message);}
  }
  async function loadRoster(id:string){
    setRoster(null);setPreview(null);setGrades({});setPresence({});
    if(!id)return;
    try{const r=await call<Roster>("/classes/"+id+"/roster");
      setRoster(r);setAssessmentId(r.assessments[0]?.id||"");setLessonId(r.lessons[0]?.id||"");
    }catch(e){setError((e as Error).message);}
  }
  async function createCurriculum(e:FormEvent){
    e.preventDefault();
    const v=await act("/curricula",{program_id:curriculumProgram,code:curriculumCode,label:curriculumName,
      items:curriculumItems.map(x=>({subject_id:x.subject_id,period_number:Number(x.period_number),
        prerequisite_subject_id:x.prerequisite_subject_id||null,required:x.required}))});
    if(v){setCurriculumCode("");setCurriculumName("");setCurriculumItems([{...blank}]);}
  }
  async function createPolicy(e:FormEvent){
    e.preventDefault();
    await act("/policies",{passing_percent:passing,min_attendance_percent:minAttendance,
      max_classes_per_term:Number(maxClasses),allow_reenrollment:allowReenroll,excused_excluded:excusedExcluded,
      enrollment_opens_on:opens||null,enrollment_closes_on:closes||null});
  }
  const currentCurricula=overview?.curricula.filter(x=>x.program_id===admitProgram&&x.status==="published")||[];
  const eligibleSubjects=overview?.subjects.filter(x=>x.program_id===curriculumProgram&&x.status==="active")||[];
  const assessment=roster?.assessments.find(x=>x.id===assessmentId);
  const lesson=roster?.lessons.find(x=>x.id===lessonId);
  async function saveGrades(){
    if(!classId||!assessmentId)return;
    const entries=Object.entries(grades).filter(([,v])=>v.trim()).map(([student_id,score])=>({student_id,score}));
    if(entries.length===0){setError("Preencha ao menos uma nota.");return;}
    const v=await act("/classes/"+classId+"/grades",{assessment_id:assessmentId,entries});
    if(v)await loadRoster(classId);
  }
  async function saveAttendance(){
    if(!classId||!lessonId)return;
    const entries=Object.entries(presence).filter(([,v])=>v).map(([student_id,status])=>({student_id,status}));
    if(entries.length===0){setError("Registre ao menos uma chamada.");return;}
    const v=await act("/classes/"+classId+"/attendance",{lesson_id:lessonId,entries});
    if(v)await loadRoster(classId);
  }
  if(me.isLoading)return <main className="p-10 text-[12px] text-[#667085]">Verificando acesso…</main>;
  if(!canView)return <main className="p-10 text-[12px] text-[#667085]">Acesso exclusivo à equipe institucional autorizada.</main>;
  return <main className="min-h-screen bg-[#FCFCFD] p-5 text-[#202124] md:p-9">
    <header className="mb-7 flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-[11px] font-medium uppercase tracking-[0.1em] text-[#85858B]">Acadêmico / Operação</p>
        <h1 className="mt-2 text-[27px] font-semibold tracking-[-0.04em]">Jornadas acadêmicas</h1>
        <p className="mt-1 text-[13px] text-[#667085]">Matrícula, currículo, ofertas, diários e resultados sob regras institucionais.</p>
      </div>
      <button type="button" onClick={()=>void refresh()} className={btn}><RefreshCw className="h-4 w-4"/>Atualizar</button>
    </header>
    <div className="mb-5 grid gap-3 md:grid-cols-3">
      {([["Solicitações para análise",overview?.counts.enrollment_requests,Clock3],
        ["Vínculos acadêmicos ativos",overview?.counts.active_students,Users],
        ["Resultados finalizados",overview?.counts.outcomes,CheckCircle2]] as const).map(([label,count,Icon])=>
        <div key={label} className="rounded-xl border border-[#EAECF0] bg-white p-4">
          <Icon className="h-4 w-4 text-[#85858B]"/><p className="mt-3 text-[11px] text-[#667085]">{label}</p>
          <p className="mt-1 text-[23px] font-semibold">{count??"—"}</p>
        </div>)}
    </div>
    <nav aria-label="Jornadas acadêmicas" className="mb-5 flex flex-wrap gap-1 rounded-xl border border-[#EAECF0] bg-white p-1.5">
      {([["matriculas","Matrículas",GraduationCap],["curriculos","Grade curricular",BookOpenCheck],
        ["ofertas","Ofertas",CalendarDays],["diario","Diário de classe",FileText],
        ["regras","Regras",ShieldCheck],["historico","Históricos",CheckCircle2]] as const).map(([key,label,Icon])=>
        <button key={key} type="button" onClick={()=>setTab(key)} aria-current={tab===key?"page":undefined}
          className={"inline-flex items-center gap-2 rounded-lg px-3 py-2 text-[12px] font-medium "+
            (tab===key?"bg-[#EFF4FF] text-[#2563EB]":"text-[#667085] hover:bg-[#F9FAFB]")}>
          <Icon className="h-4 w-4"/>{label}</button>)}
    </nav>
    {loading&&!overview&&<p className="mb-4 text-[12px] text-[#667085]"><Loader2 className="mr-2 inline h-4 w-4 animate-spin"/>Carregando…</p>}
    {error&&<p role="alert" className="mb-4 rounded-lg border border-[#FED4D2] bg-[#FFF5F5] p-3 text-[12px] text-[#B42318]">{error}</p>}
    {message&&<p role="status" className="mb-4 rounded-lg border border-[#D5EDE3] bg-[#F2FCF7] p-3 text-[12px] text-[#027A48]">{message}</p>}

    {tab==="regras"&&<div className="grid gap-5 xl:grid-cols-2">
      <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <h2 className="text-[15px] font-semibold">Regras da instituição</h2>
        <p className="mt-1 text-[12px] text-[#667085]">Versões publicadas são imutáveis. A versão nova depende de aprovação.</p>
        <div className="mt-4 space-y-2">{overview?.policies.map(p=><article key={p.id} className="flex items-center justify-between gap-2 rounded-lg border border-[#EAECF0] p-3">
          <div><strong className="text-[12px]">Versão {p.version} · {p.status}</strong>
            <p className="mt-1 text-[11px] text-[#667085]">Nota ≥ {p.passing_percent}% · Frequência ≥ {p.min_attendance_percent}% · Limite {p.max_classes_per_term} disciplinas</p>
          </div>
          {canApprove&&p.status==="draft"&&<button type="button" disabled={busy} className={btn} onClick={()=>void act("/policies/"+p.id+"/publish")}>Publicar</button>}
        </article>)}</div>
        {!overview?.policies.length&&<p className="mt-4 text-[12px] text-[#667085]">Não há regras cadastradas. Novas matrículas ficam bloqueadas.</p>}
      </section>
      <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <h2 className="text-[15px] font-semibold">Criar versão de regras</h2>
        {canManage?<form onSubmit={e=>void createPolicy(e)} className="mt-4 space-y-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="text-[11px] text-[#667085]">Nota mínima (%)
              <input className={field+" mt-1"} type="number" min="0" max="100" step="0.01" required value={passing} onChange={e=>setPassing(e.target.value)}/></label>
            <label className="text-[11px] text-[#667085]">Frequência (%)
              <input className={field+" mt-1"} type="number" min="0" max="100" step="0.01" required value={minAttendance} onChange={e=>setMinAttendance(e.target.value)}/></label>
            <label className="text-[11px] text-[#667085]">Máx. disciplinas
              <input className={field+" mt-1"} type="number" min="1" max="30" required value={maxClasses} onChange={e=>setMaxClasses(e.target.value)}/></label>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-[11px] text-[#667085]">Início da janela
              <input className={field+" mt-1"} type="date" value={opens} onChange={e=>setOpens(e.target.value)}/></label>
            <label className="text-[11px] text-[#667085]">Fim da janela
              <input className={field+" mt-1"} type="date" value={closes} onChange={e=>setCloses(e.target.value)}/></label>
          </div>
          <label className="flex items-center gap-2 text-[11px] text-[#667085]"><input type="checkbox" checked={allowReenroll} onChange={e=>setAllowReenroll(e.target.checked)}/>Permitir rematrícula</label>
          <label className="flex items-center gap-2 text-[11px] text-[#667085]"><input type="checkbox" checked={excusedExcluded} onChange={e=>setExcusedExcluded(e.target.checked)}/>Excluir faltas justificadas do denominador</label>
          <button type="submit" className={primary} disabled={busy}>Criar rascunho</button>
        </form>:<p className="mt-4 text-[12px] text-[#85858B]">Sua conta não gerencia regras.</p>}
      </section>
    </div>}

    {tab==="curriculos"&&<div className="grid gap-5 xl:grid-cols-2">
      <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <h2 className="text-[15px] font-semibold">Matrizes curriculares</h2>
        <p className="mt-1 text-[12px] text-[#667085]">Cada curso pode ter várias matrizes; os vínculos existentes preservam sua versão.</p>
        <div className="mt-4 space-y-2">{overview?.curricula.map(c=><article key={c.id} className="flex items-center justify-between gap-2 rounded-lg border border-[#EAECF0] p-3">
          <div><p className="text-[12px] font-semibold">{c.label}</p><p className="mt-1 text-[11px] text-[#667085]">{c.code} · {overview.programs.find(p=>p.id===c.program_id)?.name} · {c.status}</p></div>
          {canApprove&&c.status==="draft"&&<button className={btn} disabled={busy} onClick={()=>void act("/curricula/"+c.id+"/publish")}>Publicar</button>}
        </article>)}</div>
      </section>
      <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <h2 className="text-[15px] font-semibold">Montar grade curricular</h2>
        {canManage?<form onSubmit={e=>void createCurriculum(e)} className="mt-4 space-y-3">
          <label className="block text-[11px] text-[#667085]">Curso
            <select required value={curriculumProgram} onChange={e=>{setCurriculumProgram(e.target.value);setCurriculumItems([{...blank}]);}} className={field+" mt-1"}>
              <option value="">Selecionar curso</option>{overview?.programs.filter(p=>p.status==="active").map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
            </select></label>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-[11px] text-[#667085]">Código / versão
              <input className={field+" mt-1"} required minLength={2} maxLength={40} value={curriculumCode} onChange={e=>setCurriculumCode(e.target.value)}/></label>
            <label className="text-[11px] text-[#667085]">Nome
              <input className={field+" mt-1"} required minLength={3} maxLength={160} value={curriculumName} onChange={e=>setCurriculumName(e.target.value)}/></label>
          </div>
          <div className="space-y-2">{curriculumItems.map((item,index)=><div key={index} className="rounded-lg border border-[#EAECF0] bg-[#FAFBFC] p-3">
            <div className="flex justify-between text-[11px] font-medium"><span>Disciplina {index+1}</span>
              {curriculumItems.length>1&&<button type="button" className="text-[#B42318]" onClick={()=>setCurriculumItems(v=>v.filter((_,i)=>i!==index))}>Remover</button>}</div>
            <select className={field+" mt-2"} required value={item.subject_id} onChange={e=>setCurriculumItems(v=>v.map((it,i)=>i===index?{...it,subject_id:e.target.value}:it))}>
              <option value="">Selecionar disciplina</option>{eligibleSubjects.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <label className="text-[11px] text-[#667085]">Período
                <input type="number" required min="1" max="30" className={field+" mt-1"} value={item.period_number}
                  onChange={e=>setCurriculumItems(v=>v.map((it,i)=>i===index?{...it,period_number:e.target.value}:it))}/></label>
              <label className="text-[11px] text-[#667085]">Pré-requisito
                <select className={field+" mt-1"} value={item.prerequisite_subject_id}
                  onChange={e=>setCurriculumItems(v=>v.map((it,i)=>i===index?{...it,prerequisite_subject_id:e.target.value}:it))}>
                  <option value="">Nenhum</option>{curriculumItems.slice(0,index).filter(x=>x.subject_id).map(x=><option key={x.subject_id} value={x.subject_id}>
                    {eligibleSubjects.find(s=>s.id===x.subject_id)?.name||x.subject_id}</option>)}</select></label>
            </div>
            <label className="mt-2 flex items-center gap-2 text-[11px] text-[#667085]"><input type="checkbox" checked={item.required}
              onChange={e=>setCurriculumItems(v=>v.map((it,i)=>i===index?{...it,required:e.target.checked}:it))}/>Obrigatória</label>
          </div>)}</div>
          <div className="flex flex-wrap gap-2"><button className={btn} type="button" onClick={()=>setCurriculumItems(v=>[...v,{...blank}])}><Plus className="h-3 w-3"/>Adicionar disciplina</button>
            <button className={primary} disabled={busy} type="submit">Salvar grade curricular</button></div>
        </form>:<p className="mt-4 text-[12px] text-[#85858B]">Permissão de gestão necessária.</p>}
      </section>
    </div>}

    {tab==="ofertas"&&<section className="max-w-3xl rounded-xl border border-[#EAECF0] bg-white p-5">
      <h2 className="text-[15px] font-semibold">Ofertar disciplinas</h2>
      <p className="mt-1 text-[12px] text-[#667085]">As turmas são cadastradas em Gestão acadêmica; a abertura de vagas é controlada separadamente.</p>
      <div className="mt-5 space-y-4">
        <label className="block text-[11px] text-[#667085]">Turma
          <select value={offerId} onChange={e=>{setOfferId(e.target.value);const c=overview?.classes.find(x=>x.id===e.target.value);
            setOfferCapacity(c?.capacity==null?"":String(c.capacity));setOfferOpen(c?.enrollment_open||false);}} className={field+" mt-1"}>
            <option value="">Selecionar turma</option>
            {overview?.classes.map(c=><option key={c.id} value={c.id}>
              {c.code} · {overview.subjects.find(s=>s.id===c.subject_id)?.name} · {c.status}</option>)}
          </select></label>
        <label className="block text-[11px] text-[#667085]">Capacidade da turma (opcional)
          <input type="number" min="1" max="10000" className={field+" mt-1"} value={offerCapacity} onChange={e=>setOfferCapacity(e.target.value)}/></label>
        <label className="flex items-center gap-2 text-[12px] text-[#475467]"><input type="checkbox" checked={offerOpen} onChange={e=>setOfferOpen(e.target.checked)}/>Aceitar novas solicitações de matrícula</label>
        {canApprove&&<button type="button" className={primary} disabled={busy||!offerId}
          onClick={()=>void act("/classes/"+offerId+"/offer",{capacity:offerCapacity?Number(offerCapacity):null,enrollment_open:offerOpen})}>Salvar oferta</button>}
      </div>
    </section>}

    {tab==="matriculas"&&<div className="grid gap-5 xl:grid-cols-2">
      <section className="rounded-xl border border-[#EAECF0] bg-white p-5">
        <h2 className="text-[15px] font-semibold">Solicitações pendentes</h2>
        <p className="mt-1 text-[12px] text-[#667085]">Aprovação exige permissões, vagas e pré-requisitos verificados.</p>
        <textarea className={field+" mt-4 h-auto py-2"} rows={2} placeholder="Justificativa da decisão…" maxLength={500}
          value={note} onChange={e=>setNote(e.target.value)}/>
        <div className="mt-4 space-y-2">{requests.map(r=><article key={r.id} className="rounded-lg border border-[#EAECF0] p-3">
          <p className="text-[12px] font-semibold">{r.student_name}</p>
          <p className="mt-1 text-[11px] text-[#667085]">{r.student_registration} · {r.program_name} · {r.term_label}</p>
          <p className="mt-1 text-[11px] text-[#667085]">{r.class_codes.join(", ")||"Turmas solicitadas"}</p>
          {canApprove&&<div className="mt-3 flex gap-2">
            <button type="button" className={primary} disabled={busy||note.trim().length<3}
              onClick={()=>void act("/enrollment-requests/"+r.id+"/decide",{approve:true,note})}>Aprovar</button>
            <button type="button" className={btn} disabled={busy||note.trim().length<3}
              onClick={()=>void act("/enrollment-requests/"+r.id+"/decide",{approve:false,note})}>Rejeitar</button>
          </div>}
        </article>)}</div>
        {!requests.length&&<p className="mt-4 rounded-lg bg-[#F8FAFC] p-4 text-[12px] text-[#667085]">Nenhum pedido aguardando decisão.</p>}
      </section>
      <section className="space-y-4">
        <div className="rounded-xl border border-[#EAECF0] bg-white p-5">
          <h2 className="text-[15px] font-semibold">Vincular aluno ao curso</h2>
          <div className="mt-4 flex gap-2">
            <input className={field} placeholder="Buscar nome ou matrícula" value={studentQuery} onChange={e=>setStudentQuery(e.target.value)}
              onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();void search();}}}/>
            <button className={btn} type="button" onClick={()=>void search()} disabled={studentQuery.trim().length<2}>Buscar</button>
          </div>
          {results.map(s=><button key={s.id} type="button" onClick={()=>void chooseStudent(s)}
            className="mt-2 block w-full rounded-lg border border-[#EAECF0] p-3 text-left text-[11px] hover:bg-[#F9FAFB]">
            {s.name} · {s.registration}</button>)}
          {student&&<p className="mt-3 text-[12px] font-semibold">{student.name} · {student.registration}</p>}
          {student&&canEdit&&<form onSubmit={async e=>{e.preventDefault();const r=await act("/programs/enroll",{
            student_id:student.id,program_id:admitProgram,curriculum_id:admitCurriculum});if(r)await chooseStudent(student);
          }} className="mt-3 space-y-3">
            <select required value={admitProgram} onChange={e=>{setAdmitProgram(e.target.value);setAdmitCurriculum("");}} className={field}>
              <option value="">Selecionar curso</option>
              {overview?.programs.filter(p=>p.status==="active").map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <select required value={admitCurriculum} onChange={e=>setAdmitCurriculum(e.target.value)} className={field}>
              <option value="">Selecionar currículo publicado</option>
              {currentCurricula.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
            <button type="submit" className={primary} disabled={busy||!admitCurriculum}>Vincular ao curso</button>
          </form>}
        </div>
        {!!studentPrograms.length&&<div className="rounded-xl border border-[#EAECF0] bg-white p-5">
          <h2 className="text-[15px] font-semibold">Solicitar oferta pela secretaria</h2>
          <div className="mt-4 space-y-3">
            <select value={studentProgram} onChange={e=>{setStudentProgram(e.target.value);void loadOffers(e.target.value,term);}} className={field}>
              <option value="">Selecionar vínculo</option>{studentPrograms.filter(p=>p.status==="active").map(p=><option key={p.id} value={p.id}>{p.program_name}</option>)}
            </select>
            <select value={term} onChange={e=>{setTerm(e.target.value);void loadOffers(studentProgram,e.target.value);}} className={field}>
              <option value="">Selecionar período</option>{overview?.terms.filter(t=>["planned","active"].includes(t.status)).map(t=><option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
            {offers.map(o=><label key={o.id} className="flex gap-3 rounded-lg border border-[#EAECF0] p-3 text-[11px]">
              <input type="checkbox" disabled={!o.available} checked={picked.includes(o.id)} onChange={e=>setPicked(v=>e.target.checked?[...v,o.id]:v.filter(x=>x!==o.id))}/>
              <span className="flex-1">{o.subject_name} · {o.code}</span>
              <span className="text-[#85858B]">{o.available?"Disponível":"Lotada"}</span>
            </label>)}
            {canEdit&&<button className={primary} type="button" disabled={busy||!picked.length}
              onClick={async()=>{const v=await act("/enrollment-requests",{
                student_program_id:studentProgram,term_id:term,class_ids:picked});
                if(v){setPicked([]);await loadOffers(studentProgram,term);}}}>Enviar solicitação</button>}
          </div>
        </div>}
      </section>
    </div>}

    {tab==="diario"&&<section className="rounded-xl border border-[#EAECF0] bg-white p-5">
      <h2 className="text-[15px] font-semibold">Diário de classe</h2>
      <p className="mt-1 text-[12px] text-[#667085]">Notas, frequência e fechamento com rastreabilidade. Registros ausentes bloqueiam resultados.</p>
      <label className="mt-4 block max-w-xl text-[11px] text-[#667085]">Turma ativa
        <select value={classId} onChange={e=>{setClassId(e.target.value);void loadRoster(e.target.value);}} className={field+" mt-1"}>
          <option value="">Selecionar turma</option>{overview?.classes.filter(x=>x.status==="active").map(c=><option key={c.id} value={c.id}>{c.code} · {overview.subjects.find(s=>s.id===c.subject_id)?.name}</option>)}
        </select></label>
      {roster&&<div className="mt-5 grid gap-5 xl:grid-cols-2">
        <div className="rounded-lg border border-[#EAECF0] p-4">
          <h3 className="text-[13px] font-semibold">Notas por avaliação</h3>
          <select value={assessmentId} onChange={e=>{setAssessmentId(e.target.value);setGrades({});}} className={field+" mt-3"}>
            <option value="">Selecionar avaliação</option>{roster.assessments.map(a=><option key={a.id} value={a.id}>{a.title} · {a.max_score} pontos · {a.publication_status}</option>)}
          </select>
          <div className="mt-3 max-h-[350px] divide-y overflow-y-auto rounded-lg border border-[#EAECF0]">
            {roster.students.map(s=>{const original=roster.grades.find(g=>g.student_id===s.student_id&&g.assessment_id===assessmentId);
              return <label key={s.student_id} className="flex items-center justify-between gap-3 p-2.5 text-[11px]">
                <span className="min-w-0 flex-1 truncate">{s.name}{original?.publication_status==="published"?" · publicada":""}</span>
                <input aria-label={"Nota de "+s.name} type="number" min="0" step="0.01" max={assessment?.max_score||"100"}
                  placeholder={original?.score||"—"} disabled={!canEdit||original?.publication_status==="published"}
                  value={grades[s.student_id]??""} onChange={e=>setGrades(v=>({...v,[s.student_id]:e.target.value}))}
                  className={field+" w-[98px]"}/></label>})}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {canEdit&&<button className={btn} type="button" disabled={busy||assessment?.publication_status!=="published"} onClick={()=>void saveGrades()}>Salvar rascunhos</button>}
            {canApprove&&<button className={primary} type="button" disabled={busy||!assessmentId} onClick={async()=>{
              const v=await act("/classes/"+classId+"/grades/publish",{assessment_id:assessmentId});if(v)await loadRoster(classId);
            }}>Publicar todas as notas</button>}
          </div>
        </div>
        <div className="rounded-lg border border-[#EAECF0] p-4">
          <h3 className="text-[13px] font-semibold">Chamada de aula</h3>
          <select value={lessonId} onChange={e=>{setLessonId(e.target.value);setPresence({});}} className={field+" mt-3"}>
            <option value="">Selecionar aula</option>{roster.lessons.map(l=><option key={l.id} value={l.id}>{l.topic||"Aula"} · {new Date(l.starts_at).toLocaleDateString("pt-BR")} · {l.publication_status}</option>)}
          </select>
          <div className="mt-3 max-h-[350px] divide-y overflow-y-auto rounded-lg border border-[#EAECF0]">
            {roster.students.map(s=>{const prior=roster.attendance.find(a=>a.student_id===s.student_id&&a.lesson_id===lessonId);
              return <label key={s.student_id} className="flex items-center justify-between gap-3 p-2.5 text-[11px]">
                <span className="min-w-0 flex-1 truncate">{s.name}</span>
                <select className={field+" w-[142px]"} aria-label={"Frequência de "+s.name} disabled={!canEdit} value={presence[s.student_id]??""}
                  onChange={e=>setPresence(v=>({...v,[s.student_id]:e.target.value}))}>
                  <option value="">{prior?"Atual: "+prior.status:"Sem registro"}</option>
                  <option value="present">Presente</option><option value="absent">Ausente</option><option value="excused">Justificada</option>
                </select></label>})}
          </div>
          {canEdit&&<button className={btn+" mt-3"} type="button" disabled={busy||lesson?.publication_status!=="published"} onClick={()=>void saveAttendance()}>Salvar chamada</button>}
        </div>
        <div className="xl:col-span-2 rounded-lg border border-[#EAECF0] bg-[#FAFBFC] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h3 className="text-[13px] font-semibold">Verificação e fechamento</h3>
              <p className="mt-1 text-[11px] text-[#667085]">Sem fechamento enquanto houver notas, aulas ou chamadas pendentes.</p></div>
            <div className="flex gap-2">
              <button className={btn} type="button" onClick={async()=>{try{
                setPreview(await call<Preview>("/classes/"+classId+"/closing-preview"));setError("");
              }catch(e){setError((e as Error).message);}}}>Prévia do fechamento</button>
              {canApprove&&<button className={primary} type="button" disabled={busy||!preview?.ready}
                onClick={async()=>{if(!window.confirm("Encerrar a turma e publicar resultados finais?"))return;
                  const v=await act("/classes/"+classId+"/close");if(v){setPreview(null);await loadRoster(classId);}}}>Concluir turma</button>}
            </div>
          </div>
          {preview&&<div className="mt-3 text-[11px]">
            <p className={preview.ready?"font-semibold text-[#027A48]":"font-semibold text-[#B42318]"}>{preview.ready?"Registros conferidos":preview.reason}</p>
            {preview.items.map(i=><p key={i.student_id} className="mt-1 text-[#667085]">{i.name}: {i.ready?
              i.score_percent+"% nota · "+i.attendance_percent+"% presença · "+labels[i.result||""]:i.reason}</p>)}
          </div>}
        </div>
      </div>}
    </section>}

    {tab==="historico"&&<section className="max-w-4xl rounded-xl border border-[#EAECF0] bg-white p-5">
      <h2 className="text-[15px] font-semibold">Histórico acadêmico operacional</h2>
      <p className="mt-1 text-[12px] text-[#667085]">Selecione um estudante na aba Matrículas para consultar resultados finalizados.</p>
      {student&&<p className="mt-4 text-[12px] font-semibold">{student.name} · {student.registration}</p>}
      <div className="mt-3 divide-y overflow-hidden rounded-lg border border-[#EAECF0]">
        {transcript.map((t,i)=><div key={i} className="flex flex-wrap justify-between gap-3 p-3 text-[12px]">
          <div><p className="font-semibold">{t.subject_name}</p><p className="mt-1 text-[11px] text-[#667085]">
            {t.term_label} · Nota {t.grade_percent}% · Frequência {t.attendance_percent}% · Política v{t.policy_version}</p></div>
          <span className={t.result==="passed"?"text-[#027A48]":"text-[#B42318]"}>{labels[t.result]||t.result}</span>
        </div>)}
      </div>
      {!transcript.length&&<p className="mt-4 text-[12px] text-[#85858B]">Nenhum registro final disponível.</p>}
      <p className="mt-4 text-[11px] text-[#98A2B3]">A emissão de histórico oficial e os requerimentos ficam na Central de Serviços Acadêmicos. Esta consulta não é documento assinado.</p>
    </section>}
  </main>;
}
