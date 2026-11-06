import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-[var(--radius-md)] bg-[var(--color-panel)] motion-reduce:animate-none", className)} />;
}
