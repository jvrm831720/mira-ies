"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  Upload,
  MessageSquareHeart,
  ScrollText,
  Settings,
  Radio,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { copy } from "@/lib/copy";

const links = [
  { href: "/", label: "Command Center", icon: LayoutDashboard },
  { href: "/alunos", label: "Alunos", icon: Users },
  { href: "/importar", label: "Importar", icon: Upload },
  { href: "/retencao", label: "Retenção", icon: MessageSquareHeart },
  { href: "/retencao/logs", label: "Logs de contato", icon: ScrollText },
  { href: "/config", label: "Configurações", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-full flex-col border-b border-border bg-white/80 backdrop-blur md:w-64 md:border-b-0 md:border-r">
      <div className="flex items-center gap-3 border-b border-border px-5 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
          <Radio className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm font-semibold tracking-tight">{copy.productName}</p>
          <p className="text-xs text-muted-foreground">{copy.productTagline}</p>
        </div>
      </div>
      <nav className="flex gap-1 overflow-x-auto p-3 md:flex-1 md:flex-col">
        {links.map((link) => {
          const active =
            link.href === "/"
              ? pathname === "/"
              : pathname === link.href || pathname.startsWith(link.href + "/");
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
                active
                  ? "bg-primary/10 font-medium text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <link.icon className="h-4 w-4" />
              {link.label}
            </Link>
          );
        })}
      </nav>
      <div className="hidden border-t border-border p-4 text-[11px] leading-relaxed text-muted-foreground md:block">
        Apoio à decisão da coordenação — não substitui acompanhamento humano.
      </div>
    </aside>
  );
}
