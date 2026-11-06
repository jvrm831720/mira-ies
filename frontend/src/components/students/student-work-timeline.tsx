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
} from "@/components/ui/icons";
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
    accent: "text-[var(--color-source-b54708)]",
    bg: "bg-[var(--color-source-fffaeb)]",
    ring: "ring-[var(--color-legacy-fec84b)]",
  },
  intervention_log: {
    label: "Intervenção",
    icon: MessageSquare,
    accent: "text-[var(--color-legacy-175cd3)]",
    bg: "bg-[var(--color-legacy-eff8ff)]",
    ring: "ring-[var(--color-legacy-84caff)]",
  },
  work_activity: {
    label: "Atividade",
    icon: Activity,
    accent: "text-[var(--color-source-027a48)]",
    bg: "bg-[var(--color-source-ecfdf3)]",
    ring: "ring-[var(--color-legacy-6ce9a6)]",
  },
  engagement_event: {
    label: "Engajamento",
    icon: Sparkles,
    accent: "text-[var(--color-legacy-6941c6)]",
    bg: "bg-[var(--color-legacy-f9f5ff)]",
    ring: "ring-[var(--color-legacy-d6bbfb)]",
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
    const origin = refs.origin_type === "campaign" ? "de campanha" : "da equipe";
    const priority = refs.priority != null ? ` · prioridade ${String(refs.priority)}` : "";
    if (title) return status ? `Atividade ${origin} [${status}] ${title}${priority}` : `Atividade: ${title}${priority}`;
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
      className={cn("rounded-xl border border-[var(--color-legacy-e5e7eb)] bg-white", className)}
      data-student-work-timeline
      aria-label="Histórico operacional do aluno"
    >
      <div className="flex items-start gap-3 border-b border-[var(--color-legacy-e5e7eb)] px-4 py-3.5 sm:px-5">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-legacy-f8fafc)] text-[var(--color-legacy-667085)]">
          <History className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[length:var(--type-body-comfort)] font-semibold text-[var(--color-legacy-111827)]">Histórico operacional</h2>
          <p className="mt-0.5 text-xs leading-relaxed text-[var(--color-legacy-667085)]">
            Eventos reais de risco, intervenções, atividades e engajamento. Ausência de registro
            não significa ausência de risco.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void q.refetch()}
          disabled={q.isFetching}
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-[var(--color-legacy-e5e7eb)] bg-white px-2.5 text-[length:var(--type-caption)] font-medium text-[var(--color-legacy-344054)] hover:bg-[var(--color-legacy-f8fafc)] disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-legacy-2563eb)]"
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
            className="rounded-xl border border-[var(--color-legacy-fecdca)] bg-[var(--color-red-tint)] px-4 py-4 text-center"
          >
            <span className="mx-auto grid h-10 w-10 place-items-center rounded-lg bg-white text-[var(--color-legacy-b42318)]">
              <AlertCircle className="h-5 w-5" />
            </span>
            <p className="mt-3 text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-111827)]">
              Não foi possível carregar o histórico.
            </p>
            <p className="mt-1 text-xs text-[var(--color-legacy-667085)]">
              A consulta à timeline falhou. Tente novamente.
            </p>
            <button
              type="button"
              onClick={() => void q.refetch()}
              className="mt-3 text-xs font-semibold text-[var(--color-legacy-b42318)] underline underline-offset-2"
            >
              Tentar novamente
            </button>
          </div>
        )}

        {!q.isLoading && !q.isError && itemsNewestFirst.length === 0 && (
          <div className="rounded-xl border border-dashed border-[var(--color-legacy-e5e7eb)] bg-[var(--color-legacy-f8fafc)] px-4 py-8 text-center">
            <p className="text-[length:var(--type-body-compact)] font-medium text-[var(--color-legacy-344054)]">Nenhum evento registrado</p>
            <p className="mt-1 text-xs leading-relaxed text-[var(--color-legacy-667085)]">
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
                className="mb-3 rounded-lg border border-[var(--color-legacy-fee4e2)] bg-[var(--color-red-tint)] px-3 py-2 text-[length:var(--type-caption)] leading-relaxed text-[var(--color-legacy-b42318)]"
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
                        className="absolute left-[15px] top-8 bottom-0 w-px bg-[var(--color-legacy-e5e7eb)]"
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
                            "rounded-full px-2 py-0.5 text-[length:var(--type-overline)] font-semibold",
                            meta.bg,
                            meta.accent
                          )}
                        >
                          {meta.label}
                        </span>
                        {when && (
                          <time
                            dateTime={item.at || undefined}
                            className="text-[length:var(--type-caption)] tabular-nums text-[var(--color-legacy-98a2b3)]"
                          >
                            {when}
                          </time>
                        )}
                      </div>
                      <p className="mt-1.5 text-[length:var(--type-body-compact)] leading-relaxed text-[var(--color-legacy-111827)]">
                        {humanSummary(item)}
                      </p>
                      {item.source === "risk_assessment" && item.refs?.model_version != null && (
                        <p className="mt-1 text-[length:var(--type-caption)] text-[var(--color-legacy-98a2b3)]">
                          Modelo: {String(item.refs.model_version)}
                        </p>
                      )}
                      {link && (
                        <Link
                          href={link.href}
                          className="mt-1.5 inline-flex text-[length:var(--type-caption)] font-semibold text-[var(--color-legacy-2563eb)] hover:underline"
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
