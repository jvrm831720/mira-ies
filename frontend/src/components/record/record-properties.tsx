"use client";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { formatPropertyValue } from "@/components/object-index/object-index-utils";
import type { RecordPropertyGroup } from "./record-types";

export function RecordProperties({ groups, compact = false }: { groups: RecordPropertyGroup[]; compact?: boolean }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  return <div className="space-y-4">
    {groups.map(group => <section key={group.id} aria-label={group.title}
      className={cn("overflow-hidden rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white", compact && "rounded-[var(--radius-md)]")}>
      <h3 className="border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2.5 text-[11px] font-semibold text-[var(--color-slate-600)]">{group.title}</h3>
      <dl className="divide-y divide-[var(--color-border-subtle)]">
        {group.properties.map(property => {
          const value = property.value == null || property.value === "" ? "Não informado" : formatPropertyValue(property.type || "text", property.value);
          const active = editing === group.id + ":" + property.key;
          const canEdit = property.editable === true && typeof property.onEdit === "function";
          return <div key={property.key} className="grid grid-cols-[minmax(85px,38%)_minmax(0,1fr)] items-start gap-3 px-4 py-2.5 text-[12px]">
            <dt className="text-[var(--color-muted)]">{property.label}</dt>
            <dd className="min-w-0 break-words text-[var(--color-ink)]">
              {active && canEdit ? <form className="flex min-w-0 flex-col gap-2" onSubmit={async event => {
                event.preventDefault(); setSaving(true); setError("");
                try { await property.onEdit!(draft); setEditing(null); }
                catch(e) { setError(e instanceof Error ? e.message : "Não foi possível salvar."); }
                finally { setSaving(false); }
              }}>
                <input autoFocus value={draft} onChange={e => setDraft(e.target.value)} disabled={saving}
                  className="min-w-0 rounded-[var(--radius-md)] border border-[var(--color-border)] px-2 py-1.5 text-[12px] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]" />
                <div className="flex gap-2">
                  <button type="submit" disabled={saving} className="text-[var(--color-blue)] disabled:opacity-50">Salvar</button>
                  <button type="button" onClick={() => {setEditing(null);setError("");}}>Cancelar</button>
                </div>
                {error && <p role="alert" className="text-[var(--color-red)]">{error}</p>}
              </form> : <div className="flex items-start justify-between gap-2">
                <span className={cn(!property.value && property.value !== 0 && property.value !== false && "text-[var(--color-muted)]")}>{value}</span>
                {canEdit && <button type="button" className="shrink-0 text-[11px] text-[var(--color-blue)] hover:underline"
                  onClick={() => { setEditing(group.id + ":" + property.key); setDraft(String(property.value ?? "")); setError(""); }}>
                  Editar
                </button>}
              </div>}
            </dd>
          </div>;
        })}
      </dl>
    </section>)}
  </div>;
}
