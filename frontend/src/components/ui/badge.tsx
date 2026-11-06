import { cn } from "@/lib/utils";
import { riskLabel } from "@/lib/utils";

export function Badge({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[var(--radius-pill)] px-2.5 py-1 text-[length:var(--type-caption)] font-semibold tracking-wide",
        className
      )}
    >
      {children}
    </span>
  );
}

export function RiskBadge({ level }: { level?: string | null }) {
  const styles =
    level === "critico"
      ? "bg-[var(--color-legacy-fff0ed)] text-[var(--color-legacy-b84336)] ring-1 ring-[var(--color-legacy-f9d8d2)]"
      : level === "medio"
        ? "bg-[var(--color-legacy-eef0ff)] text-[var(--color-legacy-3848b5)] ring-1 ring-[var(--color-legacy-dce0ff)]"
        : level === "baixo"
          ? "bg-[var(--color-legacy-edf0fb)] text-[var(--brand-blue)] ring-1 ring-[var(--color-legacy-dfe4f8)]"
          : "bg-slate-100 text-slate-600 ring-1 ring-slate-200";

  return <Badge className={styles}>{riskLabel(level)}</Badge>;
}
