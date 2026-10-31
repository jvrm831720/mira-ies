import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface StepperStep {
  id: string;
  label: string;
  description?: string;
}

export function Stepper({
  steps,
  currentStep,
  className,
}: {
  steps: StepperStep[];
  currentStep: number;
  className?: string;
}) {
  return (
    <nav aria-label="Progresso das etapas" className={className}>
      <ol className="flex w-full items-start">
        {steps.map((step, index) => {
          const complete = index < currentStep;
          const current = index === currentStep;
          return (
            <li key={step.id} className={cn("relative flex min-w-0 flex-1 flex-col items-center text-center", index !== steps.length - 1 && "after:absolute after:left-1/2 after:top-4 after:h-px after:w-full after:bg-[var(--border-subtle)] after:content-['']")}>
              <span
                aria-current={current ? "step" : undefined}
                className={cn(
                  "relative z-10 flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold transition-colors",
                  complete && "border-[var(--brand-indigo)] bg-[var(--brand-indigo)] text-white",
                  current && "border-[var(--brand-indigo)] bg-white text-[var(--brand-indigo)] ring-4 ring-[var(--brand-indigo)]/10",
                  !complete && !current && "border-[var(--border-strong)] bg-white text-[var(--text-secondary)]"
                )}
              >
                {complete ? <Check aria-hidden="true" className="h-4 w-4" /> : index + 1}
              </span>
              <span className={cn("mt-2 text-xs font-medium", current ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]")}>{step.label}</span>
              {step.description && <span className="mt-1 hidden max-w-28 text-[11px] text-[var(--text-secondary)] sm:block">{step.description}</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
