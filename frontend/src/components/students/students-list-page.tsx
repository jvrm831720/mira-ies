"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Upload, Users } from "@/components/ui/icons";
import { StudentDrawer } from "@/components/students/student-drawer";
import {
  followUpLabel, formatDate, initials, KNOWN_GROUP_IDS,
} from "@/components/students/students-list-helpers";
import {
  ObjectIndex, initialObjectIndexState, type ObjectIndexState,
} from "@/components/object-index/object-index";
import type { ObjectField, ObjectDefaultView } from "@/components/object-index/object-index-types";
import { listStudentIndex, type ObjectIndexStudent } from "@/lib/object-index-api";
import { api } from "@/lib/api";
import { getVisibleNavigation } from "@/components/layout/navigation";
import { RiskBadge } from "@/components/ui/badge";

const STUDENT_VIEWS: ObjectDefaultView[] = [
  { id: "todos", title: "Todos" },
  { id: "risco", title: "Risco elevado" },
  { id: "sem_classificacao", title: "Sem classificação" },
  { id: "dados_insuficientes", title: "Dados insuficientes" },
  { id: "acompanhamento", title: "Em acompanhamento" },
];

const STUDENT_FIELDS: ObjectField<ObjectIndexStudent>[] = [
  {
    key: "nome", title: "Aluno", type: "person", primary: true, sortable: true,
    filterable: true, width: 290, getValue: row => row.nome,
    render: row => <span className="flex min-w-0 items-center gap-2.5">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-[var(--radius-md)] bg-[var(--color-panel)] text-[10px] font-semibold text-[var(--color-slate-600)]">
        {initials(row.nome)}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[12px] font-semibold text-[var(--color-ink)]">{row.nome || "Sem nome"}</span>
        <span className="block truncate text-[10px] font-normal text-[var(--color-muted)]">{row.matricula || "Matrícula não informada"}</span>
      </span>
    </span>,
  },
  { key: "matricula", title: "Matrícula", type: "identifier", getValue: row => row.matricula,
    width: 140, filterable: true, nullLabel: "Não informado" },
  { key: "curso", title: "Curso", type: "text", getValue: row => row.curso,
    width: 180, filterable: true, sortable: true },
  { key: "risk_level", title: "Classificação", type: "status", getValue: row => row.risk_level,
    width: 140, filterable: true, options: [
      { value: "critico", label: "Crítico" }, { value: "medio", label: "Moderado" }, { value: "baixo", label: "Baixo" },
    ], render: row => row.risk_level ? <RiskBadge level={row.risk_level} />
      : <span className="mira-tag border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-slate-600)]">Sem classificação</span> },
  { key: "risk_score", title: "Score", type: "number", width: 100, sortable: true,
    getValue: row => row.risk_score, filterable: true,
    render: row => <span className="font-mono text-[12px] tabular-nums">
      {typeof row.risk_score === "number" && Number.isFinite(row.risk_score) ? Math.round(row.risk_score) : "—"}
    </span> },
  { key: "follow_up", title: "Acompanhamento", type: "text", width: 185,
    getValue: row => row.follow_up?.status || null,
    render: row => <span className="block truncate text-[11px]">
      {followUpLabel(row.follow_up?.status)}
      {row.follow_up?.created_at && <span className="block text-[10px] text-[var(--color-muted)]">{formatDate(row.follow_up.created_at)}</span>}
    </span> },
];

function parseInitialState(searchParams: ReturnType<typeof useSearchParams>): ObjectIndexState {
  const requested = searchParams.get("tab") || "todos";
  const tab = STUDENT_VIEWS.some(view => view.id === requested) ? requested : "todos";
  const state = initialObjectIndexState(STUDENT_FIELDS, tab);
  const q = searchParams.get("q") || "";
  state.query = q.slice(0, 160);
  const risk = searchParams.get("risk");
  if (risk && ["critico", "medio", "baixo"].includes(risk)) {
    state.filters = [{ key: "risk_level", op: "eq", value: risk }];
  }
  return state;
}

export function StudentsListPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [state, setState] = useState(() => parseInitialState(searchParams));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [debouncedQuery, setDebouncedQuery] = useState(state.query);
  const groupId = searchParams.get("group") || "";
  const validGroup = KNOWN_GROUP_IDS.has(groupId) ? groupId : "";

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(state.query), 240);
    return () => window.clearTimeout(timer);
  }, [state.query]);

  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  useEffect(() => {
    setSelectedId(null);
  }, [me.data?.tenant_id, me.data?.user_id]);

  const visibleNav = useMemo(() => getVisibleNavigation(me.data), [me.data]);
  const canView = visibleNav.some(group => group.items.some(item => item.href === "/alunos"));
  const canImport = visibleNav.some(group => group.items.some(item => item.href === "/importar"));

  const sort = !state.sort ? "risk_desc"
    : state.sort.key === "risk_score" ? (state.sort.desc ? "risk_desc" : "risk_asc")
    : state.sort.key === "curso" ? "course_asc" : (state.sort.desc ? "name_desc" : "name_asc");

  const query = useQuery({
    queryKey: ["object-index", "students", me.data?.tenant_id, me.data?.user_id, debouncedQuery, state.view, state.filters, sort, state.pageIndex, state.pageSize],
    queryFn: () => listStudentIndex({
      limit: state.pageSize, offset: state.pageIndex * state.pageSize,
      q: debouncedQuery.trim() || undefined,
      view: state.view,
      filters: state.filters,
      sort,
    }),
    enabled: canView && !validGroup,
    staleTime: 20_000, retry: false,
  });
  // The group detail page uses the authoritative cursor-based member API.
  // Redirect instead of intersecting two unrelated partial samples.
  useEffect(() => {
    if (validGroup) router.replace("/alunos/grupos/" + encodeURIComponent(validGroup));
  }, [router, validGroup]);

  if (validGroup) return <main role="status" className="mira-page p-8 text-[13px] text-[var(--color-slate-600)]">Abrindo o grupo completo de alunos…</main>;
  if (me.isLoading) return <main className="p-8 text-[13px] text-[var(--color-slate-600)]" role="status">Carregando permissões…</main>;
  if (me.isError || !canView) return <main role="alert" className="mira-page p-8 text-[13px]">
    Não foi possível confirmar a autorização para consultar os alunos.
  </main>;

  return <>
    <main className="mira-page min-h-dvh">
      <ObjectIndex objectKey="students" title="Alunos"
        description="Explore registros institucionais, classificação e acompanhamento com dados verificados."
        fields={STUDENT_FIELDS} rows={query.data?.students || []} state={state} onStateChange={setState}
        defaultViews={STUDENT_VIEWS} remote
        total={query.data?.total}
        loading={query.isLoading}
        error={query.isError}
        onRetry={() => void query.refetch()}
        onRefresh={() => void query.refetch()}
        refreshing={query.isFetching}
        onOpen={row => setSelectedId(row.id)}
        actions={<div className="flex items-center gap-2">
          <Link href="/alunos/grupos" className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 text-[12px] font-medium text-[var(--color-ink)] hover:bg-[var(--color-panel)]">
            <Users className="h-3.5 w-3.5" /> Grupos
          </Link>
          {canImport && <Link href="/importar" className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-ink)] px-3 text-[12px] font-medium text-white hover:bg-[var(--color-ink-900)]">
            <Upload className="h-3.5 w-3.5" /> Importar
          </Link>}
        </div>}
        extra={groupId && !validGroup ? <p role="alert" className="p-3 text-[12px] text-[var(--color-red)]">O grupo indicado não foi reconhecido.</p> : null}
      />
    </main>
    <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
  </>;
}
