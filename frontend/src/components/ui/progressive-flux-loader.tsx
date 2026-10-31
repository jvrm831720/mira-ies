"use client";

import { AlertCircle, CheckCircle2, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";

export type FluxPhase =
  | "idle"
  | "receiving"
  | "validating_structure"
  | "analyzing"
  | "inconsistencies"
  | "preparing"
  | "scoring"
  | "consolidating"
  | "finishing"
  | "success"
  | "error";

const PHASE_COPY: Record<Exclude<FluxPhase, "idle">, string> = {
  receiving: "Recebendo arquivos",
  validating_structure: "Validando estrutura",
  analyzing: "Analisando registros",
  inconsistencies: "Identificando inconsistências",
  preparing: "Preparando dados",
  scoring: "Calculando scores",
  consolidating: "Consolidando resultados",
  finishing: "Finalizando processamento",
  success: "Processamento concluído",
  error: "Falha no processamento",
};

const PHASE_ORDER: Exclude<FluxPhase, "idle" | "success" | "error">[] = [
  "receiving",
  "validating_structure",
  "analyzing",
  "inconsistencies",
  "preparing",
  "scoring",
  "consolidating",
  "finishing",
];

type ProgressiveFluxLoaderProps = {
  phase: FluxPhase;
  /** Optional real percentage from backend; never invent when absent */
  percent?: number | null;
  detail?: string;
  errorMessage?: string | null;
  className?: string;
  compact?: boolean;
};

export function ProgressiveFluxLoader({
  phase,
  percent,
  detail,
  errorMessage,
  className,
  compact,
}: ProgressiveFluxLoaderProps) {
  if (phase === "idle") return null;

  const isError = phase === "error";
  const isSuccess = phase === "success";
  const activeIndex = PHASE_ORDER.indexOf(phase as (typeof PHASE_ORDER)[number]);
  const hasPercent = typeof percent === "number" && !Number.isNaN(percent);

  return (
    <div
      className={cn(
        "rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-card)]",
        compact ? "p-3" : "p-4 sm:p-5",
        className
      )}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "grid h-9 w-9 shrink-0 place-items-center rounded-xl",
            isError && "bg-red-50 text-red-600",
            isSuccess && "bg-emerald-50 text-emerald-700",
            !isError && !isSuccess && "bg-[var(--surface-subtle)] text-[var(--brand-indigo)]"
          )}
        >
          {isError ? (
            <AlertCircle className="h-4 w-4" />
          ) : isSuccess ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : (
            <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" />
          )}
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {PHASE_COPY[phase]}
            </p>
            {detail ? <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{detail}</p> : null}
            {isError && errorMessage ? (
              <p className="mt-1 text-xs text-red-700">{errorMessage}</p>
            ) : null}
          </div>

          {!isError && !isSuccess ? (
            <Progress
              value={hasPercent ? percent : null}
              indeterminate={!hasPercent}
              label={hasPercent ? "Progresso informado pela API" : "Aguardando status do processamento"}
            />
          ) : null}

          {!compact && !isError ? (
            <ol className="mt-2 grid gap-1.5 sm:grid-cols-2">
              {PHASE_ORDER.map((id, index) => {
                const done = isSuccess || (activeIndex >= 0 && index < activeIndex);
                const current = !isSuccess && index === activeIndex;
                return (
                  <li
                    key={id}
                    className={cn(
                      "flex items-center gap-2 text-xs",
                      done && "text-emerald-700",
                      current && "font-medium text-[var(--brand-indigo)]",
                      !done && !current && "text-[var(--text-secondary)]"
                    )}
                  >
                    <span
                      className={cn(
                        "h-1.5 w-1.5 rounded-full",
                        done && "bg-emerald-600",
                        current && "bg-[var(--brand-indigo)]",
                        !done && !current && "bg-[var(--border-strong)]"
                      )}
                    />
                    {PHASE_COPY[id]}
                  </li>
                );
              })}
            </ol>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Map common import/processing flags to a flux phase without inventing progress. */
export function phaseFromFlags(flags: {
  previewLoading?: boolean;
  uploadLoading?: boolean;
  multiPreviewLoading?: boolean;
  multiConfirmationLoading?: boolean;
  error?: boolean;
  success?: boolean;
}): FluxPhase {
  if (flags.error) return "error";
  if (flags.success) return "success";
  if (flags.previewLoading || flags.multiPreviewLoading) return "validating_structure";
  if (flags.uploadLoading || flags.multiConfirmationLoading) return "preparing";
  return "idle";
}
