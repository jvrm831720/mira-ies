"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { OrgMeResponse } from "@/lib/api";

const sections = [
  { href: "/academico", label: "Catálogo", feature: "academic_catalog" },
  { href: "/academico/jornadas", label: "Jornadas acadêmicas", feature: "academic_operations" },
  { href: "/academico/servicos", label: "Central de serviços", feature: "academic_services" },
] as const;

export function AcademicNavigation({ features }: { features: OrgMeResponse["available_features"] }) {
  const pathname = usePathname();

  const available = sections.filter(({ href, feature }) => href === pathname || features?.[feature] === true);

  return (
    <nav aria-label="Gestão acadêmica" className="mb-5 flex flex-wrap gap-1 border-b border-[var(--color-border)]">
      {available.map(({ href, label }) => {
        const active = href === pathname;
        return (
          <Link key={href} href={href} aria-current={active ? "page" : undefined}
            className={`border-b-2 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-blue)] ${active
              ? "border-[var(--color-blue)] font-semibold text-[var(--color-ink)]"
              : "border-transparent text-[var(--color-slate-600)] hover:bg-[var(--color-panel)]"}`}>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
