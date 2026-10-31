import { cn } from "@/lib/utils";

export interface ProgressProps {
  value?: number | null;
  max?: number;
  className?: string;
  indicatorClassName?: string;
  label?: string;
}

export function Progress({ value, max = 100, className, indicatorClassName, label }: ProgressProps) {
  const determinate = typeof value === "number" && Number.isFinite(value);
  const safeMax = max > 0 ? max : 100;
  const percentage = determinate ? Math.min(100, Math.max(0, (value / safeMax) * 100)) : undefined;

  return (
    <div
      role="progressbar"
      aria-label={label || "Progresso"}
      aria-valuemin={determinate ? 0 : undefined}
      aria-valuemax={determinate ? safeMax : undefined}
      aria-valuenow={determinate ? Math.min(safeMax, Math.max(0, value)) : undefined}
      aria-valuetext={determinate ? `${Math.round(percentage!)}%` : "Em andamento"}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-[var(--surface-subtle)]", className)}
    >
      <div
        className={cn(
          "h-full rounded-full bg-[var(--brand-indigo)] transition-[width] duration-300 ease-out",
          !determinate && "w-1/3 animate-[mira-progress-indeterminate_1.4s_ease-in-out_infinite]",
          indicatorClassName
        )}
        style={determinate ? { width: `${percentage}%` } : undefined}
      />
    </div>
  );
}
