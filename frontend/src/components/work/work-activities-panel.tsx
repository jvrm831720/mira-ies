"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  FileText,
  History,
  Loader2,
  Play,
  RotateCcw,
  UserPlus,
  XCircle,
} from "lucide-react";
import { workApi } from "@/lib/work-api";
import { api } from "@/lib/api";
import type {
  CreateFromLogDraft,
  WorkActivity,
  WorkActivityStatus,
  WorkResultKind,
} from "@/types/work";
import type { InterventionLog } from "@/types/api";
import { cn } from "@/lib/utils";
import { RiskBadge } from "@/components/ui/badge";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

const STATUS_LABEL: Record<string, string> = {
  open: "Aberta",
  in_progress: "Em andamento",
  completed: "Concluída",
  cancelled: "Cancelada",
};

const TYPE_LABEL: Record<string, string> = {
  follow_up: "Follow-up",
  contact: "Contato",
  review: "Revisão",
  other: "Outro",
};

const PRIORITY_LABEL: Record<string, string> = {
  low: "Baixa",
  normal: "Normal",
  high: "Alta",
  urgent: "Urgente",
};

const ORIGIN_LABEL: Record<string, string> = {
  manual: "Equipe",
  campaign: "Campanha",
};

const EVENT_LABEL: Record<string, string> = {
  created: "Criação",
  assignee_changed: "Responsável",
  due_changed: "Prazo",
  status_changed: "Status",
  completed: "Conclusão",
  cancelled: "Cancelamento",
  result_recorded: "Resultado operacional",
  priority_changed: "Prioridade",
  details_changed: "Detalhes",
  relations_changed: "Vínculos",
};

const RESULT_KIND_LABEL: Record<WorkResultKind, string> = {
  done: "Concluída",
  unreachable: "Não conseguiu contato",
  deferred: "Adiada",
  referred: "Encaminhada",
};

const CHANNEL_LABEL: Record<string, string> = {
  whatsapp: "WhatsApp",
  email: "E-mail",
  sms: "SMS",
};

type Props = {
  createDraft?: CreateFromLogDraft | null;
  onDraftConsumed?: () => void;
};

