"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

type EmptyStateProps = {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
};

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-dashed border-[var(--border-subtle)] bg-[var(--surface-card)] px-6 py-10 text-center",
        className
      )}
    >
      {icon ? (
        <div className="mb-3 grid h-11 w-11 place-items-center rounded-2xl bg-[var(--surface-subtle)] text-[var(--text-secondary)]">
          {icon}
        </div>
      ) : null}
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
      {description ? (
        <p className="mt-1.5 max-w-sm text-sm text-[var(--text-secondary)]">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
