import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  Send,
  XCircle,
} from "@/components/ui/icons";

const variants = {
  pending: {
    label: "Pendente",
    className: "border-[var(--color-peach-tint-border)] bg-[var(--color-peach-tint)] text-amber-800",
    icon: AlertTriangle,
  },
  progress: {
    label: "Em andamento",
    className: "border-[var(--color-blue-tint-border)] bg-[var(--color-blue-tint)] text-[var(--color-blue-ink)]",
    icon: Loader2,
  },
  submitted: {
    label: "Enviado",
    className: "border-[var(--color-purple-tint-border)] bg-[var(--color-purple-tint)] text-[var(--color-purple)]",
    icon: Send,
  },
  review: {
    label: "Em revisão",
    className: "border-[var(--color-peach-tint-border)] bg-[var(--color-peach-tint)] text-amber-800",
    icon: Clock3,
  },
  success: {
    label: "Sucesso",
    className: "border-[var(--color-green-tint-border)] bg-[var(--color-green-tint)] text-[var(--color-green)]",
    icon: CheckCircle2,
  },
  failed: {
    label: "Falhou",
    className: "border-[var(--color-red-tint-border)] bg-red-50 text-[var(--color-red)]",
    icon: XCircle,
  },
  expired: {
    label: "Expirado",
    className: "border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-slate-600)]",
    icon: Clock3,
  },
} as const;

export type StatusVariant = keyof typeof variants;

export function StatusBadge({
  status,
  label,
  className,
}: {
  status: StatusVariant;
  label?: string;
  className?: string;
}) {
  const v = variants[status];
  const Icon = v.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--radius-xs)] border px-2 py-0.5 text-[length:var(--type-caption)] font-medium tracking-tight",
        v.className,
        className
      )}
    >
      <Icon className={cn("h-3.5 w-3.5", status === "progress" && "animate-spin")} />
      {label || v.label}
    </span>
  );
}
