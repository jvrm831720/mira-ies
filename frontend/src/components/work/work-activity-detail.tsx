"use client";

import { FileText, History, Loader2 } from "@/components/ui/icons";
import { RiskBadge } from "@/components/ui/badge";
import { StudentRiskFactors } from "@/components/students/student-risk-factors";
import { InfoBlock, InterventionContext } from "./work-activity-detail-parts";
import { formatDate, STATUS_LABEL, TYPE_LABEL, PRIORITY_LABEL, ORIGIN_LABEL, EVENT_LABEL, RESULT_KIND_LABEL } from "./work-activity-labels";
import type { WorkActivity, WorkResultKind } from "@/types/work";
import { workApi } from "@/lib/work-api";
import { api } from "@/lib/api";

type StudentRisk = Awaited<ReturnType<typeof api.studentRisk>>;
type Logs = Awaited<ReturnType<typeof api.retentionLogs>>;
type Intervention = NonNullable<Logs["logs"]>[number];
type Events = Awaited<ReturnType<typeof workApi.events>>;
type Props = {
  selectedActivity: WorkActivity;
  canSensitive: boolean;
  onClose: () => void;
  student?: StudentRisk; studentLoading: boolean; studentError: boolean;
  log?: Intervention | null; logLoading: boolean; logError: boolean;
  events?: Events; eventsLoading: boolean; eventsError: boolean;
  resultNote: string; setResultNote: (value: string) => void;
  resultKind: WorkResultKind | "";
  setResultKind: (value: WorkResultKind | "") => void;
  resultError: string | null; setResultError: (value: string | null) => void;
  resultPending: boolean;
  onRecord: () => void;
};
export function WorkActivityDetail({selectedActivity, canSensitive, onClose,
  student, studentLoading, studentError, log, logLoading, logError, events, eventsLoading, eventsError,
  resultNote, setResultNote, resultKind, setResultKind, resultError, setResultError,
  resultPending, onRecord}: Props) {
  return (
          <div className="mt-4 space-y-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-source-f9fafb)] p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-[var(--color-ink)]">{selectedActivity.title}</p>
                <p className="mt-0.5 text-xs text-[var(--color-slate-600)]">
                  {TYPE_LABEL[selectedActivity.activity_type] ?? selectedActivity.activity_type} ·{" "}
                  {STATUS_LABEL[selectedActivity.status] ?? selectedActivity.status} ·{" "}
                  {ORIGIN_LABEL[selectedActivity.origin_type] ?? selectedActivity.origin_type} ·{" "}
                  prioridade {PRIORITY_LABEL[selectedActivity.priority] ?? selectedActivity.priority}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="text-xs font-medium text-[var(--color-slate-600)] hover:text-[var(--color-slate-600)]"
              >
                Fechar
              </button>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <InfoBlock label="Descrição">
                {selectedActivity.description?.trim() || (
                  <span className="text-[var(--color-muted)]">Sem descrição</span>
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

            <div className="rounded-lg border border-[var(--color-border)] bg-white p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-slate-600)]">
                Contexto do aluno
              </p>
              {!canSensitive ? <p className="text-[12px] text-[var(--color-muted)]">Contexto de risco restrito ao perfil autorizado.</p> : !selectedActivity.student_id ? (
                <p className="text-xs text-[var(--color-muted)]">Nenhum aluno vinculado a esta atividade.</p>
              ) : studentLoading ? (
                <p className="text-xs text-[var(--color-slate-600)]">Carregando dados do aluno…</p>
              ) : studentError ? (
                <p className="text-xs text-[var(--color-red)]">
                  Não foi possível carregar o contexto do aluno. O vínculo permanece; tente novamente.
                </p>
              ) : (
                <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <span className="text-[var(--color-muted)]">Nome</span>
                    <p className="font-medium text-[var(--color-ink)]">{student?.nome ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[var(--color-muted)]">Matrícula</span>
                    <p className="font-medium text-[var(--color-ink)]">
                      {student?.matricula ?? "—"}
                    </p>
                  </div>
                  <div>
                    <span className="text-[var(--color-muted)]">Curso</span>
                    <p className="font-medium text-[var(--color-ink)]">{student?.curso ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[var(--color-muted)]">Risco atual</span>
                    <div className="mt-0.5 flex items-center gap-2">
                      {student?.risk_level ? (
                        <RiskBadge
                          level={student.risk_level as "baixo" | "medio" | "critico"}
                        />
                      ) : (
                        <span className="text-[var(--color-muted)]">Sem avaliação</span>
                      )}
                      {student?.risk_score != null && (
                        <span className="tabular-nums text-[var(--color-slate-600)]">
                          {Number(student.risk_score).toLocaleString("pt-BR", {
                            maximumFractionDigits: 1,
                          })}
                        </span>
                      )}
                    </div>
                  </div>
                  {student && <div className="col-span-full"><StudentRiskFactors student={student}/></div>}
                </div>
              )}
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-white p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-slate-600)]">
                Intervenção relacionada
              </p>
              {!selectedActivity.intervention_log_id ? (
                <p className="text-xs text-[var(--color-muted)]">
                  Nenhuma intervenção vinculada. A atividade é independente do ciclo de envio.
                </p>
              ) : logLoading ? (
                <p className="text-xs text-[var(--color-slate-600)]">Carregando log de intervenção…</p>
              ) : logError ? (
                <p className="text-xs text-[var(--color-red)]">
                  Log vinculado ({selectedActivity.intervention_log_id.slice(0, 8)}…), mas não foi
                  possível carregar os detalhes.
                </p>
              ) : !log ? (
                <p className="text-xs text-[var(--color-slate-600)]">
                  Log {selectedActivity.intervention_log_id.slice(0, 8)}… vinculado; detalhes não
                  encontrados na consulta recente (tenant isolado).
                </p>
              ) : (
                <InterventionContext log={log} />
              )}
            </div>

            {selectedActivity.status !== "cancelled" && (
              <div className="rounded-lg border border-[var(--color-border)] bg-white p-3">
                <p className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-slate-600)]">
                  <FileText className="h-3.5 w-3.5" /> Registrar resultado operacional
                </p>
                <p className="mb-3 text-[11px] leading-relaxed text-[var(--color-muted)]">
                  Grava evento <code className="text-[var(--color-slate-600)]">result_recorded</code>. Não altera
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
                    onRecord();
                  }}
                >
                  <div className="grid gap-2 sm:grid-cols-[180px_1fr]">
                    <label className="block text-xs font-medium text-[var(--color-slate-600)]">
                      Tipo
                      <select
                        value={resultKind}
                        onChange={(e) => setResultKind(e.target.value as WorkResultKind | "")}
                        className="mt-1 h-9 w-full rounded-lg border border-[var(--color-border)] bg-white px-2 text-sm"
                      >
                        <option value="">Sem classificação</option>
                        {(Object.keys(RESULT_KIND_LABEL) as WorkResultKind[]).map((k) => (
                          <option key={k} value={k}>
                            {RESULT_KIND_LABEL[k]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block text-xs font-medium text-[var(--color-slate-600)]">
                      Observação *
                      <input
                        value={resultNote}
                        onChange={(e) => setResultNote(e.target.value)}
                        maxLength={2000}
                        placeholder="O que aconteceu no contato / follow-up"
                        className="mt-1 h-9 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm"
                        required
                      />
                    </label>
                  </div>
                  {resultError && (
                    <p role="alert" className="text-xs text-[var(--color-red)]">
                      {resultError}
                    </p>
                  )}
                  <button
                    type="submit"
                    disabled={resultPending}
                    className="inline-flex h-8 items-center gap-2 rounded-lg bg-[var(--color-slate-600)] px-3 text-xs font-semibold text-white disabled:opacity-50"
                  >
                    {resultPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Registrar resultado
                  </button>
                </form>
              </div>
            )}

            <div>
              <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-[var(--color-ink)]">
                <History className="h-4 w-4" /> Histórico de eventos
              </p>
              {eventsLoading ? (
                <p className="text-xs text-[var(--color-slate-600)]">Carregando eventos…</p>
              ) : eventsError ? (
                <p className="text-xs text-[var(--color-red)]">Não foi possível carregar o histórico.</p>
              ) : (events?.events?.length ?? 0) === 0 ? (
                <p className="text-xs text-[var(--color-slate-600)]">Sem eventos registrados.</p>
              ) : (
                <ul className="space-y-2">
                  {events!.events.map((ev) => (
                    <li key={ev.id} className="text-xs text-[var(--color-slate-600)]">
                      <span className="font-medium text-[var(--color-ink)]">
                        {EVENT_LABEL[ev.event_type] ?? ev.event_type}
                      </span>{" "}
                      · {formatDate(ev.created_at)}
                      {ev.payload ? (
                        <span className="ml-1 text-[var(--color-muted)]">{JSON.stringify(ev.payload)}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
  );
}
