"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

type TabItem = { id: string; label: string; disabled?: boolean };

type TabsProps = {
  items: TabItem[];
  value: string;
  onValueChange: (id: string) => void;
  className?: string;
  /** Optional panel content keyed by tab id */
  children?: React.ReactNode;
};

export function Tabs({ items, value, onValueChange, className }: TabsProps) {
  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      className={cn(
        "inline-flex flex-wrap gap-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-1",
        className
      )}
    >
      {items.map((item) => {
        const active = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            disabled={item.disabled}
            id={`tab-${item.id}`}
            onClick={() => !item.disabled && onValueChange(item.id)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-40",
              active
                ? "bg-[var(--surface-card)] text-[var(--text-primary)] shadow-sm"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({
  when,
  active,
  children,
  className,
}: {
  when: string;
  active: string;
  children: React.ReactNode;
  className?: string;
}) {
  if (when !== active) return null;
  return (
    <div role="tabpanel" aria-labelledby={`tab-${when}`} className={className}>
      {children}
    </div>
  );
}
