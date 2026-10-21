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
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
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
      ? "bg-red-50 text-red-700 ring-1 ring-red-100"
      : level === "medio"
        ? "bg-amber-50 text-amber-800 ring-1 ring-amber-100"
        : level === "baixo"
          ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100"
          : "bg-slate-100 text-slate-600 ring-1 ring-slate-200";

  return <Badge className={styles}>{riskLabel(level)}</Badge>;
}
