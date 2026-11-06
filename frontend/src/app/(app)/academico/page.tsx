"use client";

import { AcademicCatalogTable } from "@/components/academic/academic-catalog-table";
import { AcademicNavigation } from "@/components/academic/academic-navigation";

import { useCallback, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2, Loader2,
  Plus, ShieldCheck, X,
} from "@/components/ui/icons";
import { Dialog } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { ObjectIndex, initialObjectIndexState } from "@/components/object-index/object-index";
import type { ObjectField } from "@/components/object-index/object-index-types";
import { getAccessToken } from "@/lib/auth";

type Item = { id: string; name?: string; code?: string; display_name?: string; label?: string; status: string; program_id?: string; subject_id?: string; term_id?: string; teacher_id?: string };
type Overview = {
  backend: string; counts: Record<string, number>; programs: Item[];
  subjects: Item[]; teachers: Item[]; terms: Item[]; classes: Item[];
  preview_limited: boolean;
};
const CLASS_FIELDS: ObjectField<Item>[] = [
  { key: "code", title: "Turma", type: "identifier", primary: true, width: 160,
    getValue: row => row.code, sortable: true, filterable: true },
  { key: "subject_id", title: "Disciplina", type: "reference", width: 210,
    getValue: row => row.subject_id, filterable: true },
  { key: "term_id", title: "Período", type: "reference", width: 180,
    getValue: row => row.term_id, filterable: true },
  { key: "teacher_id", title: "Docente", type: "reference", width: 190,
    getValue: row => row.teacher_id },
  { key: "status", title: "Estado", type: "status", width: 130,
    getValue: row => row.status, filterable: true },
];

type Draft = { id: string; resource: string; title: string; class_id: string | null };
type Field = { key: string; label: string; type?: "date" | "datetime-local" | "number"; options?: Item[]; required?: boolean };
type NewKind = "program" | "subject" | "teacher" | "term" | "class" | "lesson" | "assessment" | "calendar_event";

