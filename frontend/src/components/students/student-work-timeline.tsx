"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  History,
  MessageSquare,
  RefreshCw,
  Shield,
  Sparkles,
} from "lucide-react";
import { workApi } from "@/lib/work-api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { WorkTimelineItem, WorkTimelineSource } from "@/types/work";

const SOURCE_META: Record<
  string,
  { label: string; icon: typeof Shield; accent: string; bg: string; ring: string }
> = {
  risk_assessment: {
    label: "Risco",
    icon: Shield,
    accent: "text-[#B54708]",
    bg: "bg-[#FFFAEB]",
    ring: "ring-[#FEC84B]",
  },
  intervention_log: {
    label: "Intervenção",
    icon: MessageSquare,
    accent: "text-[#175CD3]",
    bg: "bg-[#EFF8FF]",
    ring: "ring-[#84CAFF]",
  },
  work_activity: {
    label: "Atividade",
    icon: Activity,
    accent: "text-[#027A48]",
    bg: "bg-[#ECFDF3]",
    ring: "ring-[#6CE9A6]",
  },
  engagement_event: {
    label: "Engajamento",
    icon: Sparkles,
    accent: "text-[#6941C6]",
    bg: "bg-[#F9F5FF]",
    ring: "ring-[#D6BBFB]",
  },
};

