"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { MiraOnboardingExperience } from "@/components/onboarding/mira-onboarding-experience";

function OnboardingContent() {
  const searchParams = useSearchParams();
  const email = searchParams.get("email") || "";
  const token = searchParams.get("token") || "";
  return <MiraOnboardingExperience email={email} initialToken={token} />;
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-[#101112]" />}>
      <OnboardingContent />
    </Suspense>
  );
}