export function WorkActivitiesPanel({ createDraft = null, onDraftConsumed }: Props) {
  const qc = useQueryClient();
  const [view, setView] = useState<"all" | "mine" | "overdue">("all");
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [originFilter, setOriginFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [activityType, setActivityType] = useState("follow_up");
  const [createPriority, setCreatePriority] = useState("normal");
  const [assigneeId, setAssigneeId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [linkStudentId, setLinkStudentId] = useState<string | null>(null);
  const [linkLogId, setLinkLogId] = useState<string | null>(null);
  const [draftMeta, setDraftMeta] = useState<CreateFromLogDraft | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [resultNote, setResultNote] = useState("");
  const [resultKind, setResultKind] = useState<WorkResultKind | "">("");
  const [resultError, setResultError] = useState<string | null>(null);

  const members = useQuery({
    queryKey: ["org-members", "work"],
    queryFn: () => api.listMembers(),
    retry: false,
  });

  const summaryQuery = useQuery({
    queryKey: ["work-activity-summary"],
    queryFn: () => workApi.summary(),
    retry: false,
  });

  const listParams = useMemo(() => {
    const params: {
      assignee?: string;
      status?: string;
      origin_type?: string;
      priority?: string;
      overdue_only?: boolean;
      limit: number;
    } = { limit: 100 };
    if (view === "mine") params.assignee = "me";
    else if (view === "overdue") params.overdue_only = true;
    else if (assigneeFilter === "unassigned") params.assignee = "unassigned";
    else if (assigneeFilter) params.assignee = assigneeFilter;
    if (statusFilter) params.status = statusFilter;
    if (originFilter) params.origin_type = originFilter;
    if (priorityFilter) params.priority = priorityFilter;
    return params;
  }, [view, assigneeFilter, statusFilter, originFilter, priorityFilter]);

  const activitiesQuery = useQuery({
    queryKey: ["work-activities", listParams],
    queryFn: () =>
      view === "mine" && !statusFilter && !originFilter && !priorityFilter
        ? workApi.mine(100)
        : workApi.list(listParams),
    retry: false,
  });

  const listedActivity = useMemo(
    () => (activitiesQuery.data?.activities ?? []).find((a) => a.id === selectedId) ?? null,
    [activitiesQuery.data?.activities, selectedId]
  );

  const selectedActivityQuery = useQuery({
    queryKey: ["work-activity", selectedId],
    queryFn: () => workApi.get(selectedId!),
    enabled: Boolean(selectedId && !listedActivity),
    retry: false,
  });
  const selectedActivity = listedActivity ?? selectedActivityQuery.data ?? null;

  const eventsQuery = useQuery({
    queryKey: ["work-activity-events", selectedId],
    queryFn: () => workApi.events(selectedId!),
    enabled: Boolean(selectedId),
    retry: false,
  });

  const studentQuery = useQuery({
    queryKey: ["student-risk", selectedActivity?.student_id],
    queryFn: () => api.studentRisk(selectedActivity!.student_id!),
    enabled: Boolean(selectedActivity?.student_id),
    retry: false,
  });

  const relatedLogQuery = useQuery({
    queryKey: [
      "intervention-log-for-activity",
      selectedActivity?.intervention_log_id,
      selectedActivity?.student_id,
    ],
    queryFn: async () => {
      const logId = selectedActivity!.intervention_log_id!;
      const studentId = selectedActivity?.student_id;
      if (studentId) {
        const res = await api.retentionLogs({ student_id: studentId, limit: 50 });
        const found = res.logs?.find((l) => l.id === logId);
        if (found) return found;
      }
      const res = await api.retentionLogs({ limit: 100 });
      return res.logs?.find((l) => l.id === logId) ?? null;
    },
    enabled: Boolean(selectedActivity?.intervention_log_id),
    retry: false,
  });

  useEffect(() => {
    const activityId = new URLSearchParams(window.location.search).get("activity");
    if (activityId) setSelectedId(activityId);
  }, []);

  useEffect(() => {
    if (!createDraft) return;
    setShowCreate(true);
    setTitle(createDraft.suggested_title || "");
    setDescription(
      [
        createDraft.channel
          ? `Canal: ${CHANNEL_LABEL[createDraft.channel] ?? createDraft.channel}`
          : null,
        createDraft.decision_reason ? `Motivo: ${createDraft.decision_reason}` : null,
        createDraft.matricula ? `Matrícula: ${createDraft.matricula}` : null,
      ]
        .filter(Boolean)
        .join("\n") || ""
    );
    setActivityType("contact");
    setCreatePriority(createDraft.status === "failed" ? "high" : "normal");
    setLinkStudentId(createDraft.student_id ?? null);
    setLinkLogId(createDraft.intervention_log_id);
    setDraftMeta(createDraft);
    setFormError(null);
    onDraftConsumed?.();
  }, [createDraft, onDraftConsumed]);

  const resetCreateForm = () => {
    setShowCreate(false);
    setTitle("");
    setDescription("");
    setActivityType("follow_up");
    setCreatePriority("normal");
    setAssigneeId("");
    setDueAt("");
    setLinkStudentId(null);
    setLinkLogId(null);
    setDraftMeta(null);
    setFormError(null);
  };

  const createMut = useMutation({
    mutationFn: () =>
      workApi.create({
        title: title.trim(),
        description: description.trim() || null,
        activity_type: activityType as "follow_up" | "contact" | "review" | "other",
        priority: createPriority as "low" | "normal" | "high" | "urgent",
        assignee_user_id: assigneeId || null,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
        student_id: linkStudentId || null,
        intervention_log_id: linkLogId || null,
      }),
    onSuccess: (created) => {
      resetCreateForm();
      void qc.invalidateQueries({ queryKey: ["work-activities"] });
      void qc.invalidateQueries({ queryKey: ["work-activity-summary"] });
      if (created?.id) setSelectedId(created.id);
    },
    onError: (err: Error) => setFormError(err.message),
  });

  const patchMut = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: Parameters<typeof workApi.patch>[1];
    }) => workApi.patch(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["work-activities"] });
      void qc.invalidateQueries({ queryKey: ["work-activity-events"] });
      void qc.invalidateQueries({ queryKey: ["work-activity-summary"] });
    },
  });

  const resultMut = useMutation({
    mutationFn: () =>
      workApi.recordResult(selectedId!, {
        note: resultNote.trim(),
        kind: resultKind || null,
      }),
    onSuccess: () => {
      setResultNote("");
      setResultKind("");
      setResultError(null);
      void qc.invalidateQueries({ queryKey: ["work-activity-events"] });
      void qc.invalidateQueries({ queryKey: ["work-activities"] });
      void qc.invalidateQueries({ queryKey: ["work-activity-summary"] });
    },
    onError: (err: Error) => setResultError(err.message),
  });

  const rows = activitiesQuery.data?.activities ?? [];
  const activeMembers = members.data?.members?.filter((m) => m.status === "active") ?? [];

  return (
    <section className="overflow-hidden rounded-2xl border border-[#E5E7EB] bg-white shadow-sm">
      <div className="space-y-4 border-b border-[#EAECF0] px-4 py-4 sm:px-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div>
            <h2 className="text-base font-semibold tracking-[-0.02em] text-[#101828]">
              Atividades operacionais
            </h2>
            <p className="mt-1 text-sm text-[#667085]">
              Trabalho humano separado de envios automatizados · prioridade, prazos e histórico ·
              vínculo opcional com aluno e campanha
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (showCreate) resetCreateForm();
              else {
                setShowCreate(true);
                setLinkStudentId(null);
                setLinkLogId(null);
                setDraftMeta(null);
              }
            }}
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#2563EB] px-4 text-sm font-semibold text-white hover:bg-[#1D4ED8]"
          >
            <UserPlus className="h-4 w-4" /> Nova atividade
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6" aria-label="Resumo da fila">
          {[
            { label: "Pendentes", value: summaryQuery.data?.pending },
            { label: "Atrasadas", value: summaryQuery.data?.overdue, warning: true },
            { label: "Sem responsável", value: summaryQuery.data?.unassigned, warning: true },
            { label: "Urgentes", value: summaryQuery.data?.urgent_pending, warning: true },
            { label: "De campanhas", value: summaryQuery.data?.campaign_pending },
            { label: "Concluídas · 7d", value: summaryQuery.data?.completed_7d },
          ].map((metric) => (
            <div key={metric.label} className="rounded-xl border border-[#EAECF0] bg-[#FCFCFD] px-3 py-2.5">
              <p className="text-[11px] font-medium text-[#667085]">{metric.label}</p>
              <p className={cn("mt-1 text-lg font-semibold tabular-nums", metric.warning && Number(metric.value) > 0 ? "text-[#B42318]" : "text-[#101828]")}>{summaryQuery.isError || metric.value == null ? "—" : metric.value.toLocaleString("pt-BR")}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" className="flex flex-wrap gap-1 rounded-xl bg-[#F2F4F7] p-1">
            {(
              [
                { id: "all" as const, label: "Todas" },
                { id: "mine" as const, label: "Minhas" },
                { id: "overdue" as const, label: "Vencidas" },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={view === tab.id}
                onClick={() => {
                  setView(tab.id);
                  setAssigneeFilter("");
                }}
                className={cn(
                  "inline-flex min-h-9 items-center rounded-lg px-3 py-2 text-sm font-medium",
                  view === tab.id
                    ? "bg-white text-[#101828] shadow-sm"
                    : "text-[#667085] hover:text-[#344054]"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
          {view === "all" && (
            <select
              value={assigneeFilter}
              onChange={(e) => setAssigneeFilter(e.target.value)}
              aria-label="Filtrar por responsável"
              className="h-10 rounded-xl border border-[#D0D5DD] bg-white px-3 text-sm text-[#344054]"
            >
              <option value="">Todos os responsáveis</option>
              <option value="unassigned">Sem responsável</option>
              {activeMembers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name || m.email}
                </option>
              ))}
            </select>
          )}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filtrar por status"
            className="h-10 rounded-xl border border-[#D0D5DD] bg-white px-3 text-sm text-[#344054]"
          >
            <option value="">Todos os status</option>
            <option value="open">Aberta</option>
            <option value="in_progress">Em andamento</option>
            <option value="completed">Concluída</option>
            <option value="cancelled">Cancelada</option>
          </select>
          <select
            value={originFilter}
            onChange={(e) => setOriginFilter(e.target.value)}
            aria-label="Filtrar por origem"
            className="h-10 rounded-xl border border-[#D0D5DD] bg-white px-3 text-sm text-[#344054]"
          >
            <option value="">Todas as origens</option>
            <option value="manual">Equipe</option>
            <option value="campaign">Campanha</option>
          </select>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            aria-label="Filtrar por prioridade"
            className="h-10 rounded-xl border border-[#D0D5DD] bg-white px-3 text-sm text-[#344054]"
          >
            <option value="">Todas as prioridades</option>
            <option value="urgent">Urgente</option>
            <option value="high">Alta</option>
            <option value="normal">Normal</option>
            <option value="low">Baixa</option>
          </select>
        </div>

        {showCreate && (
          <form
            className="space-y-3 rounded-xl border border-[#D0D5DD] bg-[#F9FAFB] p-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!title.trim()) {
                setFormError("Informe um título.");
                return;
              }
              createMut.mutate();
            }}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm font-semibold text-[#101828]">
                {linkLogId ? "Criar atividade a partir da intervenção" : "Criar atividade"}
              </p>
              {linkLogId && (
                <span className="rounded-full bg-[#EFF4FF] px-2.5 py-1 text-[11px] font-medium text-[#3538CD]">
                  Vinculada ao log · {linkLogId.slice(0, 8)}…
                </span>
              )}
            </div>
            {draftMeta && (
              <p className="text-xs leading-relaxed text-[#667085]">
                Prefill com canal
                {draftMeta.channel
                  ? ` ${CHANNEL_LABEL[draftMeta.channel] ?? draftMeta.channel}`
                  : ""}
                {draftMeta.matricula ? ` · matrícula ${draftMeta.matricula}` : ""}
                {draftMeta.decision_reason ? ` · ${draftMeta.decision_reason}` : ""}. Revise antes de
                salvar.
              </p>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-xs font-medium text-[#475467]">
                Título *
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={200}
                  className="mt-1 h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                  required
                />
              </label>
              <label className="block text-xs font-medium text-[#475467]">
                Tipo
                <select
                  value={activityType}
                  onChange={(e) => setActivityType(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                >
                  <option value="follow_up">Follow-up</option>
                  <option value="contact">Contato</option>
                  <option value="review">Revisão</option>
                  <option value="other">Outro</option>
                </select>
              </label>
              <label className="block text-xs font-medium text-[#475467]">
                Prioridade
                <select
                  value={createPriority}
                  onChange={(e) => setCreatePriority(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                >
                  <option value="urgent">Urgente</option>
                  <option value="high">Alta</option>
                  <option value="normal">Normal</option>
                  <option value="low">Baixa</option>
                </select>
              </label>
              <label className="block text-xs font-medium text-[#475467]">
                Responsável
                <select
                  value={assigneeId}
                  onChange={(e) => setAssigneeId(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                >
                  <option value="">Sem responsável</option>
                  {activeMembers.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.display_name || m.email}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs font-medium text-[#475467]">
                Prazo
                <input
                  type="datetime-local"
                  value={dueAt}
                  onChange={(e) => setDueAt(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                />
              </label>
            </div>
            <label className="block text-xs font-medium text-[#475467]">
              Descrição
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                maxLength={4000}
                className="mt-1 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 py-2 text-sm"
              />
            </label>
            {formError && (
              <p role="alert" className="text-sm text-[#B42318]">
                {formError}
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={createMut.isPending}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#2563EB] px-3 text-sm font-semibold text-white disabled:opacity-50"
              >
                {createMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                Salvar
              </button>
              <button
                type="button"
                onClick={resetCreateForm}
                className="h-9 rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm font-medium text-[#344054]"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}
      </div>

      <div className="p-4 sm:p-5">
        {activitiesQuery.isError ? (
          <div
            role="alert"
            className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] p-4 text-sm text-[#B42318]"
          >
            <p className="font-semibold">Não foi possível carregar atividades.</p>
            <p className="mt-1 text-xs">{(activitiesQuery.error as Error)?.message}</p>
            <button
              type="button"
              onClick={() => void activitiesQuery.refetch()}
              className="mt-2 font-semibold underline"
            >
              Tentar novamente
            </button>
          </div>
        ) : activitiesQuery.isLoading ? (
          <div className="space-y-3" aria-label="Carregando atividades">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-xl bg-[#F2F4F7]" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#D0D5DD] bg-[#F9FAFB] px-5 py-10 text-center">
            <div className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-white text-[#667085] ring-1 ring-[#EAECF0]">
              <ClipboardList className="h-5 w-5" />
            </div>
            <p className="mt-3 text-sm font-semibold text-[#101828]">
              {view === "mine"
                ? "Nenhuma atividade atribuída a você"
                : view === "overdue"
                  ? "Nenhuma atividade vencida"
                  : "Nenhuma atividade operacional"}
            </p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-[#667085]">
              Atividades são independentes dos logs de intervenção. Use &quot;Criar atividade&quot; nas
              filas de logs ou o botão acima para atribuir responsável e prazo.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead>
                <tr className="border-b border-[#EAECF0] text-xs text-[#667085]">
                  <th className="px-3 py-3 font-medium">Título</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 font-medium">Responsável</th>
                  <th className="px-3 py-3 font-medium">Prazo</th>
                  <th className="px-3 py-3 font-medium">Ações</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item: WorkActivity) => (
                  <tr key={item.id} className="border-b border-[#F2F4F7]">
                    <td className="px-3 py-3.5">
                      <button
                        type="button"
                        onClick={() => setSelectedId(selectedId === item.id ? null : item.id)}
                        className="text-left font-semibold text-[#101828] hover:text-[#2563EB]"
                      >
                        {item.title}
                      </button>
                      <p className="mt-0.5 text-xs text-[#667085]">
                        {TYPE_LABEL[item.activity_type] ?? item.activity_type}
                        {` · ${ORIGIN_LABEL[item.origin_type] ?? item.origin_type}`}
                        {` · prioridade ${PRIORITY_LABEL[item.priority] ?? item.priority}`}
                        {item.intervention_log_id ? " · vinculada a log" : ""}
                        {item.student_id ? " · com aluno" : ""}
                      </p>
                      {item.campaign_id && (
                        <p className="mt-1 text-[10px] font-medium text-[#3538CD]">
                          Campanha · {item.campaign_id.slice(0, 8)}…
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-3.5">
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
                          item.status === "completed"
                            ? "bg-[#ECFDF3] text-[#027A48]"
                            : item.status === "cancelled"
                              ? "bg-[#F2F4F7] text-[#475467]"
                              : item.overdue
                                ? "bg-[#FEF3F2] text-[#B42318]"
                                : "bg-[#EFF4FF] text-[#3538CD]"
                        )}
                      >
                        {STATUS_LABEL[item.status] ?? item.status}
                        {item.overdue ? " · vencida" : ""}
                      </span>
                    </td>
                    <td className="px-3 py-3.5 text-[#475467]">
                      {item.assignee?.display_name || item.assignee?.email || (
                        <span className="text-[#98A2B3]">Sem responsável</span>
                      )}
                    </td>
                    <td className="px-3 py-3.5">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 text-xs",
                          item.overdue ? "font-semibold text-[#B42318]" : "text-[#475467]"
                        )}
                      >
                        <CalendarClock className="h-3.5 w-3.5" />
                        {formatDate(item.due_at)}
                      </span>
                    </td>
                    <td className="px-3 py-3.5">
                      <div className="flex flex-wrap gap-1">
                        {item.status !== "completed" && item.status !== "cancelled" && (
                          <>
                            {item.status === "open" ? (
                              <button
                                type="button"
                                title="Iniciar atividade"
                                aria-label={`Iniciar ${item.title}`}
                                disabled={patchMut.isPending}
                                onClick={() =>
                                  patchMut.mutate({
                                    id: item.id,
                                    body: { status: "in_progress" as WorkActivityStatus },
                                  })
                                }
                                className="rounded-lg border border-[#D0D5DD] bg-white p-1.5 text-[#344054]"
                              >
                                <Play className="h-4 w-4" />
                              </button>
                            ) : (
                              <button
                                type="button"
                                title="Retomar como aberta"
                                aria-label={`Retomar ${item.title}`}
                                disabled={patchMut.isPending}
                                onClick={() =>
                                  patchMut.mutate({
                                    id: item.id,
                                    body: { status: "open" as WorkActivityStatus },
                                  })
                                }
                                className="rounded-lg border border-[#D0D5DD] bg-white p-1.5 text-[#344054]"
                              >
                                <RotateCcw className="h-4 w-4" />
                              </button>
                            )}
                            <button
                              type="button"
                              title="Concluir"
                              disabled={patchMut.isPending}
                              onClick={() =>
                                patchMut.mutate({
                                  id: item.id,
                                  body: { status: "completed" as WorkActivityStatus },
                                })
                              }
                              className="rounded-lg border border-[#ABEFC6] bg-[#ECFDF3] p-1.5 text-[#027A48]"
                            >
                              <CheckCircle2 className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              title="Cancelar"
                              disabled={patchMut.isPending}
                              onClick={() =>
                                patchMut.mutate({
                                  id: item.id,
                                  body: { status: "cancelled" as WorkActivityStatus },
                                })
                              }
                              className="rounded-lg border border-[#FECDCA] bg-[#FEF3F2] p-1.5 text-[#B42318]"
                            >
                              <XCircle className="h-4 w-4" />
                            </button>
                            <select
                              aria-label="Alterar prioridade"
                              value={item.priority}
                              disabled={patchMut.isPending}
                              onChange={(e) =>
                                patchMut.mutate({
                                  id: item.id,
                                  body: {
                                    priority: e.target.value as "low" | "normal" | "high" | "urgent",
                                  },
                                })
                              }
                              className="h-8 rounded-lg border border-[#D0D5DD] bg-white px-2 text-xs"
                            >
                              <option value="urgent">Urgente</option>
                              <option value="high">Alta</option>
                              <option value="normal">Normal</option>
                              <option value="low">Baixa</option>
                            </select>
                            <select
                              aria-label="Atribuir responsável"
                              value={item.assignee_user_id ?? ""}
                              disabled={patchMut.isPending}
                              onChange={(e) => {
                                const v = e.target.value;
                                if (!v) {
                                  patchMut.mutate({ id: item.id, body: { clear_assignee: true } });
                                } else {
                                  patchMut.mutate({
                                    id: item.id,
                                    body: { assignee_user_id: v },
                                  });
                                }
                              }}
                              className="h-8 max-w-[140px] rounded-lg border border-[#D0D5DD] bg-white px-2 text-xs"
                            >
                              <option value="">Sem resp.</option>
                              {activeMembers.map((m) => (
                                <option key={m.id} value={m.id}>
                                  {m.display_name || m.email}
                                </option>
                              ))}
                            </select>
                          </>
                        )}
                        <button
                          type="button"
                          title="Detalhe e histórico"
                          onClick={() => setSelectedId(selectedId === item.id ? null : item.id)}
                          className="rounded-lg border border-[#D0D5DD] bg-white p-1.5 text-[#475467]"
                        >
                          <History className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selectedId && selectedActivity && (
          <div className="mt-4 space-y-4 rounded-xl border border-[#EAECF0] bg-[#F9FAFB] p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-[#101828]">{selectedActivity.title}</p>
                <p className="mt-0.5 text-xs text-[#667085]">
                  {TYPE_LABEL[selectedActivity.activity_type] ?? selectedActivity.activity_type} ·{" "}
                  {STATUS_LABEL[selectedActivity.status] ?? selectedActivity.status} ·{" "}
                  {ORIGIN_LABEL[selectedActivity.origin_type] ?? selectedActivity.origin_type} ·{" "}
                  prioridade {PRIORITY_LABEL[selectedActivity.priority] ?? selectedActivity.priority}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedId(null);
                  setResultNote("");
                  setResultKind("");
                  setResultError(null);
                }}
                className="text-xs font-medium text-[#667085] hover:text-[#344054]"
              >
                Fechar
              </button>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <InfoBlock label="Descrição">
                {selectedActivity.description?.trim() || (
                  <span className="text-[#98A2B3]">Sem descrição</span>
                )}
              </InfoBlock>
              <InfoBlock label="Responsável">
                {selectedActivity.assignee?.display_name ||
                  selectedActivity.assignee?.email ||
                  "Sem responsável"}
              </InfoBlock>
              <InfoBlock label="Origem">
                {ORIGIN_LABEL[selectedActivity.origin_type] ?? selectedActivity.origin_type}
                {selectedActivity.campaign_id ? ` · campanha ${selectedActivity.campaign_id.slice(0, 8)}…` : ""}
              </InfoBlock>
              <InfoBlock label="Prazo">{formatDate(selectedActivity.due_at)}</InfoBlock>
              <InfoBlock label="Criada em">{formatDate(selectedActivity.created_at)}</InfoBlock>
              <InfoBlock label="Concluída em">{formatDate(selectedActivity.completed_at)}</InfoBlock>
              <InfoBlock label="Cancelada em">{formatDate(selectedActivity.cancelled_at)}</InfoBlock>
            </div>

            <div className="rounded-lg border border-[#E5E7EB] bg-white p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#667085]">
                Contexto do aluno
              </p>
              {!selectedActivity.student_id ? (
                <p className="text-xs text-[#98A2B3]">Nenhum aluno vinculado a esta atividade.</p>
              ) : studentQuery.isLoading ? (
                <p className="text-xs text-[#667085]">Carregando dados do aluno…</p>
              ) : studentQuery.isError ? (
                <p className="text-xs text-[#B42318]">
                  Não foi possível carregar o contexto do aluno. O vínculo permanece; tente novamente.
                </p>
              ) : (
                <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <span className="text-[#98A2B3]">Nome</span>
                    <p className="font-medium text-[#101828]">{studentQuery.data?.nome ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[#98A2B3]">Matrícula</span>
                    <p className="font-medium text-[#101828]">
                      {studentQuery.data?.matricula ?? "—"}
                    </p>
                  </div>
                  <div>
                    <span className="text-[#98A2B3]">Curso</span>
                    <p className="font-medium text-[#101828]">{studentQuery.data?.curso ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[#98A2B3]">Risco atual</span>
                    <div className="mt-0.5 flex items-center gap-2">
                      {studentQuery.data?.risk_level ? (
                        <RiskBadge
                          level={studentQuery.data.risk_level as "baixo" | "medio" | "critico"}
                        />
                      ) : (
                        <span className="text-[#98A2B3]">Sem avaliação</span>
                      )}
                      {studentQuery.data?.risk_score != null && (
                        <span className="tabular-nums text-[#475467]">
                          {Number(studentQuery.data.risk_score).toLocaleString("pt-BR", {
                            maximumFractionDigits: 1,
                          })}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-lg border border-[#E5E7EB] bg-white p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#667085]">
                Intervenção relacionada
              </p>
              {!selectedActivity.intervention_log_id ? (
                <p className="text-xs text-[#98A2B3]">
                  Nenhuma intervenção vinculada. A atividade é independente do ciclo de envio.
                </p>
              ) : relatedLogQuery.isLoading ? (
                <p className="text-xs text-[#667085]">Carregando log de intervenção…</p>
              ) : relatedLogQuery.isError ? (
                <p className="text-xs text-[#B42318]">
                  Log vinculado ({selectedActivity.intervention_log_id.slice(0, 8)}…), mas não foi
                  possível carregar os detalhes.
                </p>
              ) : !relatedLogQuery.data ? (
                <p className="text-xs text-[#667085]">
                  Log {selectedActivity.intervention_log_id.slice(0, 8)}… vinculado; detalhes não
                  encontrados na consulta recente (tenant isolado).
                </p>
              ) : (
                <InterventionContext log={relatedLogQuery.data} />
              )}
            </div>

            {selectedActivity.status !== "cancelled" && (
              <div className="rounded-lg border border-[#D0D5DD] bg-white p-3">
                <p className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[#667085]">
                  <FileText className="h-3.5 w-3.5" /> Registrar resultado operacional
                </p>
                <p className="mb-3 text-[11px] leading-relaxed text-[#98A2B3]">
                  Grava evento <code className="text-[#475467]">result_recorded</code>. Não altera
                  status da atividade, delivery status nem outcome de permanência.
                </p>
                <form
                  className="space-y-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!resultNote.trim()) {
                      setResultError("Informe uma observação.");
                      return;
                    }
                    resultMut.mutate();
                  }}
                >
                  <div className="grid gap-2 sm:grid-cols-[180px_1fr]">
                    <label className="block text-xs font-medium text-[#475467]">
                      Tipo
                      <select
                        value={resultKind}
                        onChange={(e) => setResultKind(e.target.value as WorkResultKind | "")}
                        className="mt-1 h-9 w-full rounded-lg border border-[#D0D5DD] bg-white px-2 text-sm"
                      >
                        <option value="">Sem classificação</option>
                        {(Object.keys(RESULT_KIND_LABEL) as WorkResultKind[]).map((k) => (
                          <option key={k} value={k}>
                            {RESULT_KIND_LABEL[k]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block text-xs font-medium text-[#475467]">
                      Observação *
                      <input
                        value={resultNote}
                        onChange={(e) => setResultNote(e.target.value)}
                        maxLength={2000}
                        placeholder="O que aconteceu no contato / follow-up"
                        className="mt-1 h-9 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm"
                        required
                      />
                    </label>
                  </div>
                  {resultError && (
                    <p role="alert" className="text-xs text-[#B42318]">
                      {resultError}
                    </p>
                  )}
                  <button
                    type="submit"
                    disabled={resultMut.isPending}
                    className="inline-flex h-8 items-center gap-2 rounded-lg bg-[#344054] px-3 text-xs font-semibold text-white disabled:opacity-50"
                  >
                    {resultMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Registrar resultado
                  </button>
                </form>
              </div>
            )}

            <div>
              <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#101828]">
                <History className="h-4 w-4" /> Histórico de eventos
              </p>
              {eventsQuery.isLoading ? (
                <p className="text-xs text-[#667085]">Carregando eventos…</p>
              ) : eventsQuery.isError ? (
                <p className="text-xs text-[#B42318]">Não foi possível carregar o histórico.</p>
              ) : (eventsQuery.data?.events?.length ?? 0) === 0 ? (
                <p className="text-xs text-[#667085]">Sem eventos registrados.</p>
              ) : (
                <ul className="space-y-2">
                  {eventsQuery.data!.events.map((ev) => (
                    <li key={ev.id} className="text-xs text-[#475467]">
                      <span className="font-medium text-[#101828]">
                        {EVENT_LABEL[ev.event_type] ?? ev.event_type}
                      </span>{" "}
                      · {formatDate(ev.created_at)}
                      {ev.payload ? (
                        <span className="ml-1 text-[#98A2B3]">{JSON.stringify(ev.payload)}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        <p className="mt-3 text-xs text-[#667085]">
          Status da atividade ≠ status de envio do InterventionLog ≠ outcome de permanência. Resultado
          operacional é apenas evento de auditoria.
        </p>
      </div>
    </section>
  );
}

function InfoBlock({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[#E5E7EB] bg-white px-3 py-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-[#98A2B3]">{label}</p>
      <div className="mt-0.5 text-xs text-[#344054]">{children}</div>
    </div>
  );
}

function InterventionContext({ log }: { log: InterventionLog }) {
  return (
    <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
      <div>
        <span className="text-[#98A2B3]">Canal</span>
        <p className="font-medium text-[#101828]">
          {log.channel ? CHANNEL_LABEL[log.channel] ?? log.channel : "—"}
        </p>
      </div>
      <div>
        <span className="text-[#98A2B3]">Data</span>
        <p className="font-medium text-[#101828]">{formatDate(log.created_at)}</p>
      </div>
      <div>
        <span className="text-[#98A2B3]">Decision reason</span>
        <p className="font-medium text-[#101828]">{log.decision_reason || "—"}</p>
      </div>
      <div>
        <span className="text-[#98A2B3]">Status de execução</span>
        <p className="font-medium text-[#101828]">{log.status || "—"}</p>
      </div>
      <div>
        <span className="text-[#98A2B3]">Delivery status</span>
        <p className="font-medium text-[#101828]">{log.delivery_status || "—"}</p>
      </div>
      <div>
        <span className="text-[#98A2B3]">Outcome</span>
        <p className="font-medium text-[#101828]">
          {log.outcome
            ? `${log.outcome}${log.outcome_at ? ` · ${formatDate(log.outcome_at)}` : ""}`
            : "—"}
        </p>
      </div>
    </div>
  );
}
