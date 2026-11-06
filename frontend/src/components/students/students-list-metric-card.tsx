"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  hint,
  icon,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  icon: ReactNode;
  tone: "neutral" | "coral" | "blue";
}) {
  return (
    <article
      className={cn(
        "rounded-xl border border-[var(--color-legacy-e5e7eb)] bg-white p-4",
        tone === "coral" && "border-[var(--color-legacy-fecdca)]",
        tone === "blue" && "border-[var(--color-source-bfdbfe)]"
      )}
    >
      <div className="flex items-center gap-2 text-[var(--color-legacy-667085)]">
        <span
          className={cn(
            "grid h-8 w-8 place-items-center rounded-lg bg-[var(--color-legacy-f8fafc)]",
            tone === "coral" && "bg-[var(--color-red-tint)] text-[var(--color-legacy-b42318)]",
            tone === "blue" && "bg-[var(--color-source-eff6ff)] text-[var(--color-legacy-2563eb)]"
          )}
        >
          {icon}
        </span>
        <p className="text-xs font-medium">{label}</p>
      </div>
      <p className="mt-4 text-[length:var(--type-display-medium)] font-semibold leading-none tracking-[-0.04em] tabular-nums text-[var(--color-legacy-111827)]">
        {value}
      </p>
      <p className="mt-2 text-[length:var(--type-caption)] leading-snug text-[var(--color-legacy-667085)]">{hint}</p>
    </article>
  );
}
