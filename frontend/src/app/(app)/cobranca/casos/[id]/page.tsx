import { Suspense } from "react";
import { CollectionCaseFullPage } from "@/components/collections/collection-record-experience";

export default function CollectionCasePage() {
  return <Suspense fallback={<main className="mira-page p-8 text-xs text-[var(--color-muted)]" role="status">
    Carregando ficha do caso financeiro…
  </main>}>
    <CollectionCaseFullPage />
  </Suspense>;
}
