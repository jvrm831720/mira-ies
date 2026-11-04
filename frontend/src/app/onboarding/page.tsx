"use client";

import { Suspense } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

function OnboardingConfirmation() {
  const searchParams = useSearchParams();
  const email = searchParams.get("email");

  return (
    <main className="flex min-h-screen items-center justify-center bg-white px-6 py-12 text-neutral-900">
      <section className="w-full max-w-[420px]">
        <Image src="/mira-logo.svg" alt="MIRA" width={112} height={29} priority className="mb-16 h-auto w-[104px] brightness-0" />
        <p className="mb-3 text-[12px] font-medium uppercase tracking-[0.12em] text-neutral-400">E-mail confirmado</p>
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.04em]">Vamos preparar seu acesso.</h1>
        <p className="mt-3 text-[14px] leading-6 text-neutral-500">
          {email ? <>Confirmamos que você tem acesso ao e-mail <span className="font-medium text-neutral-800">{email}</span>.</> : "Seu e-mail foi confirmado."}
          {" "}A próxima etapa será configurar seu acesso à MIRA.
        </p>
        <p className="mt-8 rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 text-[13px] leading-5 text-neutral-600">
          O processo de onboarding será continuado nesta etapa. Nenhuma conta foi criada ainda.
        </p>
        <Link href="/login" className="mt-8 inline-flex text-[13px] font-medium text-neutral-900 underline underline-offset-4">
          Voltar para o início
        </Link>
      </section>
    </main>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-white" />}>
      <OnboardingConfirmation />
    </Suspense>
  );
}
