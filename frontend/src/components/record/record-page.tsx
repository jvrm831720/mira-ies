import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft } from "@/components/ui/icons";
import { RecordHeading } from "./record-heading";
import { RecordActions } from "./record-actions";
import type { RecordAction, RecordIdentity } from "./record-types";

export function RecordPage({ record, status, actions=[], backHref, children, aside }: {
  record:RecordIdentity; backHref:string; status?:ReactNode; actions?:RecordAction[]; children:ReactNode; aside?:ReactNode;
}) {
  return <div className="mira-page mx-auto w-full max-w-[1500px] px-4 pb-10 pt-5 md:px-8 md:pt-6">
    <nav aria-label="Localização do registro" className="mb-4">
      <Link href={backHref} className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-slate-600)] hover:text-[var(--color-blue)]">
        <ArrowLeft className="h-4 w-4"/> Voltar à lista
      </Link>
    </nav>
    <header className="mb-5 flex flex-wrap items-start justify-between gap-4 border-b border-[var(--color-border)] pb-5">
      <RecordHeading record={record} status={status}/>
      <RecordActions actions={actions}/>
    </header>
    <div className={aside?"grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_300px]":"min-w-0"}>
      <div className="min-w-0">{children}</div>
      {aside&&<aside aria-label="Propriedades do registro" className="min-w-0 space-y-4 xl:sticky xl:top-5 xl:self-start">{aside}</aside>}
    </div>
  </div>;
}
