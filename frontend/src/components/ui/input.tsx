import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white px-3 text-sm font-medium text-ink ring-offset-background placeholder:text-[var(--color-fog-400)] transition-colors duration-[var(--motion-standard)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]/25 focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = "Input";
