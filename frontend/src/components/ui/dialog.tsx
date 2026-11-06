"use client";

import * as React from "react";
import { X } from "@/components/ui/icons";
import { cn } from "@/lib/utils";

type DialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  /** When true, Escape and backdrop click close the dialog. */
  dismissible?: boolean;
};

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  className,
  dismissible = true,
}: DialogProps) {
  const dialogRef = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();
  const descId = React.useId();

  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && dismissible) onOpenChange(false);
    };
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = () => Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
    ) || []);
    const onTrap = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const controls = focusable();
      if (!controls.length) { event.preventDefault(); dialogRef.current?.focus(); return; }
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    };
    dialogRef.current?.focus();
    document.addEventListener("keydown", onKey);
    document.addEventListener("keydown", onTrap);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("keydown", onTrap);
      previousFocus?.focus();
      document.body.style.overflow = prev;
    };
  }, [open, dismissible, onOpenChange]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button
        type="button"
        className="absolute inset-0 bg-[var(--brand-midnight)]/40 backdrop-blur-[2px]"
        aria-label="Fechar"
        disabled={!dismissible}
        onClick={() => dismissible && onOpenChange(false)}
      />
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        className={cn(
          "relative z-10 flex max-h-[min(92vh,720px)] w-full max-w-lg flex-col overflow-hidden rounded-t-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-overlay)] sm:rounded-[var(--radius-card)]",
          className
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
              {title}
            </h2>
            {description ? (
              <p id={descId} className="mt-1 text-sm text-[var(--text-secondary)]">
                {description}
              </p>
            ) : null}
          </div>
          {dismissible ? (
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-[var(--text-secondary)] transition hover:bg-[var(--surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
              aria-label="Fechar"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
