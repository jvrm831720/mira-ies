import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white px-3.5 py-2 text-sm text-[var(--text-primary)] shadow-sm outline-none placeholder:text-[var(--text-secondary)]/70 transition-colors",
        "hover:border-[var(--border-strong)] focus-visible:border-[var(--brand-indigo)] focus-visible:ring-2 focus-visible:ring-[var(--brand-indigo)]/20",
        "disabled:cursor-not-allowed disabled:bg-[var(--surface-subtle)] disabled:text-[var(--text-secondary)] disabled:opacity-70",
        "aria-[invalid=true]:border-red-500 aria-[invalid=true]:focus-visible:ring-red-500/20",
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = "Input";
