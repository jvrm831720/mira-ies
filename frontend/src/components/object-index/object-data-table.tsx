"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import {
  flexRender, getCoreRowModel, useReactTable,
  type ColumnDef, type RowSelectionState, type SortingState, type VisibilityState,
  type ColumnSizingState,
} from "@tanstack/react-table";
import { ChevronDown } from "@/components/ui/icons";
import { cn } from "@/lib/utils";
import type { ObjectField, ObjectSort } from "./object-index-types";
import { formatPropertyValue } from "./object-index-utils";

export type ObjectDataTableProps<T extends { id: string }> = {
  records: T[];
  fields: ObjectField<T>[];
  visible: string[];
  onVisibleChange: (keys: string[]) => void;
  sorts: ObjectSort[];
  onSortsChange: (sorts: ObjectSort[]) => void;
  density: "compact" | "comfortable";
  pinned: string[];
  onPinnedChange: (keys: string[]) => void;
  columnWidths: Record<string, number>;
  onWidthsChange: (widths: Record<string, number>) => void;
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
    return <span className={cn("mira-tag inline-flex max-w-full truncate", "mira-tag--" + semantic)}>{label}</span>;
  }
  return <span className={cn("block truncate", ["number", "percentage", "currency"].includes(field.type) && "tabular-nums")}>{label}</span>;
}

