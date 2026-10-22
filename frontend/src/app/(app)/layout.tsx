"use client";

import { AuthGate } from "@/components/auth-gate";
import { Sidebar } from "@/components/layout/sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <div className="min-h-screen bg-[hsl(var(--background))] md:flex">
        <Sidebar />
        <div className="min-w-0 flex-1 bg-[hsl(var(--background))]">{children}</div>
      </div>
    </AuthGate>
  );
}
