"use client";

import { useMemo, type ReactNode } from "react";
import {
  flexRender, getCoreRowModel, getSortedRowModel, useReactTable,
  type ColumnDef, type RowSelectionState, type SortingState, type VisibilityState,
} from "@tanstack/react-table";
import { Check, ChevronDown } from "@/components/ui/icons";
import { cn } from "@/lib/utils";
import type { ObjectField, ObjectSort } from "./object-index-types";
import { formatPropertyValue } from "./object-index-utils";

export type ObjectDataTableProps<T extends { id: string }> = {
  records: T[];
  fields: ObjectField<T>[];
  visible: string[];
  onVisibleChange: (keys: string[]) => void;
  sort: ObjectSort | null;
  onSortChange: (sort: ObjectSort | null) => void;
  manualSorting?: boolean;
  selected: RowSelectionState;
  onSelectedChange: (state: RowSelectionState) => void;
  onOpen?: (record: T) => void;
  loading?: boolean;
  emptyText?: string;
  emptyAction?: ReactNode;
};

function PropertyCell<T>({ field, record }: { field: ObjectField<T>; record: T }) {
  if (field.render) return <>{field.render(record)}</>;
  const value = field.getValue(record);
  const label = formatPropertyValue(field.type, value, field.nullLabel);
  if (field.type === "status" || field.type === "select") {
    const tone = String(value || "").toLowerCase();
    const semantic = ["critico", "failed", "rejected", "cancelled"].includes(tone) ? "red"
      : ["medio", "pending", "in_review"].includes(tone) ? "peach"
      : ["baixo", "approved", "completed", "active"].includes(tone) ? "green" : "blue";
    return <span className={cn("mira-tag inline-flex max-w-[230px] truncate", "mira-tag--" + semantic)}>{label}</span>;
  }
  return <span className={cn("block truncate", ["number", "percentage", "currency"].includes(field.type) && "tabular-nums")}>{label}</span>;
}

