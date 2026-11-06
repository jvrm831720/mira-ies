"use client";
import { useQuery } from "@tanstack/react-query";
import { workApi } from "@/lib/work-api";
import { RecordActivity } from "./record-activity";
import { fromStudentWorkTimeline } from "./record-activity-utils";
import { Skeleton } from "@/components/ui/skeleton";
export function StudentRecordActivity({studentId,canView}:{studentId:string;canView:boolean}) {
  const q=useQuery({
    queryKey:["student-work-timeline",studentId],
    queryFn:()=>workApi.getTimeline(studentId,100),
    enabled:Boolean(studentId)&&canView,retry:false,staleTime:30_000,
  });
  if(!canView)return <p className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-panel)] p-4 text-[12px] text-[var(--color-slate-600)]">Histórico restrito ao perfil autorizado.</p>;
  if(q.isLoading)return <div role="status" aria-label="Carregando atividades" className="space-y-2"><Skeleton className="h-16 w-full"/><Skeleton className="h-16 w-full"/></div>;
  if(q.isError)return <div role="alert" className="rounded-[var(--radius-md)] border border-[var(--color-border)] p-4 text-[12px] text-[var(--color-slate-600)]">
    Não foi possível consultar a atividade registrada.
    <button type="button" className="ml-2 font-medium text-[var(--color-blue)]" onClick={()=>void q.refetch()}>Tentar novamente</button>
  </div>;
  return <RecordActivity events={fromStudentWorkTimeline(q.data?.items||[])}
    truncated={Boolean(q.data?.truncated)||Boolean(q.data&&q.data.count>=q.data.limit)} />;
}
