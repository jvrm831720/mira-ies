"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

type TabsContextValue = { value: string; setValue: (value: string) => void; id: string };
const TabsContext = React.createContext<TabsContextValue | null>(null);
function useTabs() {
  const context = React.useContext(TabsContext);
  if (!context) throw new Error("Tabs components must be used inside Tabs.");
  return context;
}

export function Tabs({ defaultValue, value, onValueChange, children, className }: {
  defaultValue: string;
  value?: string;
  onValueChange?: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const [internal, setInternal] = React.useState(defaultValue);
  const id = React.useId();
  const active = value ?? internal;
  const setValue = (next: string) => { if (value === undefined) setInternal(next); onValueChange?.(next); };
  return <TabsContext.Provider value={{ value: active, setValue, id }}><div className={className}>{children}</div></TabsContext.Provider>;
}

export function TabsList({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div role="tablist" className={cn("inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-lg bg-[var(--surface-subtle)] p-1", className)}>{children}</div>;
}

export function TabsTrigger({ value, children, disabled, className }: { value: string; children: React.ReactNode; disabled?: boolean; className?: string }) {
  const tabs = useTabs();
  const selected = tabs.value === value;
  return <button type="button" role="tab" id={`${tabs.id}-tab-${value}`} aria-selected={selected} aria-controls={`${tabs.id}-panel-${value}`} tabIndex={selected ? 0 : -1} disabled={disabled} onClick={() => tabs.setValue(value)} className={cn("shrink-0 rounded-md px-3 py-1.5 text-sm font-medium text-[var(--text-secondary)] outline-none transition-colors hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-indigo)] disabled:pointer-events-none disabled:opacity-50", selected && "bg-white text-[var(--text-primary)] shadow-sm", className)}>{children}</button>;
}

export function TabsContent({ value, children, className }: { value: string; children: React.ReactNode; className?: string }) {
  const tabs = useTabs();
  if (tabs.value !== value) return null;
  return <div role="tabpanel" id={`${tabs.id}-panel-${value}`} aria-labelledby={`${tabs.id}-tab-${value}`} tabIndex={0} className={cn("mt-4 outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-indigo)]", className)}>{children}</div>;
}
