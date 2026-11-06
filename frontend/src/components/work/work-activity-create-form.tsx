"use client";

import { Loader2 } from "@/components/ui/icons";
import type { CreateFromLogDraft } from "@/types/work";
import { api } from "@/lib/api";
import { CHANNEL_LABEL } from "./work-activity-labels";

type Member = Awaited<ReturnType<typeof api.listMembers>>["members"][number];
type Props = {
  title: string; setTitle: (value: string) => void;
  description: string; setDescription: (value: string) => void;
  activityType: string; setActivityType: (value: string) => void;
  createPriority: string; setCreatePriority: (value: string) => void;
  assigneeId: string; setAssigneeId: (value: string) => void;
  dueAt: string; setDueAt: (value: string) => void;
  linkLogId: string | null;
  draftMeta: CreateFromLogDraft | null;
  formError: string | null;
  activeMembers: Member[];
  saving: boolean;
  onSave: () => void; onCancel: () => void;
};

export function WorkActivityCreateForm({title, setTitle, description, setDescription,
  activityType, setActivityType, createPriority, setCreatePriority,
  assigneeId, setAssigneeId, dueAt, setDueAt, linkLogId, draftMeta, formError,
  activeMembers, saving, onSave, onCancel}: Props) {
  return (
          <form
            className="space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-source-f9fafb)] p-4"
            onSubmit={(e) => { e.preventDefault(); onSave(); }}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm font-semibold text-[var(--color-ink)]">
                {linkLogId ? "Criar atividade a partir da intervenção" : "Criar atividade"}
              </p>
              {linkLogId && (
                <span className="rounded-full bg-[var(--color-source-eff4ff)] px-2.5 py-1 text-[11px] font-medium text-[var(--color-source-3538cd)]">
                  Vinculada ao log · {linkLogId.slice(0, 8)}…
                </span>
              )}
            </div>
            {draftMeta && (
              <p className="text-xs leading-relaxed text-[var(--color-slate-600)]">
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
              <label className="block text-xs font-medium text-[var(--color-slate-600)]">
                Título *
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={200}
                  className="mt-1 h-10 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm"
                  required
                />
              </label>
              <label className="block text-xs font-medium text-[var(--color-slate-600)]">
                Tipo
                <select
                  value={activityType}
                  onChange={(e) => setActivityType(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm"
                >
                  <option value="follow_up">Follow-up</option>
                  <option value="contact">Contato</option>
                  <option value="review">Revisão</option>
                  <option value="other">Outro</option>
                </select>
              </label>
              <label className="block text-xs font-medium text-[var(--color-slate-600)]">
                Prioridade
                <select
                  value={createPriority}
                  onChange={(e) => setCreatePriority(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm"
                >
                  <option value="urgent">Urgente</option>
                  <option value="high">Alta</option>
                  <option value="normal">Normal</option>
                  <option value="low">Baixa</option>
                </select>
              </label>
              <label className="block text-xs font-medium text-[var(--color-slate-600)]">
                Responsável
                <select
                  value={assigneeId}
                  onChange={(e) => setAssigneeId(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm"
                >
                  <option value="">Sem responsável</option>
                  {activeMembers.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.display_name || m.email}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs font-medium text-[var(--color-slate-600)]">
                Prazo
                <input
                  type="datetime-local"
                  value={dueAt}
                  onChange={(e) => setDueAt(e.target.value)}
                  className="mt-1 h-10 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm"
                />
              </label>
            </div>
            <label className="block text-xs font-medium text-[var(--color-slate-600)]">
              Descrição
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                maxLength={4000}
                className="mt-1 w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm"
              />
            </label>
            {formError && (
              <p role="alert" className="text-sm text-[var(--color-red)]">
                {formError}
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={saving}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-[var(--color-blue)] px-3 text-sm font-semibold text-white disabled:opacity-50"
              >
                {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                Salvar
              </button>
              <button
                type="button"
                onClick={onCancel}
                className="h-9 rounded-lg border border-[var(--color-border)] bg-white px-3 text-sm font-medium text-[var(--color-slate-600)]"
              >
                Cancelar
              </button>
            </div>
          </form>
  );
}
