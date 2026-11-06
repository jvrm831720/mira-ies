import { Suspense } from "react";
import { CollectionsExperience } from "@/components/collections/collections-experience";

export default function CollectionsPage() {
  return <Suspense fallback={<main className="mira-page p-8 text-sm text-[var(--color-muted)]" role="status">Carregando casos financeiros…</main>}>
    <CollectionsExperience />
  </Suspense>;
}
