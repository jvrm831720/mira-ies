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
      className={cn(
        "flex w-full flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-2",
        className
      )}
      aria-label="Progresso do fluxo"
    >
      {steps.map((step, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li
            key={step.id}
            className={cn(
              "flex min-w-0 flex-1 items-start gap-2.5",
              index < steps.length - 1 && "sm:pr-2"
            )}
            aria-current={active ? "step" : undefined}
          >
            <span
              className={cn(
                "grid h-7 w-7 shrink-0 place-items-center rounded-full border text-xs font-semibold transition",
                done && "border-[var(--brand-indigo)] bg-[var(--brand-indigo)] text-white",
                active &&
                  !done &&
                  "border-[var(--brand-indigo)] bg-[var(--brand-indigo)]/10 text-[var(--brand-indigo)]",
                !done &&
                  !active &&
                  "border-[var(--border-subtle)] bg-[var(--surface-card)] text-[var(--text-secondary)]"
              )}
            >
              {done ? <Check className="h-3.5 w-3.5" aria-hidden /> : index + 1}
            </span>
            <span className="min-w-0 pt-0.5">
              <span
                className={cn(
                  "block text-sm font-medium",
                  active || done ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                )}
              >
                {step.label}
              </span>
              {step.description ? (
                <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">{step.description}</span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
