import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-[var(--radius-control)] border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm text-[var(--color-ink)] ring-offset-background placeholder:text-[var(--color-muted)] transition-colors duration-[var(--motion-standard)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]/30 focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = "Input";
