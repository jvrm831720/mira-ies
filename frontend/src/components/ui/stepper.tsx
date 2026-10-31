"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export type StepItem = {
  id: string;
  label: string;
  description?: string;
};

type StepperProps = {
  steps: StepItem[];
  /** Zero-based index of the current step */
  current: number;
  className?: string;
};

export function Stepper({ steps, current, className }: StepperProps) {
  return (
    <ol
      className={cn("flex w-full flex-col gap-4 sm:flex-row sm:items-start sm:gap-0", className)}
      aria-label="Progresso do fluxo"
    >
      {steps.map((step, index) => {
        const done = index < current;
        const active = index === current;
        const isLast = index === steps.length - 1;
        return (
          <li
            key={step.id}
            className={cn("relative flex min-w-0 flex-1 items-start gap-2.5 sm:flex-col sm:items-center sm:text-center")}
            aria-current={active ? "step" : undefined}
          >
            {!isLast ? (
              <span
                aria-hidden
                className={cn(
                  "absolute left-[1.125rem] top-7 h-[calc(100%-1.75rem)] w-px sm:left-[calc(50%+14px)] sm:right-0 sm:top-3.5 sm:h-px sm:w-[calc(100%-28px)]",
                  done ? "bg-[var(--brand-indigo)]" : "bg-[var(--border-subtle)]"
                )}
              />
            ) : null}
            <span
              className={cn(
                "relative z-[1] grid h-7 w-7 shrink-0 place-items-center rounded-full border text-xs font-semibold transition",
                done && "border-[var(--brand-indigo)] bg-[var(--brand-indigo)] text-white",
                active &&
                  !done &&
                  "border-[var(--brand-indigo)] bg-[var(--brand-indigo)]/10 text-[var(--brand-indigo)] ring-4 ring-[var(--brand-indigo)]/10",
                !done &&
                  !active &&
                  "border-[var(--border-subtle)] bg-[var(--surface-card)] text-[var(--text-secondary)]"
              )}
            >
              {done ? <Check className="h-3.5 w-3.5" aria-hidden /> : index + 1}
            </span>
            <span className="min-w-0 pt-0.5 sm:max-w-[7.5rem] sm:pt-2">
              <span
                className={cn(
                  "block text-sm font-medium leading-tight",
                  active || done ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                )}
              >
                {step.label}
              </span>
              {step.description ? (
                <span className="mt-0.5 block text-[11px] leading-snug text-[var(--text-secondary)] sm:hidden">
                  {step.description}
                </span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
