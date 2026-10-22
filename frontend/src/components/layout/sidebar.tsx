"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Upload,
  MessageSquareHeart,
  ScrollText,
  Settings,
  UserCog,
} from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Visão geral", icon: LayoutDashboard },
  { href: "/alunos", label: "Alunos", icon: Users },
  { href: "/importar", label: "Importar", icon: Upload },
  { href: "/retencao", label: "Retenção", icon: MessageSquareHeart },
  { href: "/retencao/logs", label: "Logs de contato", icon: ScrollText },
  { href: "/membros", label: "Membros", icon: UserCog },
  { href: "/config", label: "Configurações", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden min-h-screen w-[248px] shrink-0 flex-col bg-[var(--brand-midnight)] text-white md:flex">
      <div className="flex h-[76px] items-center border-b border-white/10 px-6">
        <Image src="/mira-logo.svg" alt="Mira" width={128} height={29} className="h-auto w-[118px]" priority />
      </div>
      <nav aria-label="Navegação principal" className="flex flex-1 flex-col gap-1 px-3 py-6">
        <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/45">
          Workspace
        </p>
        {links.map((link) => {
          const active =
            link.href === "/"
              ? pathname === "/"
              : pathname === link.href ||
                (link.href !== "/retencao" && pathname.startsWith(link.href + "/"));
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "group relative flex shrink-0 items-center gap-3 rounded-xl px-3 py-3 text-[13px] transition duration-200",
                active
                  ? "bg-white/10 font-semibold text-white shadow-inner"
                  : "text-white/65 hover:bg-white/[0.07] hover:text-white"
              )}
              aria-current={active ? "page" : undefined}
            >
              {active && (
                <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-[var(--brand-coral)]" />
              )}
              <link.icon
                className={cn(
                  "h-[17px] w-[17px]",
                  active ? "text-[var(--brand-coral)]" : "text-white/55 group-hover:text-white"
                )}
              />
              {link.label}
            </Link>
          );
        })}
      </nav>
      <div className="m-3 rounded-xl border border-white/10 bg-white/[0.04] p-3.5 text-[11px] leading-relaxed text-white/60">
        <span className="mb-2 block h-1 w-8 rounded-full bg-[var(--brand-coral)]" />
        Apoio à decisão da coordenação. O cuidado humano continua no centro.
      </div>
    </aside>
  );
}
