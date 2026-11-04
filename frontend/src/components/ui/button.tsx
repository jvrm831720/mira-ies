import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "rounded-[var(--radius-control)] bg-graphite text-white shadow-sm transition-colors duration-[var(--motion-standard)] hover:bg-ink",
        secondary:
          "rounded-[var(--radius-control)] bg-paper text-ink transition-colors duration-[var(--motion-standard)] hover:bg-haze",
        outline:
          "rounded-[var(--radius-control)] border border-[var(--border-subtle)] bg-white text-ink transition-colors duration-[var(--motion-standard)] hover:bg-paper",
        ghost: "rounded-[var(--radius-control)] text-carbon transition-colors duration-[var(--motion-standard)] hover:bg-paper",
        destructive:
          "rounded-[var(--radius-control)] bg-red-700 text-white transition-colors duration-[var(--motion-standard)] hover:bg-red-800",
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
