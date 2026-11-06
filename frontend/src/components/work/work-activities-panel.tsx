"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "@/components/ui/icons";
import { workApi } from "@/lib/work-api";
import { api } from "@/lib/api";
import type { CreateFromLogDraft, WorkResultKind } from "@/types/work";
import { WorkQueueFilters } from "./work-queue-filters";
import { hasNavigationPermission } from "@/components/layout/navigation";
import { toast } from "sonner";
import { WorkQueueSummary } from "./work-queue-summary";
import { WorkActivityList } from "./work-activity-list";
import { WorkActivityCreateForm } from "./work-activity-create-form";
import { WorkActivityDetail } from "./work-activity-detail";
import { WorkSevenDayPriority } from "./work-seven-day-priority";
import { CHANNEL_LABEL } from "./work-activity-labels";

type Props = {
  createDraft?: CreateFromLogDraft | null;
  onDraftConsumed?: () => void;
};

export function WorkActivitiesPanel({ createDraft = null, onDraftConsumed }: Props) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const canSensitive = hasNavigationPermission(me.data, "students.sensitive.view");
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

  const noContact = useQuery({
    queryKey: ["work-priority-no-contact", me.data?.tenant_id],
    queryFn: workApi.priorityWithoutContact,
    enabled: Boolean(me.data?.tenant_id && canSensitive), retry: false,
    staleTime: 60_000,
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
    enabled: Boolean(selectedActivity?.student_id) && canSensitive,
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
      void qc.invalidateQueries({ queryKey: ["work-priority-no-contact"] });
      if (created?.id) setSelectedId(created.id);
      toast.success("Atividade criada.");
    },
    onError: (err: Error) => { setFormError(err.message); toast.error(err.message); },
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
      toast.success("Atividade atualizada.");
    },
    onError: (error: Error) => toast.error(error.message || "Falha ao atualizar atividade."),
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
      toast.success("Resultado operacional registrado.");
      void qc.invalidateQueries({ queryKey: ["work-activity-events"] });
      void qc.invalidateQueries({ queryKey: ["work-activities"] });
      void qc.invalidateQueries({ queryKey: ["work-activity-summary"] });
    },
    onError: (err: Error) => { setResultError(err.message); toast.error(err.message); },
  });

  const rows = activitiesQuery.data?.activities ?? [];
  const activeMembers = members.data?.members?.filter((m) => m.status === "active") ?? [];

  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-sm">
      <div className="space-y-4 border-b border-[var(--color-border)] px-4 py-4 sm:px-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
          <div>
            <h2 className="text-base font-semibold tracking-[-0.02em] text-[var(--color-ink)]">
              Atividades operacionais
            </h2>
            <p className="mt-1 text-sm text-[var(--color-slate-600)]">
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
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-[var(--color-blue)] px-4 text-sm font-semibold text-white hover:bg-[var(--color-blue)]"
          >
            <UserPlus className="h-4 w-4" /> Nova atividade
          </button>
        </div>

        <WorkQueueSummary data={summaryQuery.data} isLoading={summaryQuery.isLoading} isError={summaryQuery.isError} />
        {canSensitive ? <WorkSevenDayPriority data={noContact.data} loading={noContact.isLoading} error={noContact.isError} /> : null}

        <WorkQueueFilters view={view} setView={setView}
          assigneeFilter={assigneeFilter} setAssigneeFilter={setAssigneeFilter}
          statusFilter={statusFilter} setStatusFilter={setStatusFilter}
          originFilter={originFilter} setOriginFilter={setOriginFilter}
          priorityFilter={priorityFilter} setPriorityFilter={setPriorityFilter}
          activeMembers={activeMembers} />
        {summaryQuery.data?.urgent_pending ? <button type="button" onClick={() => { setView("all"); setPriorityFilter("urgent"); }}
          className="flex w-full items-center justify-between rounded-[var(--radius-md)] border border-[var(--color-peach-tint-border)] bg-[var(--color-peach-tint)] px-3 py-2 text-left text-xs text-[var(--color-ink)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]">
          <span><strong>{summaryQuery.data.urgent_pending}</strong> atividade(s) urgentes aguardam tratamento</span>
          <span className="font-semibold">Priorizar agora</span>
        </button> : null}
        {showCreate && <WorkActivityCreateForm title={title} setTitle={setTitle}
          description={description} setDescription={setDescription}
          activityType={activityType} setActivityType={setActivityType}
          createPriority={createPriority} setCreatePriority={setCreatePriority}
          assigneeId={assigneeId} setAssigneeId={setAssigneeId}
          dueAt={dueAt} setDueAt={setDueAt}
          linkLogId={linkLogId} draftMeta={draftMeta} formError={formError}
          activeMembers={activeMembers} saving={createMut.isPending}
          onSave={() => { if (!title.trim()) { setFormError("Informe um título."); return; } createMut.mutate(); }}
          onCancel={resetCreateForm} />}
      </div>

      <div className="p-4 sm:p-5">
        <WorkActivityList rows={rows} view={view} selectedId={selectedId} activeMembers={activeMembers}
          loading={activitiesQuery.isLoading} error={activitiesQuery.isError}
          errorMessage={(activitiesQuery.error as Error | null)?.message} patchPending={patchMut.isPending}
          onRetry={() => { void activitiesQuery.refetch(); }}
          onToggle={id => setSelectedId(selectedId === id ? null : id)} onPatch={patchMut.mutate} />

        {selectedId && selectedActivity && <WorkActivityDetail
          selectedActivity={selectedActivity} canSensitive={canSensitive}
          onClose={() => { setSelectedId(null); setResultNote(""); setResultKind(""); setResultError(null); }}
          student={studentQuery.data} studentLoading={studentQuery.isLoading} studentError={studentQuery.isError}
          log={relatedLogQuery.data} logLoading={relatedLogQuery.isLoading} logError={relatedLogQuery.isError}
          events={eventsQuery.data} eventsLoading={eventsQuery.isLoading} eventsError={eventsQuery.isError}
          resultNote={resultNote} setResultNote={setResultNote} resultKind={resultKind}
          setResultKind={setResultKind} resultError={resultError} setResultError={setResultError}
          resultPending={resultMut.isPending}
          onRecord={() => { if (!resultNote.trim()) { setResultError("Informe uma observação."); return; } resultMut.mutate(); }}
        />}


        <p className="mt-3 text-xs text-[var(--color-slate-600)]">
          Status da atividade ≠ status de envio do InterventionLog ≠ outcome de permanência. Resultado
          operacional é apenas evento de auditoria.
        </p>
      </div>
    </section>
  );
}

