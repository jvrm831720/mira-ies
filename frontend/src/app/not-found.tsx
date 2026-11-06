import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[var(--color-legacy-f8f9fc)] p-6 text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">404</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Página não encontrada</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        O endereço pode estar incorreto ou a página foi movida.
      </p>
      <Link
        href="/"
        className="mt-6 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white"
      >
        Voltar ao painel
      </Link>
    </div>
  );
}
