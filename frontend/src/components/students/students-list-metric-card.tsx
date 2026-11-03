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
        "rounded-xl border border-[#E5E7EB] bg-white p-4",
        tone === "coral" && "border-[#FECDCA]",
        tone === "blue" && "border-[#BFDBFE]"
      )}
    >
      <div className="flex items-center gap-2 text-[#667085]">
        <span
          className={cn(
            "grid h-8 w-8 place-items-center rounded-lg bg-[#F8FAFC]",
            tone === "coral" && "bg-[#FEF3F2] text-[#B42318]",
            tone === "blue" && "bg-[#EFF6FF] text-[#2563EB]"
          )}
        >
          {icon}
        </span>
        <p className="text-[12px] font-medium">{label}</p>
      </div>
      <p className="mt-4 text-[28px] font-semibold leading-none tracking-[-0.04em] tabular-nums text-[#111827]">
        {value}
      </p>
      <p className="mt-2 text-[11px] leading-snug text-[#667085]">{hint}</p>
    </article>
  );
}
