"use client";

import { Suspense } from "react";
import { ConversationalOnboarding } from "@/components/onboarding/conversational-onboarding";

export default function OnboardingPage() {
  return (
    <Suspense fallback={<main className="mira-flow-page" aria-busy="true" />}>
      <ConversationalOnboarding />
    </Suspense>
  );
}
