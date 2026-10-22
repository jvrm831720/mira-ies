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
        "inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-wide",
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
      ? "bg-[#fff0ed] text-[#b84336] ring-1 ring-[#f9d8d2]"
      : level === "medio"
        ? "bg-[#eef0ff] text-[#3848b5] ring-1 ring-[#dce0ff]"
        : level === "baixo"
          ? "bg-[#edf0fb] text-[#29399f] ring-1 ring-[#dfe4f8]"
          : "bg-slate-100 text-slate-600 ring-1 ring-slate-200";

  return <Badge className={styles}>{riskLabel(level)}</Badge>;
}
