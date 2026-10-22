import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  Send,
  XCircle,
} from "lucide-react";

const variants = {
  pending: {
    label: "Pendente",
    className: "border-amber-500/25 bg-amber-500/10 text-amber-600",
    icon: AlertTriangle,
  },
  progress: {
    label: "Em andamento",
    className: "border-sky-500/25 bg-sky-500/10 text-sky-600",
    icon: Loader2,
  },
  submitted: {
    label: "Enviado",
    className: "border-violet-500/25 bg-violet-500/10 text-violet-600",
    icon: Send,
  },
  review: {
    label: "Em revisão",
    className: "border-yellow-500/25 bg-yellow-500/10 text-yellow-700",
    icon: Clock3,
  },
  success: {
    label: "Sucesso",
    className: "border-emerald-500/25 bg-emerald-500/10 text-emerald-600",
    icon: CheckCircle2,
  },
  failed: {
    label: "Falhou",
    className: "border-red-500/25 bg-red-500/10 text-red-600",
    icon: XCircle,
  },
  expired: {
    label: "Expirado",
    className: "border-neutral-500/25 bg-neutral-500/10 text-neutral-500",
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
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-tight",
        v.className,
        className
      )}
    >
      <Icon className={cn("h-3.5 w-3.5", status === "progress" && "animate-spin")} />
      {label || v.label}
    </span>
  );
}
