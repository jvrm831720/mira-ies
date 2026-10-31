"use client";

import { cn } from "@/lib/utils";

type ProgressProps = {
  /** 0–100 when known; omit or null when percentage is unknown */
  value?: number | null;
  label?: string;
  indeterminate?: boolean;
  className?: string;
};

export function Progress({ value, label, indeterminate, className }: ProgressProps) {
  const known = typeof value === "number" && !Number.isNaN(value);
  const clamped = known ? Math.max(0, Math.min(100, value)) : 0;
  const showIndeterminate = indeterminate || !known;

  return (
    <div className={cn("space-y-1.5", className)}>
      {label ? (
        <div className="flex items-center justify-between gap-2 text-xs text-[var(--text-secondary)]">
          <span>{label}</span>
          {known && !indeterminate ? <span className="tabular-nums">{Math.round(clamped)}%</span> : null}
        </div>
      ) : null}
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={showIndeterminate ? undefined : clamped}
        aria-valuetext={showIndeterminate ? label || "Em andamento" : undefined}
        className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-subtle)]"
      >
        <div
          className={cn(
            "h-full rounded-full bg-[var(--brand-indigo)] transition-[width] duration-[var(--motion-standard)]",
            showIndeterminate && "w-1/3 animate-pulse"
          )}
          style={showIndeterminate ? undefined : { width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
