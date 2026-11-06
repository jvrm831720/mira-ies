import Link from "next/link";

export default function UnauthorizedPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--color-legacy-f8f9fc)] p-6 text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--color-legacy-b84336)]">403</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Acesso não autorizado</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Seu perfil nesta organização não permite abrir esta área. Peça a um administrador se precisar
        de permissão adicional.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <Link href="/" className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white">
          Ir para visão geral
        </Link>
        <Link
          href="/config"
          className="rounded-xl border border-border bg-white px-4 py-2.5 text-sm font-semibold"
        >
          Configurações
        </Link>
      </div>
    </div>
  );
}
