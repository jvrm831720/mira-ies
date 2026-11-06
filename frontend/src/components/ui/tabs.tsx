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
      onKeyDown={(event) => {
        if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
        const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]:not(:disabled)'));
        if (!buttons.length) return;
        event.preventDefault();
        const index = buttons.indexOf(event.target as HTMLButtonElement);
        const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
        const target = buttons[next];
        target.focus();
        const id = target.dataset.tabId;
        if (id) onValueChange(id);
      }}
      className={cn(
        "inline-flex flex-wrap gap-1 rounded-[var(--radius-control)] border border-[var(--color-border)] bg-[var(--color-panel)] p-1",
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
            data-tab-id={item.id}
            tabIndex={active ? 0 : -1}
            aria-selected={active}
            disabled={item.disabled}
            id={`tab-${item.id}`}
            onClick={() => !item.disabled && onValueChange(item.id)}
            className={cn(
              "rounded-[var(--radius-md)] px-3 py-1.5 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-40",
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
