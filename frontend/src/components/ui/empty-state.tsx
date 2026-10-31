import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-h-48 flex-col items-center justify-center rounded-[var(--radius-card)] border border-dashed border-[var(--border-strong)] bg-[var(--surface-card)] px-6 py-10 text-center", className)}>
      {Icon && <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-subtle)] text-[var(--text-secondary)]"><Icon aria-hidden="true" className="h-5 w-5" /></span>}
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
      {description && <p className="mt-1.5 max-w-md text-sm leading-6 text-[var(--text-secondary)]">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