export function ObjectDataTable<T extends { id: string }>({
  records, fields, visible, onVisibleChange, sort, onSortChange,
  manualSorting = false, selected, onSelectedChange, onOpen,
  loading, emptyText = "Nenhum registro encontrado.", emptyAction,
}: ObjectDataTableProps<T>) {
  const primary = fields.find(field => field.primary) || fields[0];
  const columnVisibility = useMemo<VisibilityState>(() => Object.fromEntries(
    fields.map(field => [field.key, field.primary || visible.includes(field.key)])
  ), [fields, visible]);
  const columns = useMemo<ColumnDef<T>[]>(() => [
    {
      id: "__select",
      size: 42, enableSorting: false, enableHiding: false,
      header: ({ table }) => <input type="checkbox" aria-label="Selecionar registros desta página"
        checked={table.getIsAllPageRowsSelected()}
        ref={node => { if (node) node.indeterminate = table.getIsSomePageRowsSelected(); }}
        onChange={table.getToggleAllPageRowsSelectedHandler()}
        className="h-4 w-4 accent-[var(--color-blue)]" />,
      cell: ({ row }) => <input type="checkbox" aria-label={"Selecionar " + String(primary?.getValue(row.original) || row.id)}
        checked={row.getIsSelected()} onChange={row.getToggleSelectedHandler()}
        className="h-4 w-4 accent-[var(--color-blue)]" />,
    },
    ...fields.map<ColumnDef<T>>(field => ({
      id: field.key,
      accessorFn: record => field.getValue(record),
      size: field.width || 180,
      minSize: field.primary ? 200 : 100,
      enableSorting: !!field.sortable,
      enableHiding: !field.primary,
      header: ({ column }) => {
        const active = sort?.key === field.key;
        return <button type="button" disabled={!field.sortable}
          aria-label={field.sortable ? "Ordenar por " + field.title : field.title}
          aria-sort={active ? sort.desc ? "descending" : "ascending" : "none"}
          onClick={() => onSortChange(!active ? { key: field.key, desc: false }
            : !sort?.desc ? { key: field.key, desc: true } : null)}
          className={cn("flex max-w-full items-center gap-1.5 truncate text-left text-[11px] font-semibold",
            field.sortable && "cursor-pointer hover:text-[var(--color-ink)]",
            active && "text-[var(--color-ink)]")}>
          <span className="truncate">{field.title}</span>
          {field.sortable && <ChevronDown className={cn("h-3 w-3 shrink-0", active && !sort.desc && "rotate-180", !active && "opacity-0 group-hover:opacity-100")} />}
        </button>;
      },
      cell: ({ row }) => field.primary && onOpen
        ? <button type="button" onClick={() => onOpen(row.original)}
            className="max-w-full truncate text-left text-[12px] font-semibold text-[var(--color-ink)] hover:text-[var(--color-blue)] focus-visible:rounded focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]">
            <PropertyCell field={field} record={row.original} />
          </button>
        : <PropertyCell field={field} record={row.original} />,
    })),
  ], [fields, primary, onOpen, sort, onSortChange]);

  const table = useReactTable<T>({
    data: records, columns, getRowId: record => record.id,
    state: {
      rowSelection: selected,
      sorting: sort ? [{ id: sort.key, desc: sort.desc }] : [],
      columnVisibility,
    },
    onRowSelectionChange: updater => {
      const next = typeof updater === "function" ? updater(selected) : updater;
      onSelectedChange(next);
    },
    onSortingChange: updater => {
      const previous: SortingState = sort ? [{ id: sort.key, desc: sort.desc }] : [];
      const next = typeof updater === "function" ? updater(previous) : updater;
      onSortChange(next[0] ? { key: next[0].id, desc: next[0].desc } : null);
    },
    onColumnVisibilityChange: updater => {
      const next = typeof updater === "function" ? updater(columnVisibility) : updater;
      onVisibleChange(fields.filter(field => field.primary || next[field.key] !== false).map(field => field.key));
    },
    enableRowSelection: true,
    manualSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (loading) return <div role="status" aria-label="Carregando registros" className="space-y-2 p-4">
    {Array.from({ length: 7 }, (_, index) =>
      <div key={index} className="h-10 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-panel)] motion-reduce:animate-none" />)}
  </div>;

  if (!records.length) return <div className="flex min-h-40 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
    <p className="text-[13px] font-medium text-[var(--color-slate-600)]">{emptyText}</p>{emptyAction}
  </div>;

  return <div className="w-full overflow-x-auto" role="region" tabIndex={0} aria-label="Tabela de registros; role para navegar horizontalmente">
    <table className="w-full min-w-[650px] table-fixed border-separate border-spacing-0 text-left" aria-rowcount={records.length}>
      <thead className="sticky top-0 z-[1] bg-[var(--color-panel)]">
        {table.getHeaderGroups().map(group => <tr key={group.id}>
          {group.headers.map(header => <th key={header.id}
            scope="col" style={{ width: header.getSize() }}
            className="group h-10 border-b border-r border-[var(--color-border)] px-3 text-[11px] font-medium text-[var(--color-slate-600)] last:border-r-0">
            {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
          </th>)}
        </tr>)}
      </thead>
      <tbody>
        {table.getRowModel().rows.map(row => <tr key={row.id}
          data-selected={row.getIsSelected() ? "true" : undefined}
          className={cn("h-11 border-b transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)] motion-reduce:transition-none",
            row.getIsSelected() && "bg-[var(--color-blue-tint)]/50")}>
          {row.getVisibleCells().map(cell => <td key={cell.id} style={{ width: cell.column.getSize() }}
            className="h-11 max-w-0 overflow-hidden border-b border-[var(--color-border-subtle)] px-3 text-[12px] text-[var(--color-slate-600)]">
            {flexRender(cell.column.columnDef.cell, cell.getContext())}
          </td>)}
        </tr>)}
      </tbody>
    </table>
  </div>;
}