/** Shared accessible object table. Row selection is *only* for loaded page records. */
export function ObjectDataTable<T extends { id: string }>({
  records, fields, visible, onVisibleChange, sorts, onSortsChange,
  density, pinned, onPinnedChange, columnWidths, onWidthsChange,
  selected, onSelectedChange, onOpen, loading, emptyText = "Nenhum registro encontrado.", emptyAction,
}: ObjectDataTableProps<T>) {
  const primary = fields.find(field => field.primary) || fields[0];
  const [sizes, setSizes] = useState<ColumnSizingState>(columnWidths);
  useEffect(() => { setSizes(columnWidths); }, [columnWidths]);
  useEffect(() => {
    if (JSON.stringify(sizes) === JSON.stringify(columnWidths)) return;
    const timer = window.setTimeout(() => onWidthsChange(Object.fromEntries(
      Object.entries(sizes).filter(([key, width]) => fields.some(field => field.key === key) &&
        Number.isFinite(width) && width >= 100 && width <= 640)
    )), 400);
    return () => window.clearTimeout(timer);
  }, [sizes, columnWidths, fields, onWidthsChange]);

  const visibleIds = useMemo(() => new Set(fields.map(field => field.key)), [fields]);
  const leftPinned = useMemo(() => ["__select", ...pinned.filter(key => visibleIds.has(key))], [pinned, visibleIds]);
  const columnVisibility = useMemo<VisibilityState>(() => Object.fromEntries(
    fields.map(field => [field.key, field.primary || visible.includes(field.key)])
  ), [fields, visible]);
  const tableSorts: SortingState = sorts.map(sort => ({ id: sort.key, desc: sort.desc }));

  const toggleSort = useCallback((key: string, additive: boolean) => {
    const current = sorts.find(sort => sort.key === key);
    const next = current ? current.desc ? null : { key, desc: true } : { key, desc: false };
    if (additive) {
      onSortsChange(current
        ? next ? sorts.map(sort => sort.key === key ? next : sort) : sorts.filter(sort => sort.key !== key)
        : next ? [...sorts, next].slice(0, 3) : sorts);
    } else {
      onSortsChange(next ? [next] : []);
    }
  }, [sorts, onSortsChange]);

  const columns = useMemo<ColumnDef<T>[]>(() => [
    {
      id: "__select", size: 42, minSize: 42, maxSize: 42,
      enableSorting: false, enableHiding: false, enableResizing: false,
      header: ({ table }) => <input type="checkbox" aria-label="Selecionar somente os registros desta página"
        checked={table.getIsAllPageRowsSelected()}
        ref={node => { if (node) node.indeterminate = table.getIsSomePageRowsSelected() && !table.getIsAllPageRowsSelected(); }}
        onChange={table.getToggleAllPageRowsSelectedHandler()}
        className="h-4 w-4 accent-[var(--color-blue)]" />,
      cell: ({ row }) => <input type="checkbox" aria-label={"Selecionar " + String(primary?.getValue(row.original) || row.id)}
        checked={row.getIsSelected()} onChange={row.getToggleSelectedHandler()}
        className="h-4 w-4 accent-[var(--color-blue)]" />,
    },
    ...fields.map<ColumnDef<T>>(field => ({
      id: field.key,
      accessorFn: record => field.getValue(record),
      size: field.width || 180, minSize: field.primary ? 200 : 100, maxSize: 640,
      enableSorting: !!field.sortable, enableHiding: !field.primary,
      enableResizing: true,
      header: () => {
        const rank = sorts.findIndex(item => item.key === field.key);
        const active = rank >= 0 ? sorts[rank] : null;
        return <button type="button" disabled={!field.sortable}
          title={field.sortable ? "Clique para ordenar; Shift+clique adiciona uma coluna à ordenação" : undefined}
          aria-label={field.sortable ? "Ordenar por " + field.title + (active ? ", critério " + (rank + 1) : "") : field.title}
          onClick={event => toggleSort(field.key, event.shiftKey)}
          className={cn("flex w-full min-w-0 items-center gap-1 truncate text-left text-[length:var(--type-caption)] font-semibold",
            field.sortable && "cursor-pointer hover:text-[var(--color-ink)]",
            active && "text-[var(--color-ink)]")}>
          <span className="truncate">{field.title}</span>
          {active && sorts.length > 1 && <span className="text-[length:var(--type-overline)] tabular-nums" aria-hidden="true">{rank + 1}</span>}
          {field.sortable && <ChevronDown className={cn("h-3 w-3 shrink-0", active && !active.desc && "rotate-180",
            !active && "opacity-0 group-hover:opacity-100")} />}
        </button>;
      },
      cell: ({ row }) => field.primary && onOpen
        ? <button type="button" onClick={() => onOpen(row.original)}
            className="max-w-full truncate text-left text-xs font-semibold text-[var(--color-ink)] hover:text-[var(--color-blue)] focus-visible:rounded focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]">
            <PropertyCell field={field} record={row.original} />
          </button>
        : <PropertyCell field={field} record={row.original} />,
    })),
  ], [fields, primary, onOpen, sorts, toggleSort]);

  const table = useReactTable<T>({
    data: records, columns, getRowId: record => record.id,
    state: {
      rowSelection: selected, sorting: tableSorts, columnVisibility,
      columnPinning: { left: leftPinned, right: [] },
      columnSizing: sizes,
    },
    onColumnSizingChange: updater => setSizes(old => typeof updater === "function" ? updater(old) : updater),
    onRowSelectionChange: updater => onSelectedChange(typeof updater === "function" ? updater(selected) : updater),
    onSortingChange: updater => {
      const next = typeof updater === "function" ? updater(tableSorts) : updater;
      onSortsChange(next.map(item => ({ key: item.id, desc: item.desc })).slice(0, 3));
    },
    onColumnVisibilityChange: updater => {
      const next = typeof updater === "function" ? updater(columnVisibility) : updater;
      onVisibleChange(fields.filter(field => field.primary || next[field.key] !== false).map(field => field.key));
    },
    enableRowSelection: true, enableColumnResizing: true, columnResizeMode: "onChange",
    manualSorting: true, getCoreRowModel: getCoreRowModel(),
  });

  function keyboardRow(event: KeyboardEvent<HTMLTableRowElement>, id: string, record: T) {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" && onOpen) { event.preventDefault(); onOpen(record); return; }
    if (event.key === " " || event.key === "Spacebar") {
      event.preventDefault(); onSelectedChange({ ...selected, [id]: !selected[id] }); return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const rows = Array.from(event.currentTarget.parentElement?.querySelectorAll<HTMLTableRowElement>("tr[data-record-row]") || []);
    const index = rows.indexOf(event.currentTarget);
    rows[index + (event.key === "ArrowDown" ? 1 : -1)]?.focus();
  }

  if (loading) return <div role="status" aria-label="Carregando registros" className="space-y-2 p-4">
    {Array.from({ length: 7 }, (_, index) =>
      <div key={index} className="h-10 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-panel)] motion-reduce:animate-none" />)}
  </div>;

  if (!records.length) return <div className="flex min-h-40 flex-col items-center justify-center gap-2 px-6 py-10 text-center">
    <p className="text-[length:var(--type-body-compact)] font-medium text-[var(--color-slate-600)]">{emptyText}</p>{emptyAction}
  </div>;

  const compact = density === "compact";
  function stickyStyle(column: ReturnType<typeof table.getAllColumns>[number], header = false): CSSProperties {
    const sticky = column.getIsPinned() === "left";
    return {
      width: column.getSize(), minWidth: column.getSize(),
      position: sticky ? "sticky" : "relative",
      left: sticky ? column.getStart("left") : undefined,
      zIndex: sticky ? header ? 5 : 3 : header ? 2 : 1,
      background: sticky ? "var(--color-canvas)" : undefined,
      boxShadow: sticky && column.getIsLastColumn("left") ? "-1px 0 0 var(--color-border) inset" : undefined,
    };
  }

  return <div className="w-full overflow-x-auto" role="region" tabIndex={0}
    aria-label="Tabela de registros; use as setas verticais nas linhas para navegar">
    <table className="w-max min-w-full table-fixed border-separate border-spacing-0 text-left"
      aria-rowcount={records.length}>
      <thead className="sticky top-0 z-[4] bg-[var(--color-panel)]">
        {table.getHeaderGroups().map(group => <tr key={group.id}>
          {group.headers.map(header => <th key={header.id}
            scope="col" aria-sort={header.column.getCanSort() ?
              header.column.getIsSorted() === "asc" ? "ascending" :
              header.column.getIsSorted() === "desc" ? "descending" : "none" : undefined}
            style={stickyStyle(header.column, true)}
            className={cn("group border-b border-r border-[var(--color-border)] px-3 text-[length:var(--type-caption)] font-medium text-[var(--color-slate-600)] last:border-r-0",
              compact ? "h-9" : "h-11")}>
            <div className="flex items-center gap-1">
              <div className="min-w-0 flex-1">{header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}</div>
              {header.column.id !== "__select" &&
                <button type="button" aria-label={(pinned.includes(header.column.id) ? "Desafixar " : "Fixar ") + header.column.id}
                  onClick={() => onPinnedChange(pinned.includes(header.column.id)
                    ? pinned.filter(id => id !== header.column.id) : [...pinned, header.column.id].slice(0, 3))}
                  title={pinned.includes(header.column.id) ? "Desafixar coluna" : "Fixar coluna"}
                  className={cn("shrink-0 rounded px-1 text-[length:var(--type-overline)] focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]",
                    pinned.includes(header.column.id) ? "text-[var(--color-blue)]" : "text-[var(--color-muted)] opacity-50 group-hover:opacity-100")}>
                  {pinned.includes(header.column.id) ? "◆" : "◇"}
                </button>}
            </div>
            {header.column.getCanResize() && <div
              role="separator" aria-orientation="vertical"
              aria-label={"Redimensionar coluna " + header.column.id}
              aria-valuemin={header.column.columnDef.minSize || 100}
              aria-valuemax={header.column.columnDef.maxSize || 640}
              aria-valuenow={header.column.getSize()} tabIndex={0}
              onMouseDown={header.getResizeHandler()}
              onTouchStart={header.getResizeHandler()}
              onDoubleClick={() => { header.column.resetSize(); onWidthsChange({ ...columnWidths, [header.column.id]: header.column.columnDef.size || 180 }); }}
              onKeyDown={event => {
                if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
                event.preventDefault(); event.stopPropagation();
                const width = Math.max(100, Math.min(640, header.column.getSize() + (event.key === "ArrowRight" ? 16 : -16)));
                setSizes(previous => ({ ...previous, [header.column.id]: width }));
              }}
              className="absolute inset-y-0 right-0 w-2 cursor-col-resize touch-none hover:bg-[var(--color-blue)]/20 focus-visible:bg-[var(--color-blue)]/20" />}
          </th>)}
        </tr>)}
      </thead>
      <tbody>
        {table.getRowModel().rows.map(row => <tr key={row.id}
          data-record-row tabIndex={0} aria-selected={row.getIsSelected()}
          onKeyDown={event => keyboardRow(event, row.id, row.original)}
          data-selected={row.getIsSelected() ? "true" : undefined}
          className={cn("group/row border-b transition-colors duration-[var(--motion-standard)] hover:bg-[var(--color-panel)] focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--color-blue)] motion-reduce:transition-none",
            row.getIsSelected() && "bg-[var(--color-blue-tint)]/50",
            compact ? "h-8" : "h-11")}>
          {row.getVisibleCells().map(cell => <td key={cell.id} style={stickyStyle(cell.column)}
            className={cn("max-w-0 overflow-hidden border-b border-[var(--color-border-subtle)] px-3 text-xs text-[var(--color-slate-600)]",
              compact ? "h-8" : "h-11")}>
            {flexRender(cell.column.columnDef.cell, cell.getContext())}
          </td>)}
        </tr>)}
      </tbody>
    </table>
  </div>;
}
