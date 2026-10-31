import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  wrapperClassName?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, wrapperClassName, children, ...props }, ref) => (
    <div className={cn("relative w-full", wrapperClassName)}>
      <select
        ref={ref}
        className={cn(
          "flex h-10 w-full appearance-none rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white px-3.5 pr-10 text-sm text-[var(--text-primary)] shadow-sm outline-none transition-colors",
          "hover:border-[var(--border-strong)] focus-visible:border-[var(--brand-indigo)] focus-visible:ring-2 focus-visible:ring-[var(--brand-indigo)]/20",
          "disabled:cursor-not-allowed disabled:bg-[var(--surface-subtle)] disabled:text-[var(--text-secondary)] disabled:opacity-70",
          "aria-[invalid=true]:border-red-500 aria-[invalid=true]:focus-visible:ring-red-500/20",
          className
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-secondary)]" />
    </div>
  )
);
Select.displayName = "Select";
