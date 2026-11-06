"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
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
import { getVisibleNavigation, hasNavigationPermission } from "@/components/layout/navigation";
import { RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { RiskScoreTrend } from "./risk-trend";
import { RiskMovementsFeed } from "./risk-movements-feed";

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
  const [campaignIds, setCampaignIds] = useState<string[]>([]);
  const [campaignName, setCampaignName] = useState("");
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
    setCampaignIds([]);
  }, [me.data?.tenant_id, me.data?.user_id]);

  const visibleNav = useMemo(() => getVisibleNavigation(me.data), [me.data]);
  const canView = visibleNav.some(group => group.items.some(item => item.href === "/alunos"));
  const canImport = visibleNav.some(group => group.items.some(item => item.href === "/importar"));
  const canSensitive = hasNavigationPermission(me.data, "students.sensitive.view");
  const publicFields = STUDENT_FIELDS.filter(field => ["nome", "matricula", "curso"].includes(field.key));
  const exposedFields = canSensitive ? STUDENT_FIELDS : publicFields;
  const exposedViews = canSensitive ? STUDENT_VIEWS : STUDENT_VIEWS.filter(view => view.id === "todos");
  const safeView = canSensitive ? state.view : "todos";
  const safeFilters = canSensitive ? state.filters : state.filters.filter(filter =>
    ["nome", "matricula", "curso"].includes(filter.key));
  // Avoid even asking the backend for a prohibited risk sorting/count query.
  const safeSort = !canSensitive && state.sort?.key === "risk_score" ? null : state.sort;

  const sort = !safeSort ? (canSensitive ? "risk_desc" : "name_asc")
    : safeSort.key === "risk_score" ? (safeSort.desc ? "risk_desc" : "risk_asc")
    : safeSort.key === "curso" ? "course_asc" : (safeSort.desc ? "name_desc" : "name_asc");

  const canPrepareCampaign = canSensitive && hasNavigationPermission(me.data, "campaigns.create");
  const range = useMemo(() => {
    const now = new Date();
    const previous = new Date(now);
    previous.setDate(now.getDate() - 30);
    return { from: previous.toISOString().slice(0, 10), to: now.toISOString().slice(0, 10) };
  }, []);
  const movementsQuery = useQuery({
    queryKey: ["risk-movements", me.data?.tenant_id, range.from, range.to],
    queryFn: () => api.riskHistory({ from: range.from, to: range.to, page: 1, page_size: 100 }),
    enabled: canSensitive && canView,
    staleTime: 60_000, retry: false,
  });
  const movementsByStudent = useMemo(() =>
    new Map((movementsQuery.data?.movements || []).map(m => [m.student_id, m])),
    [movementsQuery.data]);
  const riskFields = useMemo(() => STUDENT_FIELDS.map(field => field.key === "risk_score"
    ? { ...field, render: (row: ObjectIndexStudent) =>
      <RiskScoreTrend score={row.risk_score} movement={movementsByStudent.get(row.id)} /> } : field),
    [movementsByStudent]);
  const simulateCampaign = useMutation({
    mutationFn: () => api.enqueueRetention({
      dry_run: true, student_ids: campaignIds, limit: campaignIds.length, campaign_name: campaignName.trim(),
    }, typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : undefined),
    onSuccess: () => {
      toast.success("Simulação de retenção solicitada. Nenhuma mensagem real será enviada.");
      setCampaignIds([]);
      setCampaignName("");
    },
    onError: (e: Error) => toast.error(e.message || "Não foi possível preparar o público."),
  });

  const query = useQuery({
    queryKey: ["object-index", "students", me.data?.tenant_id, me.data?.user_id, debouncedQuery, safeView, safeFilters, sort, state.pageIndex, state.pageSize],
    queryFn: () => listStudentIndex({
      limit: state.pageSize, offset: state.pageIndex * state.pageSize,
      q: debouncedQuery.trim() || undefined,
      view: safeView,
      filters: safeFilters,
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
        description={canSensitive ? "Explore registros institucionais, classificação e acompanhamento com dados verificados." : "Registros institucionais autorizados para este perfil."}
        fields={canSensitive ? riskFields : exposedFields} rows={query.data?.students || []}
        state={canSensitive ? state : {
          ...state, view: safeView, filters: safeFilters, sort: safeSort,
          columns: state.columns.filter(key => publicFields.some(field => field.key === key)),
        }}
        onStateChange={setState}
        defaultViews={exposedViews} remote
        total={query.data?.total}
        loading={query.isLoading}
        error={query.isError}
        onRetry={() => void query.refetch()}
        onRefresh={() => void query.refetch()}
        refreshing={query.isFetching}
        onOpen={row => setSelectedId(row.id)}
        selectionActions={canPrepareCampaign ? rows => <Button size="sm" variant="primary" onClick={() => {
          setCampaignIds([...new Set(rows.map(row => row.id))]);
          setCampaignName("");
        }}>Preparar retenção ({rows.length})</Button> : undefined}
        emptyAction={state.query || state.filters.length
          ? <button type="button" className="text-[12px] font-medium text-[var(--color-blue)] hover:underline"
              onClick={() => setState(initialObjectIndexState(STUDENT_FIELDS))}>Limpar busca e filtros</button>
          : canImport ? <Link href="/importar" className="text-[12px] font-medium text-[var(--color-blue)] hover:underline">Importar alunos</Link> : null}
        actions={<div className="flex items-center gap-2">
          <Link href="/alunos/grupos" className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 text-[12px] font-medium text-[var(--color-ink)] hover:bg-[var(--color-panel)]">
            <Users className="h-3.5 w-3.5" /> Grupos
          </Link>
          {canImport && <Link href="/importar" className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-ink)] px-3 text-[12px] font-medium text-white hover:bg-[var(--color-ink-900)]">
            <Upload className="h-3.5 w-3.5" /> Importar
          </Link>}
        </div>}
        extra={<>
          {canSensitive && <RiskMovementsFeed movements={movementsQuery.data?.movements || []}
            loading={movementsQuery.isLoading} unavailable={movementsQuery.isError}
            truncated={Boolean(movementsQuery.data?.movements_truncated || movementsQuery.data?.temporal_data_truncated)}
            onOpen={setSelectedId} />}
          {groupId && !validGroup && <p role="alert" className="p-3 text-[12px] text-[var(--color-red)]">O grupo indicado não foi reconhecido.</p>}
        </>}
      />
    </main>
    <StudentDrawer studentId={selectedId} onClose={() => setSelectedId(null)} />
    <Dialog open={campaignIds.length > 0}
      onOpenChange={open => { if (!open && !simulateCampaign.isPending) setCampaignIds([]); }}
      title="Preparar ação de retenção"
      description="Seleção limitada aos registros desta página. Esta operação é uma simulação, não uma autorização de disparo.">
      <form className="space-y-4" onSubmit={event => {
        event.preventDefault();
        if (canPrepareCampaign && campaignIds.length && campaignName.trim().length >= 3) simulateCampaign.mutate();
      }}>
        <p className="text-[13px] text-[var(--color-slate-600)]">{campaignIds.length} aluno(s) selecionado(s). As regras de consentimento, elegibilidade e canais continuam no servidor.</p>
        <label className="block text-[12px] font-medium text-[var(--color-ink)]">Nome de referência
          <input value={campaignName} onChange={event => setCampaignName(event.target.value)}
            minLength={3} maxLength={100} placeholder="Ex.: Acompanhamento de novembro" required
            className="mt-1 h-10 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-canvas)] px-3 text-[13px] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]" />
        </label>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" disabled={simulateCampaign.isPending} onClick={() => setCampaignIds([])}>Cancelar</Button>
          <Button type="submit" variant="primary" disabled={!canPrepareCampaign || simulateCampaign.isPending || campaignName.trim().length < 3}>
            {simulateCampaign.isPending ? "Preparando…" : "Simular campanha sem envio"}
          </Button>
        </div>
      </form>
    </Dialog>
  </>;
}
