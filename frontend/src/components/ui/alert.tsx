import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

const styles = {
  default: { icon: Info, className: "border-[var(--border-subtle)] bg-[var(--surface-card)] text-[var(--text-primary)]" },
  info: { icon: Info, className: "border-blue-200 bg-blue-50 text-blue-900" },
  success: { icon: CheckCircle2, className: "border-emerald-200 bg-emerald-50 text-emerald-900" },
  warning: { icon: TriangleAlert, className: "border-amber-200 bg-amber-50 text-amber-950" },
  destructive: { icon: AlertCircle, className: "border-red-200 bg-red-50 text-red-900" },
} as const;

export function Alert({
  variant = "default",
  title,
  children,
  className,
  role,
}: {
  variant?: keyof typeof styles;
  title?: string;
  children: React.ReactNode;
  className?: string;
  role?: "alert" | "status";
}) {
  const config = styles[variant];
  const Icon = config.icon;
  return (
    <div role={role || (variant === "destructive" ? "alert" : "status")} className={cn("flex gap-3 rounded-[var(--radius-control)] border p-3.5 text-sm", config.className, className)}>
      <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        <div className={cn(title && "mt-1", "leading-5")}>{children}</div>
      </div>
    </div>
  );
}