async function staffRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  if (!token) throw new Error("Faça login na conta institucional.");
  const response = await fetch("/api/v1/native-academic/catalog" + path, {
    ...init, cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    let message = response.status === 503
      ? "Gestão acadêmica ainda está em homologação."
      : response.status === 403 ? "Sua conta não tem acesso à operação." : "Não foi possível executar a operação.";
    if (response.status === 409) message = "Código ou vínculo já existe. Confira os dados e tente novamente.";
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
const counts: { key: string; title: string; detail: string }[] = [
  { key: "programs", title: "Cursos", detail: "Programas cadastrados" },
  { key: "subjects", title: "Disciplinas", detail: "Unidades curriculares" },
  { key: "teachers", title: "Professores", detail: "Equipe docente" },
  { key: "classes", title: "Turmas", detail: "Oferta por período" },
  { key: "lessons", title: "Aulas", detail: "Encontros de ensino" },
  { key: "assessments", title: "Avaliações", detail: "Atividades avaliativas" },
  { key: "attendance", title: "Chamadas", detail: "Lançamentos de presença" },
  { key: "grades", title: "Notas", detail: "Registros por avaliação" },
];
const kindLabels: Record<NewKind, string> = {
  program: "Curso", subject: "Disciplina", teacher: "Professor", term: "Período",
  class: "Turma", lesson: "Aula", assessment: "Avaliação", calendar_event: "Evento",
};
const keys: Record<NewKind, string> = {
  program: "programs", subject: "subjects", teacher: "teachers", term: "terms",
  class: "classes", lesson: "lessons", assessment: "assessments", calendar_event: "calendar_events",
};
function pretty(item: Item): string {
  return item.name || item.display_name || item.label || item.code || item.id;
}
function fieldsFor(kind: NewKind, data: Overview): Field[] {
  const p = (key: string, label: string): Field => ({ key, label, required: true });
  const select = (key: string, label: string, options: Item[]): Field => ({ key, label, options, required: true });
  const term: Field[] = [p("code", "Código do período"), p("label", "Nome do período"),
    { ...p("starts_on", "Data inicial"), type: "date" },
    { ...p("ends_on", "Data final"), type: "date" }];
  const range: Field[] = [
    { ...p("starts_at", "Início"), type: "datetime-local" },
    { ...p("ends_at", "Fim"), type: "datetime-local" },
  ];
  switch (kind) {
    case "program": return [p("code", "Código do curso"), p("name", "Nome do curso"), {key:"modality",label:"Modalidade"}];
    case "subject": return [
      select("program_id", "Curso vinculado", data.programs),
      p("code", "Código da disciplina"), p("name", "Nome da disciplina"),
      {key:"credit_hours",label:"Carga horária",type:"number"},
    ];
    case "teacher": return [p("staff_code", "Código docente"), p("display_name", "Nome do professor"),
      {key:"department",label:"Departamento"}];
    case "term": return term;
    case "class": return [select("subject_id", "Disciplina", data.subjects), select("term_id", "Período", data.terms),
      {key:"teacher_id",label:"Professor responsável (opcional)",options:data.teachers},
      p("code", "Código da turma"), {key:"campus",label:"Unidade/campus"}];
    case "lesson": return [select("class_id", "Turma", data.classes), ...range,
      {key:"topic",label:"Tema da aula"}, {key:"room",label:"Sala ou link"}];
    case "assessment": return [select("class_id", "Turma", data.classes),
      p("code", "Código da avaliação"), p("title", "Título"),
      {...p("max_score", "Pontuação máxima"),type:"number"}];
    case "calendar_event": return [select("term_id", "Período", data.terms),
      p("title", "Título do evento"), ...range, {key:"location",label:"Local"}];
  }
}

export default function AcademicManagementPage() {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, staleTime: 60_000, retry: false });
  const canView = me.data?.operation_profile === "institution" &&
    (me.data.permissions ? me.data.permissions.includes("students.sensitive.view")
      : ["admin","coordinator"].includes(me.data.role || ""));
  const canCreate = canView && (me.data?.permissions
    ? me.data.permissions.includes("settings.manage") && me.data.permissions.includes("students.edit")
    : me.data?.role === "admin");
  const canPublish = canCreate && (me.data?.permissions
    ? me.data.permissions.includes("critical.manage") : me.data?.role === "admin");

  const overview = useQuery({
    queryKey: ["native-academic", me.data?.tenant_id, me.data?.user_id, "catalog-overview"],
    queryFn: () => staffRequest<Overview>("/overview"),
    enabled: !!canView, retry: false,
  });
  const drafts = useQuery({
    queryKey: ["native-academic", me.data?.tenant_id, me.data?.user_id, "drafts"],
    queryFn: () => staffRequest<{ items: Draft[] }>("/drafts"),
    enabled: !!canView && !!canPublish, retry: false,
  });
  const [kind, setKind] = useState<NewKind | null>(null);
  const [form, setForm] = useState<Record<string,string>>({});
  const [feedback, setFeedback] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [classIndexState, setClassIndexState] = useState(() => initialObjectIndexState(CLASS_FIELDS));

  const [selection, setSelection] = useState<{ id: string; tenant: string; user: string } | null>(null);
  const selectedClass = selection && selection.tenant === me.data?.tenant_id && selection.user === me.data?.user_id
    ? overview.data?.classes.find(row => row.id === selection.id)
    : undefined;
  const closeRecord = useCallback((open: boolean) => {
    if (!open) setSelection(null);
  }, []);

  const create = useMutation({
    mutationFn: async ({type, fields}: {type: NewKind; fields:Record<string,string>}) => {
      const fieldsWithoutEmpty = Object.fromEntries(
        Object.entries(fields).filter(([,value]) => value.trim() !== "")
      ) as Record<string,unknown>;
      if (type === "subject" && fieldsWithoutEmpty.credit_hours) {
        fieldsWithoutEmpty.credit_hours = Number(fieldsWithoutEmpty.credit_hours);
      }
      if (type === "assessment") fieldsWithoutEmpty.max_score = Number(fieldsWithoutEmpty.max_score);
      if (type === "lesson" || type === "calendar_event") {
        for (const key of ["starts_at", "ends_at"]) {
          if (typeof fieldsWithoutEmpty[key] === "string") {
            const parsed = new Date(fieldsWithoutEmpty[key] as string);
            if (Number.isNaN(parsed.getTime())) throw new Error("Data e hora inválidas.");
            fieldsWithoutEmpty[key] = parsed.toISOString();
          }
        }
      }
      if (type === "calendar_event") fieldsWithoutEmpty.scope = "institution";
      const body = { [keys[type]]: [fieldsWithoutEmpty] };
      return staffRequest("/batch", { method: "POST", body: JSON.stringify(body) });
    },
    onSuccess: () => {
      setKind(null); setForm({}); setFailed(null);
      setFeedback("Registro criado como rascunho. Nenhuma mensagem foi enviada.");
      void queryClient.invalidateQueries({ queryKey: ["native-academic"] });
    },
    onError: (error: Error) => setFailed(error.message),
  });

  const publish = useMutation({
    mutationFn: (draft: Draft) =>
      staffRequest("/" + draft.resource + "/" + encodeURIComponent(draft.id) + "/publish", {method:"POST"}),
    onSuccess: () => {
      setFeedback("Registro publicado. Agora está disponível nas consultas autorizadas.");
      void queryClient.invalidateQueries({ queryKey: ["native-academic"] });
    },
    onError: (error: Error) => setFailed(error.message),
  });

  const possible = useMemo(() => (
    overview.data ? fieldsFor(kind || "program", overview.data) : []
  ), [kind, overview.data]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (kind && canCreate) create.mutate({type:kind,fields:form});
  }
  if (me.isLoading) return <main className="p-10 text-[13px] text-[#667085]">Verificando acesso…</main>;
  if (!canView) return <main className="p-10 text-[13px] text-[#667085]">
    Esta área é exclusiva de instituições de ensino com acesso acadêmico autorizado.
  </main>;

  return <main className="mx-auto max-w-[1370px] space-y-6 px-5 pb-16 pt-8 md:px-10">
    <AcademicNavigation features={me.data?.available_features} />
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#98A2B3]">OPERAÇÃO ACADÊMICA · MIRA</p>
        <h1 className="mt-3 text-[27px] font-semibold tracking-[-0.04em] text-[#101828]">Gestão acadêmica</h1>
        <p className="mt-2 text-[13px] text-[#667085]">
          Cursos, disciplinas, docentes, turmas, aulas, calendário e histórico para o Portal do Aluno.
        </p>
      </div>
      <span className="inline-flex items-center gap-2 rounded-lg border border-[#E4E7EC] bg-white px-3 py-2 text-[11px] font-semibold text-[#667085]">
        <ShieldCheck className="h-4 w-4 text-[#2563EB]"/> Permissões institucionais
      </span>
    </header>

    <div className="rounded-lg border border-[#DCE8FF] bg-[#F5F8FF] px-4 py-3 text-[11px] leading-5 text-[#475467]">
      O módulo acadêmico é independente de Frappe/ERPNext. Dados de alunos continuam isolados por instituição.
      A publicação de notas, aulas e eventos exige aprovação. Sem cobrança ou envio automático.
    </div>

    {feedback && <div role="status" className="flex items-center gap-2 rounded-lg border border-[#D1FADF] bg-[#ECFDF3] px-4 py-3 text-[12px] text-[#067647]">
      <CheckCircle2 className="h-4 w-4"/> {feedback}
    </div>}
    {failed && <div role="alert" className="rounded-lg border border-[#FECDCA] bg-[#FFF5F5] px-4 py-3 text-[12px] text-[#B42318]">{failed}</div>}

    {overview.isLoading && <div className="flex items-center gap-2 rounded-lg border border-[#E4E7EC] bg-white p-7 text-[12px] text-[#667085]">
      <Loader2 className="h-4 w-4 animate-spin"/> Consultando o catálogo acadêmico…
    </div>}
    {overview.isError && <section className="rounded-xl border border-[#E4E7EC] bg-white p-7">
      <h2 className="text-[16px] font-semibold">Catálogo indisponível</h2>
      <p className="mt-2 max-w-xl text-[12px] leading-6 text-[#667085]">
        O módulo ainda está desabilitado ou não foi homologado com o banco de dados.
        Nenhum registro é exibido como se já estivesse sincronizado.
      </p>
    </section>}

    {overview.data && <>
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {counts.map(item => <article key={item.key} className="rounded-xl border border-[#E4E7EC] bg-white p-5">
          <p className="text-[12px] text-[#667085]">{item.title}</p>
          <p className="mt-4 text-[29px] font-semibold tracking-[-0.05em] text-[#101828]">
            {overview.data!.counts[item.key] ?? "—"}
          </p>
          <p className="mt-2 text-[11px] text-[#98A2B3]">{item.detail}</p>
        </article>)}
      </section>
      <ObjectIndex objectKey="academic_classes"
        title="Turmas"
        description="Índice de turmas da prévia oficial do catálogo acadêmico."
        fields={CLASS_FIELDS.map(field => {
          if (field.key === "subject_id") return {
            ...field,
            render: (row: Item) => {
              const item = overview.data!.subjects.find(value => value.id === row.subject_id);
              return <span className="block truncate">{item ? pretty(item) : row.subject_id ? "Referência não carregada" : "—"}</span>;
            },
          };
          if (field.key === "term_id") return {
            ...field,
            render: (row: Item) => {
              const item = overview.data!.terms.find(value => value.id === row.term_id);
              return <span className="block truncate">{item ? pretty(item) : row.term_id ? "Referência não carregada" : "—"}</span>;
            },
          };
          if (field.key === "teacher_id") return {
            ...field,
            render: (row: Item) => {
              const item = overview.data!.teachers.find(value => value.id === row.teacher_id);
              return <span className="block truncate">{item ? pretty(item) : row.teacher_id ? "Referência não carregada" : "—"}</span>;
            },
          };
          return field;
        })}
        rows={overview.data.classes} state={classIndexState} onStateChange={setClassIndexState}
        onOpen={row => {
          if (me.data?.tenant_id && me.data.user_id) {
            setSelection({ id: row.id, tenant: me.data.tenant_id, user: me.data.user_id });
          }
        }}
        total={overview.data.counts.classes}
        partial={overview.data.counts.classes > overview.data.classes.length}
        defaultViews={[
          { id: "todos", title: "Todas" },
          { id: "active", title: "Ativas", filterKey: "status:active" },
        ]}
        onRefresh={() => void overview.refetch()} refreshing={overview.isFetching}
        emptyTitle="Nenhuma turma foi carregada do catálogo acadêmico."
      />

      {selectedClass && <Dialog open onOpenChange={closeRecord}
        title={`Turma ${pretty(selectedClass)}`} description="Vínculos no catálogo acadêmico">
        <dl className="grid gap-4 sm:grid-cols-2">
          {([
            ["Disciplina", selectedClass.subject_id, overview.data.subjects],
            ["Período", selectedClass.term_id, overview.data.terms],
            ["Professor", selectedClass.teacher_id, overview.data.teachers],
          ] as const).map(([label, id, options]) => {
            const item = options.find(option => option.id === id);
            return <div key={label}>
              <dt className="text-xs text-[#505967]">{label}</dt>
              <dd className="mt-1 text-sm font-medium">{item ? pretty(item) : id ? "Referência fora da prévia" : "Sem vínculo"}</dd>
            </div>;
          })}
          <div>
            <dt className="text-xs text-[#505967]">Estado</dt>
            <dd className="mt-1 text-sm font-medium">{selectedClass.status}</dd>
          </div>
        </dl>
      </Dialog>}

      <div className="grid gap-5 lg:grid-cols-[1fr_370px]">
        <section className="space-y-5">
          <AcademicCatalogTable key={`${me.data?.tenant_id}:${me.data?.user_id}:programs`}
            title="Cursos" records={overview.data.programs} total={overview.data.counts.programs} />
          <AcademicCatalogTable key={`${me.data?.tenant_id}:${me.data?.user_id}:subjects`}
            title="Disciplinas" records={overview.data.subjects} total={overview.data.counts.subjects} />
          <AcademicCatalogTable key={`${me.data?.tenant_id}:${me.data?.user_id}:teachers`}
            title="Professores" records={overview.data.teachers} total={overview.data.counts.teachers} />
          <AcademicCatalogTable key={`${me.data?.tenant_id}:${me.data?.user_id}:terms`}
            title="Períodos letivos" records={overview.data.terms} total={overview.data.counts.terms} />
          {canPublish && <div className="rounded-xl border border-[#E4E7EC] bg-white p-5">
            <h2 className="text-[14px] font-semibold">Publicações pendentes</h2>
            <p className="mt-1 text-[11px] text-[#98A2B3]">Aulas, eventos, avaliações e notas exigem aprovação explícita.</p>
            {drafts.isLoading && <p className="py-4 text-[11px] text-[#667085]">Carregando aprovações…</p>}
            {drafts.data?.items.length === 0 && <p className="mt-4 rounded-lg bg-[#F9FAFB] px-4 py-3 text-[12px] text-[#667085]">Nenhum registro aguardando publicação.</p>}
            <ul className="mt-4 divide-y divide-[#EAECF0]">
              {drafts.data?.items.slice(0, 30).map(item => <li key={item.resource + item.id} className="flex items-center justify-between gap-3 py-3">
                <div><p className="text-[12px] font-medium">{item.title}</p>
                  <p className="mt-1 text-[10px] text-[#98A2B3]">{item.resource} · Rascunho</p></div>
                <button type="button" disabled={publish.isPending}
                  onClick={() => {setFailed(null); publish.mutate(item);}}
                  className="rounded-md border border-[#D0D5DD] px-3 py-2 text-[11px] font-semibold text-[#344054] hover:bg-[#F9FAFB] disabled:opacity-40">
                  Publicar
                </button>
              </li>)}
            </ul>
          </div>}
        </section>

        <section className="self-start rounded-xl border border-[#E4E7EC] bg-white p-5">
          <div className="flex items-center gap-2"><Plus className="h-4 w-4 text-[#2563EB]"/>
            <h2 className="text-[14px] font-semibold">Novo registro</h2></div>
          <p className="mt-2 text-[11px] leading-5 text-[#667085]">
            Cadastre a estrutura inicial. Registros de aulas, eventos e avaliações começam como rascunho.
          </p>
          {canCreate ? <>
            {!kind && <div className="mt-5 grid grid-cols-2 gap-2">
              {(Object.entries(kindLabels) as [NewKind,string][]).map(([id,label]) =>
                <button key={id} type="button" onClick={() => {setKind(id);setForm({});setFailed(null);}}
                  className="flex h-11 items-center justify-between gap-2 rounded-lg border border-[#E4E7EC] px-3 text-left text-[11px] font-semibold text-[#344054] hover:border-[#9CC0FF] hover:bg-[#F5F8FF]">
                  {label}<Plus className="h-3 w-3 text-[#98A2B3]"/>
                </button>)}
            </div>}
            {kind && <form onSubmit={onSubmit} className="mt-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-[13px] font-semibold">Criar {kindLabels[kind].toLowerCase()}</h3>
                <button type="button" aria-label="Cancelar" onClick={() => {setKind(null);setForm({});}}
                  className="text-[#667085]"><X className="h-4 w-4"/></button>
              </div>
              {possible.map(field => <div key={field.key}>
                <label htmlFor={"catalog-" + field.key} className="mb-1.5 block text-[11px] font-semibold text-[#475467]">{field.label}</label>
                {field.options ?
                  <select id={"catalog-" + field.key} required={field.required}
                    value={form[field.key] || ""} onChange={e => setForm(v=>({...v,[field.key]:e.target.value}))}
                    className="h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-2 text-[12px]">
                    <option value="">Selecionar</option>
                    {field.options.map(item => <option key={item.id} value={item.id}>{pretty(item)}</option>)}
                  </select> :
                  <input id={"catalog-" + field.key} required={field.required} type={field.type || "text"}
                    value={form[field.key] || ""} onChange={e=>setForm(v=>({...v,[field.key]:e.target.value}))}
                    className="h-10 w-full rounded-lg border border-[#D0D5DD] px-3 text-[12px] outline-none focus:border-[#2563EB]"/>
                }
              </div>)}
              <button type="submit" disabled={create.isPending}
                className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-[#101828] text-[12px] font-semibold text-white disabled:opacity-40">
                {create.isPending ? "Salvando…" : "Criar registro"} <Plus className="h-3.5 w-3.5"/>
              </button>
            </form>}
          </> : <div className="mt-5 rounded-lg bg-[#F9FAFB] p-4 text-[11px] text-[#667085]">
            A sua função pode visualizar o catálogo, mas não criar ou aprovar registros.
          </div>}
        </section>
      </div>
      {overview.data.preview_limited && <p className="text-[11px] text-[#667085]">
        A prévia mostra um número limitado de registros. Os totais representam a base institucional completa.
      </p>}
    </>}
  </main>;
}
