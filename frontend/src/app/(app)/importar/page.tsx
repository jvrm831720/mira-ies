"use client";

import { Header } from "@/components/layout/header";
import { SmartImportWizard } from "@/components/import/SmartImportWizard";

export default function ImportarPage() {
  return (
    <>
      <Header title="Importação inteligente" subtitle="Reconheça colunas, valide registros e importe com controle." />
      <main className="mx-auto w-full max-w-[1200px] space-y-5 px-4 pb-12 pt-5 md:px-8 md:pt-7 xl:px-10">
        <SmartImportWizard />
      </main>
    </>
  );
}
