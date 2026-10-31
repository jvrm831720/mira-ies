"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export function Dialog({ open, onOpenChange, children, className }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = React.useRef<HTMLDialogElement>(null);
  React.useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return <dialog ref={ref} onClose={() => onOpenChange(false)} onClick={(event) => { if (event.target === ref.current) onOpenChange(false); }} className={cn("m-auto max-h-[min(90vh,48rem)] w-[calc(100%-2rem)] max-w-lg overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-white p-0 text-[var(--text-primary)] shadow-[var(--shadow-overlay)] backdrop:bg-slate-950/35", className)}>{children}</dialog>;
}

export function DialogContent({ children, className, onClose }: { children: React.ReactNode; className?: string; onClose?: () => void }) {
  return <div className={cn("relative p-6", className)}>{onClose && <button type="button" aria-label="Fechar" onClick={onClose} className="absolute right-4 top-4 rounded-md p-1.5 text-[var(--text-secondary)] hover:bg-[var(--surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-indigo)]"><X className="h-4 w-4" /></button>}{children}</div>;
}
export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn("mb-5 flex flex-col gap-1.5", className)} {...props} />; }
export function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) { return <h2 className={cn("text-lg font-semibold tracking-tight", className)} {...props} />; }
export function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) { return <p className={cn("text-sm leading-6 text-[var(--text-secondary)]", className)} {...props} />; }
