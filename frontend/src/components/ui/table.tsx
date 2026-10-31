import * as React from "react";
import { cn } from "@/lib/utils";

export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return <div className="w-full overflow-x-auto rounded-[var(--radius-control)] border border-[var(--border-subtle)]"><table className={cn("w-full caption-bottom border-collapse text-sm", className)} {...props} /></div>;
}
export function TableHeader({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("bg-[var(--surface-subtle)] [&_tr]:border-b [&_tr]:border-[var(--border-subtle)]", className)} {...props} />;
}
export function TableBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}
export function TableFooter({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tfoot className={cn("border-t border-[var(--border-subtle)] bg-[var(--surface-subtle)] font-medium", className)} {...props} />;
}
export function TableRow({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("border-b border-[var(--border-subtle)] transition-colors hover:bg-[var(--surface-subtle)]/70 data-[state=selected]:bg-[var(--accent)]", className)} {...props} />;
}
export function TableHead({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th scope="col" className={cn("h-10 px-4 text-left align-middle text-xs font-semibold tracking-wide text-[var(--text-secondary)]", className)} {...props} />;
}
export function TableCell({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-4 py-3 align-middle text-[var(--text-primary)]", className)} {...props} />;
}
export function TableCaption({ className, ...props }: React.HTMLAttributes<HTMLTableCaptionElement>) {
  return <caption className={cn("p-3 text-left text-xs text-[var(--text-secondary)]", className)} {...props} />;
}
