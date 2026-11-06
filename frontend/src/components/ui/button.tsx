import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition duration-[var(--motion-standard)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "rounded-[var(--radius-control)] bg-[var(--color-ink)] text-white shadow-[var(--shadow-button-attio)] transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-ink-900)]",
        secondary:
          "rounded-[var(--radius-control)] bg-[var(--color-panel)] text-[var(--color-ink)] transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-border)]",
        outline:
          "rounded-[var(--radius-control)] border border-[var(--color-border)] bg-white text-[var(--color-ink)] transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)]",
        ghost: "rounded-[var(--radius-control)] transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)]",
        destructive:
          "rounded-[var(--radius-control)] bg-red-600 text-white transition-colors duration-[var(--motion-standard)] hover:bg-red-700",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 px-3 text-xs",
        lg: "h-11 px-6",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  )
);
Button.displayName = "Button";
