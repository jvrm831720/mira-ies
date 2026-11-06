import Link from "next/link";
import { Activity, BookOpen, MessageCircle, Shield, Clock3, Wallet } from "@/components/ui/icons";
import { cn } from "@/lib/utils";
import type { RecordActivityEvent } from "./record-types";

const META: Record<RecordActivityEvent["kind"],{label:string;Icon:typeof Activity}> = {
  academic:{label:"Evento acadêmico",Icon:BookOpen},contact:{label:"Contato/engajamento",Icon:MessageCircle},
  intervention:{label:"Intervenção",Icon:Shield},activity:{label:"Atividade",Icon:Activity},
  risk:{label:"Avaliação de risco",Icon:Shield},finance:{label:"Registro financeiro confirmado",Icon:Wallet},
  status:{label:"Mudança de estado",Icon:Clock3},
};
function formatDate(iso:string|null) {
  if(!iso)return "Data não informada";
  const date=new Date(iso);
  return Number.isNaN(date.getTime())?"Data não informada":new Intl.DateTimeFormat("pt-BR",{dateStyle:"medium",timeStyle:"short",timeZone:"America/Sao_Paulo"}).format(date);
}
export function RecordActivity({ events, truncated=false, emptyMessage="Nenhum evento registrado nesta fonte.", className }: {
  events: RecordActivityEvent[]; truncated?:boolean; emptyMessage?:string; className?:string;
}) {
  return <section aria-label="Atividade do registro" className={cn("rounded-[var(--radius-card)] border border-[var(--color-border)] bg-white",className)}>
    <header className="border-b border-[var(--color-border)] px-4 py-3">
      <h3 className="text-[13px] font-semibold text-[var(--color-ink)]">Atividade</h3>
      <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">Somente eventos documentados pelas fontes autorizadas.</p>
    </header>
    {events.length?<ol className="divide-y divide-[var(--color-border-subtle)]">
      {events.map(event=>{
        const meta=META[event.kind];const Icon=meta.Icon;
        return <li key={event.id} className="flex gap-3 px-4 py-3.5">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[var(--color-panel)] text-[var(--color-slate-600)]"><Icon className="h-4 w-4"/></span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-start justify-between gap-x-2">
              <p className="text-[12px] font-medium text-[var(--color-ink)]">{event.title}</p>
              <time dateTime={event.at||undefined} className="text-[10px] text-[var(--color-muted)]">{formatDate(event.at)}</time>
            </div>
            <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">{meta.label} · Origem: {event.origin}</p>
            {(event.actor||event.status)&&<p className="mt-1 text-[11px] text-[var(--color-slate-600)]">
              {event.actor?"Responsável: "+event.actor:"Responsável não informado"}{event.status?" · Estado: "+event.status:""}
            </p>}
            {event.description&&<p className="mt-1 text-[11px] text-[var(--color-slate-600)]">{event.description}</p>}
            {event.href&&<Link href={event.href} className="mt-1 inline-block text-[11px] font-medium text-[var(--color-blue)] hover:underline">Ver registro relacionado</Link>}
          </div>
        </li>;
      })}
    </ol>:<p className="px-4 py-7 text-[12px] text-[var(--color-muted)]">{emptyMessage}</p>}
    {truncated&&<p role="note" className="border-t border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2.5 text-[11px] text-[var(--color-slate-600)]">Prévia limitada: podem existir eventos adicionais na origem.</p>}
  </section>;
}
