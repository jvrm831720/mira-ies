"use client";

import { AuthGate } from "@/components/auth-gate";
import { Sidebar } from "@/components/layout/sidebar";
import { NavigationContextProvider } from "@/components/layout/navigation-context-provider";
import { InstitutionalOnboarding } from "@/components/onboarding/institutional-onboarding";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <NavigationContextProvider>
      <a href="#mira-main-content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[90] focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:text-[var(--color-ink)]">Pular para o conteúdo</a>
      <div className="mira-app-shell min-h-dvh bg-[var(--color-canvas)] md:flex">
        <Sidebar />
        <div id="mira-main-content" className="min-w-0 flex-1">{children}</div>
      </div>
      <InstitutionalOnboarding />
      </NavigationContextProvider>
    </AuthGate>
  );
}
