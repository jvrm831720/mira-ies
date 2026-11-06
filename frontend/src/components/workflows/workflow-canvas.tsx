"use client";

import { useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Clock3, LockKeyhole, Minus, Plus, Workflow } from "@/components/ui/icons";
import type { WorkflowBlock, BlockState } from "./workflow-model";

const color: Record<BlockState, string> = {
  verified: "border-[var(--color-legacy-d9e6dd)] bg-[var(--color-legacy-f3faf5)] text-[var(--color-legacy-287347)]",
  pending: "border-[var(--color-legacy-e6e7ec)] bg-[var(--color-legacy-f6f7f9)] text-[var(--color-legacy-737783)]",
  attention: "border-[var(--color-legacy-f7ddb4)] bg-[var(--color-legacy-fff7ea)] text-[var(--color-legacy-a26818)]",
  unavailable: "border-[var(--color-legacy-ebe8e8)] bg-[var(--color-legacy-fafafa)] text-[var(--color-legacy-9a9aa0)]",
};
const label: Record<BlockState, string> = {
  verified: "Registrado", pending: "Pendente", attention: "Requer atenção",
  unavailable: "Sem evidência / indisponível",
};

export function WorkflowCanvas({
  nodes, selectedId, onSelect,
}: {
  nodes: WorkflowBlock[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const [zoom, setZoom] = useState(100);
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const go = (index: number, delta: number) => {
    const next = Math.max(0, Math.min(nodes.length - 1, index + delta));
    refs.current[next]?.focus();
    onSelect(nodes[next].id);
  };
  return (
    <section aria-label="Canvas do processo" className="flex min-h-[610px] min-w-0 flex-col overflow-hidden rounded-xl border border-[var(--color-legacy-e7e9ed)] bg-[var(--color-source-f9fafb)]">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--color-legacy-e8e9ec)] bg-white px-3 py-2.5 sm:px-4">
        <div className="flex items-center gap-2 text-xs font-medium text-[var(--color-legacy-575e69)]">
          <Workflow className="h-4 w-4" aria-hidden="true" />
          <span>Fluxo observado</span>
          <span className="hidden text-[var(--color-legacy-9398a1)] sm:inline">· representação de contratos existentes</span>
        </div>
        <div className="flex items-center gap-1 rounded-md border border-[var(--color-legacy-e8e9ec)] bg-white p-1">
          <button aria-label="Reduzir zoom" type="button" disabled={zoom <= 75} onClick={() => setZoom(n => Math.max(75, n - 25))}
            className="rounded p-1.5 text-[var(--color-legacy-454952)] hover:bg-[var(--color-legacy-f4f5f6)] disabled:opacity-30"><Minus className="h-3.5 w-3.5" /></button>
          <span className="w-12 text-center text-[length:var(--type-caption)] tabular-nums text-[var(--color-legacy-555a64)]">{zoom}%</span>
          <button aria-label="Aumentar zoom" type="button" disabled={zoom >= 125} onClick={() => setZoom(n => Math.min(125, n + 25))}
            className="rounded p-1.5 text-[var(--color-legacy-454952)] hover:bg-[var(--color-legacy-f4f5f6)] disabled:opacity-30"><Plus className="h-3.5 w-3.5" /></button>
          <button type="button" onClick={() => setZoom(100)} className="ml-1 rounded border-l px-2 py-1 text-[length:var(--type-caption)] text-[var(--color-legacy-656a73)] hover:bg-[var(--color-legacy-f4f5f6)]">100%</button>
        </div>
      </div>
      <div className="flex-1 overflow-auto px-3 py-8 sm:px-8">
        <div className="mx-auto w-full max-w-[420px] pb-10 transition-transform duration-150" style={{ zoom: zoom / 100 }}>
          {nodes.map((node, index) => {
            const Icon = node.state === "verified" ? CheckCircle2
              : node.state === "attention" ? AlertCircle
              : node.state === "unavailable" ? LockKeyhole : Clock3;
            return (
              <div key={node.id} className="flex flex-col items-center">
                <button
                  ref={element => { refs.current[index] = element; }}
                  type="button"
                  data-workflow-node
                  onClick={() => onSelect(node.id)}
                  onKeyDown={event => {
                    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
                      event.preventDefault(); go(index, 1);
                    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
                      event.preventDefault(); go(index, -1);
                    }
                  }}
                  aria-pressed={node.id === selectedId}
                  aria-label={node.title + ". " + label[node.state] + ". Ver propriedades."}
                  className={"w-full rounded-xl border bg-white p-4 text-left shadow-[0_1px_2px_rgba(16,24,40,0.05)] transition-all hover:border-[var(--color-legacy-a3b9ed)] hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-legacy-2563eb)] " +
                    (node.id === selectedId ? "border-[var(--color-legacy-2563eb)] ring-2 ring-[var(--color-legacy-2563eb)]/15" : "border-[var(--color-legacy-e3e6eb)]")}
                >
                  <div className="flex items-start gap-3">
                    <div className={"grid h-9 w-9 shrink-0 place-items-center rounded-lg border " + color[node.state]}>
                      <Icon className="h-[17px] w-[17px]" aria-hidden="true" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[length:var(--type-body-compact)] font-semibold text-[var(--color-legacy-171a20)]">{node.title}</p>
                      <p className="mt-1 text-[length:var(--type-caption)] leading-5 text-[var(--color-legacy-6f7782)]">{node.description}</p>
                      <p className="mt-2 text-[length:var(--type-overline)] font-medium text-[var(--color-legacy-7c8490)]">{label[node.state]}</p>
                    </div>
                    <span aria-hidden="true" className="mt-0.5 h-2 w-2 rounded-full bg-[var(--color-legacy-ccd1da)]" />
                  </div>
                </button>
                {index < nodes.length - 1 && <div aria-hidden="true" className="flex h-10 flex-col items-center">
                  <span className="h-8 border-l border-[var(--color-legacy-d4d8df)]" />
                  <span className="h-0 w-0 border-x-[4px] border-t-[5px] border-x-transparent border-t-[var(--color-legacy-d4d8df)]" />
                </div>}
              </div>
            );
          })}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-legacy-e8e9ec)] bg-white px-4 py-2.5">
        <p className="text-[length:var(--type-caption)] text-[var(--color-legacy-6e7480)]">Setas ↑↓ para navegar · clique para inspecionar</p>
        <p className="text-[length:var(--type-caption)] text-[var(--color-legacy-6e7480)]">Sem execução ou publicação neste editor</p>
      </div>
    </section>
  );
}
