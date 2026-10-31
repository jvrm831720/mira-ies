import { cn } from "@/lib/utils";
import { riskLabel } from "@/lib/utils";

const badgeVariants = {
  default: "bg-[var(--surface-subtle)] text-[var(--text-primary)]",
  secondary: "bg-slate-100 text-slate-700",
  outline: "border border-[var(--border-subtle)] bg-white text-[var(--text-primary)]",
  success: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  warning: "bg-amber-50 text-amber-800 ring-1 ring-amber-200",
  destructive: "bg-red-50 text-red-700 ring-1 ring-red-200",
  info: "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
} as const;

export function Badge({
  className,
  children,
  variant = "default",
}: {
  className?: string;
  children: React.ReactNode;
  variant?: keyof typeof badgeVariants;
}) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-wide", badgeVariants[variant], className)}>
      {children}
    </span>
  );
}

export function RiskBadge({ level }: { level?: string | null }) {
  const styles =
    level === "critico"
      ? "bg-[#fff0ed] text-[#b84336] ring-1 ring-[#f9d8d2]"
      : level === "medio"
        ? "bg-[#eef0ff] text-[#3848b5] ring-1 ring-[#dce0ff]"
        : level === "baixo"
          ? "bg-[#edf0fb] text-[#29399f] ring-1 ring-[#dfe4f8]"
          : "bg-slate-100 text-slate-600 ring-1 ring-slate-200";

  return <Badge className={styles}>{riskLabel(level)}</Badge>;
}
