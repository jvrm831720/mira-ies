"use client";

import { useMemo, useState } from "react";
import { Plus, X } from "@/components/ui/icons";
import type { ObjectField, ObjectFilter, FilterOperator } from "./object-index-types";
import { FILTER_OPS } from "./object-index-utils";

type Props<T> = {
  fields: ObjectField<T>[];
  filters: ObjectFilter[];
  onChange: (filters: ObjectFilter[]) => void;
  onClose: () => void;
};

export function ObjectFilterBuilder<T>({ fields, filters, onChange, onClose }: Props<T>) {
  const available = useMemo(() => fields.filter(field => field.filterable), [fields]);
  const [key, setKey] = useState(available[0]?.key || "");
  const field = available.find(item => item.key === key);
  const allowed = FILTER_OPS[field?.type || "text"] || FILTER_OPS.text;
  const [op, setOp] = useState<FilterOperator>("contains");
  const operator = allowed.find(item => item.value === op)?.value || allowed[0].value;
  const [value, setValue] = useState("");
  const [second, setSecond] = useState("");
  const [choiceValues, setChoiceValues] = useState<string[]>([]);
  const [validationError, setValidationError] = useState("");

  function changeField(next: string) {
    setKey(next);
    const selected = available.find(field => field.key === next);
    setOp((FILTER_OPS[selected?.type || "text"] || FILTER_OPS.text)[0].value);
    setValue("");
    setSecond("");
    setChoiceValues([]);
    setValidationError("");
  }

  function apply() {
    if (!field || filters.length >= 8) return;
    setValidationError("");
    const numeric = ["number", "percentage", "currency"].includes(field.type);
    const list = operator === "in";
    const between = operator === "between";
    const items = list
      ? field.options?.length ? choiceValues : value.split(",").map(item => item.trim()).filter(Boolean)
      : between ? [value.trim(), second.trim()] : [value.trim()];
    if (operator !== "empty" && (!items.length || items.some(item => !item))) {
      setValidationError("Informe um valor válido para este filtro.");
      return;
    }
    if (items.length > 12 || items.some(item => item.length > 150)) {
      setValidationError("Limite de 12 valores e 150 caracteres por valor.");
      return;
    }
    if (numeric && items.some(item => !Number.isFinite(Number(item)))) {
      setValidationError("Informe um número válido.");
      return;
    }
    const parse = (item: string) => numeric ? Number(item) : item;
    const nextValue = operator === "empty" ? null
      : list || between ? items.map(parse) : parse(items[0]);
    onChange([...filters, { key, op: operator, value: nextValue }]);
    onClose();
  }

  return <div className="w-[min(90vw,330px)] space-y-3 p-3" role="group" aria-label="Criar filtro AND">
    <div className="flex items-center justify-between">
      <p className="text-xs font-semibold text-[var(--color-ink)]">Novo filtro</p>
      <button type="button" onClick={onClose} aria-label="Fechar filtros"
        className="rounded-md p-1 text-[var(--color-muted)] hover:bg-[var(--color-panel)]"><X className="h-4 w-4" /></button>
    </div>
    <label className="block text-[length:var(--type-caption)] font-medium text-[var(--color-slate-600)]">
      Propriedade
      <select value={key} onChange={event => changeField(event.target.value)}
        className="mt-1 h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-ink)]">
        {available.map(option => <option key={option.key} value={option.key}>{option.title}</option>)}
      </select>
    </label>
    <label className="block text-[length:var(--type-caption)] font-medium text-[var(--color-slate-600)]">
      Operador
      <select value={operator} onChange={event => { setOp(event.target.value as FilterOperator); setValue(""); setSecond(""); setChoiceValues([]); setValidationError(""); }}
        className="mt-1 h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-2 text-xs">
        {allowed.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select>
    </label>
    {operator === "in" && field?.options?.length ? <fieldset className="max-h-[170px] overflow-y-auto rounded-md border border-[var(--color-border)] p-2">
      <legend className="px-1 text-[length:var(--type-caption)] font-medium text-[var(--color-slate-600)]">Valores</legend>
      {field.options.map(option => <label key={option.value} className="flex items-center gap-2 px-1 py-1 text-xs">
        <input type="checkbox" checked={choiceValues.includes(option.value)}
          onChange={event => setChoiceValues(old => event.target.checked
            ? [...old, option.value].slice(0, 12) : old.filter(item => item !== option.value))}
          className="h-4 w-4 accent-[var(--color-blue)]" />{option.label}
      </label>)}
    </fieldset> : operator !== "empty" && <label className="block text-[length:var(--type-caption)] font-medium text-[var(--color-slate-600)]">
      Valor
      {field?.options?.length && !["between", "in"].includes(operator) ?
        <select value={value} onChange={event => setValue(event.target.value)}
          className="mt-1 h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-white px-2 text-xs">
          <option value="">Selecione…</option>
          {field.options.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
        : <input value={value} onChange={event => setValue(event.target.value)}
          type={field?.type === "date" || field?.type === "datetime" ? "date"
            : ["number", "currency", "percentage"].includes(field?.type || "") ? "number" : "text"}
          placeholder={operator === "in" ? "Valores separados por vírgula" : "Informe um valor"}
          className="mt-1 h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] px-2 text-xs focus-visible:ring-2 focus-visible:ring-[var(--color-blue)]" />}
    </label>}
    {operator === "between" && <label className="block text-[length:var(--type-caption)] font-medium text-[var(--color-slate-600)]">
      Até
      <input value={second} onChange={event => setSecond(event.target.value)}
        type={field?.type === "date" ? "date" : ["number", "currency", "percentage"].includes(field?.type || "") ? "number" : "text"}
        className="mt-1 h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] px-2 text-xs" />
    </label>}
    <p className="text-[length:var(--type-caption)] text-[var(--color-muted)]">Aplicado a todos os registros via servidor quando disponível. Até 8 filtros combinados com E.</p>
    {validationError && <p role="alert" className="text-xs text-[var(--color-red)]">{validationError}</p>
    <button type="button" disabled={!field || filters.length >= 8}
      onClick={apply}
      className="flex h-9 w-full items-center justify-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-ink)] text-xs font-medium text-white disabled:opacity-40">
      <Plus className="h-3.5 w-3.5" /> Aplicar filtro
    </button>
  </div>;
}