function formatDateTime(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function humanSummary(item: WorkTimelineItem): string {
  const refs = item.refs || {};
  if (item.source === "risk_assessment") {
    const level = refs.risk_level != null ? String(refs.risk_level) : null;
    const score = refs.score != null ? String(refs.score) : null;
    const parts = ["Avaliação de risco"];
    if (level) parts.push(level);
    if (score) parts.push(`score ${score}`);
    return parts.join(" · ");
  }
  if (item.source === "intervention_log") {
    const status = refs.status != null ? String(refs.status) : null;
    const channel = refs.channel != null ? String(refs.channel) : null;
    const delivery = refs.delivery_status != null ? String(refs.delivery_status) : null;
    const outcome = refs.outcome != null ? String(refs.outcome) : null;
    const parts: string[] = [];
    if (status) parts.push(`Status: ${status}`);
    if (channel) parts.push(`Canal: ${channel}`);
    if (delivery) parts.push(`Entrega: ${delivery}`);
    if (outcome) parts.push(`Outcome: ${outcome}`);
    else parts.push("Outcome: não registrado");
    return parts.join(" · ") || item.summary;
  }
  if (item.source === "work_activity") {
    const eventType = refs.event_type != null ? String(refs.event_type) : null;
    if (eventType === "result_recorded") {
      const payload = (refs.payload as Record<string, unknown> | undefined) || {};
      const kind = payload.kind != null ? String(payload.kind) : null;
      const note = payload.note != null ? String(payload.note) : null;
      let s = "Resultado operacional registrado";
      if (kind) s += ` (${kind})`;
      if (note) s += `: ${note}`;
      return s;
    }
    const title = refs.title != null ? String(refs.title) : null;
    const status = refs.status != null ? String(refs.status) : null;
    if (title) return status ? `Atividade [${status}] ${title}` : `Atividade: ${title}`;
  }
  if (item.source === "engagement_event") {
    const et = refs.event_type != null ? String(refs.event_type) : null;
    const ch = refs.channel != null ? String(refs.channel) : null;
    if (et) return ch ? `Engajamento: ${et} (${ch})` : `Engajamento: ${et}`;
  }
  return item.summary;
}

function relatedLink(item: WorkTimelineItem): { href: string; label: string } | null {
  const refs = item.refs || {};
  if (item.source === "work_activity") {
    const activityId =
      (refs.activity_id as string | undefined) ||
      (refs.event_type === "created" || !refs.event_type ? item.id : undefined);
    if (activityId && typeof activityId === "string") {
      return { href: `/trabalho?activity=${activityId}`, label: "Ver atividade" };
    }
  }
  if (item.source === "intervention_log") {
    return { href: `/retencao/logs?log=${item.id}`, label: "Ver intervenção" };
  }
  return null;
}

export function StudentWorkTimeline({
  studentId,
  compact = false,
  className,
}: {
  studentId: string;
  compact?: boolean;
  className?: string;
}) {
  const q = useQuery({
    queryKey: ["student-work-timeline", studentId],
    queryFn: () => workApi.getTimeline(studentId, 100),
    enabled: Boolean(studentId),
    retry: 1,
  });

  const itemsNewestFirst = [...(q.data?.items || [])].reverse();
  const truncated = Boolean(q.data?.truncated) || (q.data != null && q.data.count >= q.data.limit);

  return (
    <section
      className={cn("rounded-xl border border-[#E5E7EB] bg-white", className)}
      data-student-work-timeline
      aria-label="Histórico operacional do aluno"
    >
      <div className="flex items-start gap-3 border-b border-[#E5E7EB] px-4 py-3.5 sm:px-5">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#F8FAFC] text-[#667085]">
          <History className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] font-semibold text-[#111827]">Histórico operacional</h2>
          <p className="mt-0.5 text-[12px] leading-relaxed text-[#667085]">
            Eventos reais de risco, intervenções, atividades e engajamento. Ausência de registro
            não significa ausência de risco.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void q.refetch()}
          disabled={q.isFetching}
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-[#E5E7EB] bg-white px-2.5 text-[11px] font-medium text-[#344054] hover:bg-[#F8FAFC] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
          aria-label="Atualizar histórico"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", q.isFetching && "animate-spin")} />
          Atualizar
        </button>
      </div>

      <div className={cn("px-4 py-4 sm:px-5", compact ? "max-h-[420px] overflow-y-auto" : "")}>
        {q.isLoading && (
          <div className="space-y-3" role="status" aria-label="Carregando histórico">
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        )}

        {q.isError && (
          <div
            role="alert"
            className="rounded-xl border border-[#FECDCA] bg-[#FEF3F2] px-4 py-4 text-center"
          >
            <span className="mx-auto grid h-10 w-10 place-items-center rounded-lg bg-white text-[#B42318]">
              <AlertCircle className="h-5 w-5" />
            </span>
            <p className="mt-3 text-[13px] font-semibold text-[#111827]">
              Não foi possível carregar o histórico.
            </p>
            <p className="mt-1 text-[12px] text-[#667085]">
              A consulta à timeline falhou. Tente novamente.
            </p>
            <button
              type="button"
              onClick={() => void q.refetch()}
              className="mt-3 text-[12px] font-semibold text-[#B42318] underline underline-offset-2"
            >
              Tentar novamente
            </button>
          </div>
        )}

        {!q.isLoading && !q.isError && itemsNewestFirst.length === 0 && (
          <div className="rounded-xl border border-dashed border-[#E5E7EB] bg-[#F8FAFC] px-4 py-8 text-center">
            <p className="text-[13px] font-medium text-[#344054]">Nenhum evento registrado</p>
            <p className="mt-1 text-[12px] leading-relaxed text-[#667085]">
              Ainda não há avaliações de risco, intervenções, atividades ou engajamentos
              persistidos para este aluno.
            </p>
          </div>
        )}

        {!q.isLoading && !q.isError && itemsNewestFirst.length > 0 && (
          <>
            {truncated && (
              <div
                role="status"
                className="mb-3 rounded-lg border border-[#FEE4E2] bg-[#FEF3F2] px-3 py-2 text-[11px] leading-relaxed text-[#B42318]"
              >
                Histórico limitado: a lista exibida pode não conter todos os eventos (limite de{" "}
                {q.data?.limit ?? 100}).
              </div>
            )}
            <ol className="relative space-y-0">
              {itemsNewestFirst.map((item, index) => {
                const meta =
                  SOURCE_META[item.source as WorkTimelineSource] || SOURCE_META.work_activity;
                const Icon = meta.icon;
                const when = formatDateTime(item.at);
                const link = relatedLink(item);
                const isLast = index === itemsNewestFirst.length - 1;
                return (
                  <li key={`${item.source}-${item.id}-${index}`} className="relative flex gap-3 pb-4">
                    {!isLast && (
                      <span
                        className="absolute left-[15px] top-8 bottom-0 w-px bg-[#E5E7EB]"
                        aria-hidden
                      />
                    )}
                    <span
                      className={cn(
                        "relative z-[1] grid h-8 w-8 shrink-0 place-items-center rounded-full ring-2 ring-offset-1",
                        meta.bg,
                        meta.accent,
                        meta.ring
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" />
                    </span>
                    <div className="min-w-0 flex-1 pt-0.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[10px] font-semibold",
                            meta.bg,
                            meta.accent
                          )}
                        >
                          {meta.label}
                        </span>
                        {when && (
                          <time
                            dateTime={item.at || undefined}
                            className="text-[11px] tabular-nums text-[#98A2B3]"
                          >
                            {when}
                          </time>
                        )}
                      </div>
                      <p className="mt-1.5 text-[13px] leading-relaxed text-[#111827]">
                        {humanSummary(item)}
                      </p>
                      {item.source === "risk_assessment" && item.refs?.model_version != null && (
                        <p className="mt-1 text-[11px] text-[#98A2B3]">
                          Modelo: {String(item.refs.model_version)}
                        </p>
                      )}
                      {link && (
                        <Link
                          href={link.href}
                          className="mt-1.5 inline-flex text-[11px] font-semibold text-[#2563EB] hover:underline"
                        >
                          {link.label}
                        </Link>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </div>
    </section>
  );
}
