"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export function StudentCampaignsPanel({ studentId, canView }: { studentId: string; canView: boolean }) {
  const logs = useQuery({
    queryKey: ["student-campaign-logs", studentId],
    queryFn: () => api.retentionLogs({ student_id: studentId, limit: 100 }),
    enabled: Boolean(studentId) && canView, retry: false, staleTime: 30_000,
  });
  if (!canView) return <p className="text-[12px] text-[var(--color-muted)]">Histórico de campanhas restrito ao perfil autorizado.</p>;
  if (logs.isLoading) return <div role="status" aria-label="Carregando campanhas" className="space-y-2">
    <Skeleton className="h-12 w-full"/><Skeleton className="h-12 w-full"/>
  </div>;
  if (logs.isError) return <div role="alert" className="space-y-2 text-[12px] text-[var(--color-red)]">Não foi possível consultar o histórico.
    <button type="button" onClick={() => void logs.refetch()} className="font-medium underline">Tentar novamente</button>
  </div>;
  const byCampaign = new Map<string, number>();
  for (const item of logs.data?.logs || []) if (item.campaign_id) byCampaign.set(item.campaign_id, (byCampaign.get(item.campaign_id) || 0) + 1);
  return <div className="space-y-3 text-[12px]">
    <p className="text-[var(--color-slate-600)]">Campanhas com registros de contato para este aluno (até 100 registros consultados).</p>
    {byCampaign.size ? <ul className="space-y-2">{[...byCampaign.entries()].map(([id,count]) =>
      <li key={id} className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2">
        <span className="font-medium">Campanha {id.slice(0, 8)}…</span>
        <span className="ml-2 text-[var(--color-muted)]">{count} registro(s)</span>
      </li>)}</ul> : <p className="rounded-[var(--radius-md)] bg-[var(--color-panel)] p-3 text-[var(--color-muted)]">Nenhuma campanha vinculada aos contatos consultados.</p>}
    <Link href="/campanhas" className="inline-flex font-medium text-[var(--color-blue)] hover:underline">Ver campanhas do workspace</Link>
  </div>;
}
