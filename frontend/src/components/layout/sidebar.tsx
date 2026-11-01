"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BriefcaseBusiness,
  Building2,
  ChartNoAxesCombined,
  ChevronDown,
  ChevronsUpDown,
  Database,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Receipt,
  Search,
  Settings2,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { clearAuth } from "@/lib/auth";
import { api } from "@/lib/api";

type NavLink = {
  href: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  match?: "exact" | "prefix";
};

type NavGroup = {
  id: string;
  label: string;
  links: NavLink[];
};

const groups: NavGroup[] = [
  {
    id: "executiva",
    label: "Visão executiva",
    links: [
      {
        href: "/",
        label: "Visão geral",
        description: "Painel e prioridades",
        icon: LayoutDashboard,
        match: "exact",
      },
    ],
  },
  {
    id: "alunos",
    label: "Gestão de alunos",
    links: [
      {
        href: "/alunos",
        label: "Alunos",
        description: "Base acadêmica",
        icon: Users,
        match: "prefix",
      },
      {
        href: "/monitoramento",
        label: "Monitoramento",
        description: "Prioridades e risco atual",
        icon: Activity,
        match: "prefix",
      },
    ],
  },
  {
    id: "operacao",
    label: "Operação",
    links: [
      {
        href: "/trabalho",
        label: "Central de trabalho",
        description: "Filas e tarefas",
        icon: BriefcaseBusiness,
        match: "prefix",
      },
      {
        href: "/retencao",
        label: "Intervenções",
        description: "Ações de retenção",
        icon: Workflow,
        match: "prefix",
      },
    ],
  },
  {
    id: "inteligencia",
    label: "Inteligência e resultados",
    links: [
      {
        href: "/retencao/logs",
        label: "Resultados",
        description: "Indicadores e logs",
        icon: ChartNoAxesCombined,
        match: "prefix",
      },
    ],
  },
  {
    id: "admin",
    label: "Administração",
    links: [
      {
        href: "/conectores",
        label: "Dados e integrações",
        description: "Conectores e imports",
        icon: Database,
        match: "prefix",
      },
      {
        href: "/fatura",
        label: "Fatura e créditos",
        description: "Plano, consumo e créditos",
        icon: Receipt,
        match: "prefix",
      },
      {
        href: "/config",
        label: "Configurações",
        description: "Instituição e acesso",
        icon: Settings2,
        match: "prefix",
      },
    ],
  },
];
