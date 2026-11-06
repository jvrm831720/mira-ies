import type { ReactNode } from "react";
"use client";
import { useEffect, useId, useRef } from "react";
import Link from "next/link";
import { ExternalLink, X } from "@/components/ui/icons";
import { RecordHeading } from "./record-heading";
import { RecordActions } from "./record-actions";
import type { RecordAction, RecordIdentity } from "./record-types";

type Props={
  record: RecordIdentity | null; onClose: () => void;
  fullPageHref?: string; status?: ReactNode;
  actions?: RecordAction[]; children: ReactNode;
};
export function RecordDrawer({ record,onClose,fullPageHref,status,actions=[],children }:Props) {
  const onCloseRef=useRef(onClose);
  useEffect(()=>{onCloseRef.current=onClose;},[onClose]);
  const titleId=useId();const dialogRef=useRef<HTMLElement>(null);const origin=useRef<HTMLElement|null>(null);
  const recordId=record?.id;
  useEffect(()=>{
    if(!recordId)return;
    origin.current=document.activeElement instanceof HTMLElement?document.activeElement:null;
    const previous=document.body.style.overflow;document.body.style.overflow="hidden";
    dialogRef.current?.focus();
    const trap=(event:KeyboardEvent)=>{
      if(event.key==="Escape"){event.preventDefault();onCloseRef.current();return;}
      if(event.key!=="Tab")return;
      const controls=Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
        'a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])'
      )||[]);
      if(!controls.length){event.preventDefault();dialogRef.current?.focus();return;}
      const first=controls[0],last=controls[controls.length-1];
      if(event.shiftKey&&(document.activeElement===first||document.activeElement===dialogRef.current)){
        event.preventDefault();last.focus();
      }else if(!event.shiftKey&&(document.activeElement===last||!dialogRef.current?.contains(document.activeElement))){
        event.preventDefault();first.focus();
      }
    };
    window.addEventListener("keydown",trap);
    return ()=>{window.removeEventListener("keydown",trap);document.body.style.overflow=previous;origin.current?.focus();};
  },[recordId]);
  if(!record)return null;
  return <div className="fixed inset-0 z-[70] flex justify-end">
    <button type="button" tabIndex={-1} aria-label="Fechar visualização"
      onClick={onClose} className="absolute inset-0 bg-[var(--color-ink)]/35" />
    <aside ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true"
      aria-labelledby={titleId} aria-label={"Registro: "+record.title}
      className="relative flex h-dvh w-full max-w-[570px] min-w-0 flex-col border-l border-[var(--color-border)] bg-white shadow-[var(--shadow-overlay)] focus:outline-none motion-safe:animate-none sm:w-[min(570px,94vw)]">
      <header className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-4 sm:px-6">
        <div id={titleId} className="min-w-0 flex-1">
          <RecordHeading record={record} compact status={status} />
        </div>
        <div className="flex shrink-0 gap-1">
          {fullPageHref&&<Link href={fullPageHref} aria-label="Abrir ficha completa"
            className="grid h-8 w-8 place-items-center rounded-[var(--radius-md)] text-[var(--color-slate-600)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]"><ExternalLink className="h-4 w-4"/></Link>}
          <button type="button" onClick={onClose} aria-label="Fechar painel"
            className="grid h-8 w-8 place-items-center rounded-[var(--radius-md)] text-[var(--color-slate-600)] hover:bg-[var(--color-panel)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]"><X className="h-4 w-4"/></button>
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">{children}</div>
      {(fullPageHref||actions.length>0)&&<footer className="shrink-0 border-t border-[var(--color-border)] bg-white p-3 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <RecordActions actions={actions}/>
          {fullPageHref&&<Link href={fullPageHref}
            className="inline-flex h-9 items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-ink)] px-3 text-xs font-semibold text-white hover:bg-[var(--color-ink-900)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]">
            Abrir ficha completa <ExternalLink className="h-3.5 w-3.5"/>
          </Link>}
        </div>
      </footer>}
    </aside>
  </div>;
}
