"use client";

import { useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Clock3, LockKeyhole, Minus, Plus, Workflow } from "@/components/ui/icons";
import type { WorkflowBlock, BlockState } from "./workflow-model";

const color: Record<BlockState, string> = {
  verified: "border-[#D9E6DD] bg-[#F3FAF5] text-[#287347]",
  pending: "border-[#E6E7EC] bg-[#F6F7F9] text-[#737783]",
  attention: "border-[#F7DDB4] bg-[#FFF7EA] text-[#A26818]",
  unavailable: "border-[#EBE8E8] bg-[#FAFAFA] text-[#9A9AA0]",
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
    <section aria-label="Canvas do processo" className="flex min-h-[610px] min-w-0 flex-col overflow-hidden rounded-xl border border-[#E7E9ED] bg-[#F9FAFB]">
      <div className="flex items-center justify-between gap-3 border-b border-[#E8E9EC] bg-white px-3 py-2.5 sm:px-4">
        <div className="flex items-center gap-2 text-xs font-medium text-[#575E69]">
          <Workflow className="h-4 w-4" aria-hidden="true" />
          <span>Fluxo observado</span>
          <span className="hidden text-[#9398A1] sm:inline">· representação de contratos existentes</span>
        </div>
        <div className="flex items-center gap-1 rounded-md border border-[#E8E9EC] bg-white p-1">
          <button aria-label="Reduzir zoom" type="button" disabled={zoom <= 75} onClick={() => setZoom(n => Math.max(75, n - 25))}
            className="rounded p-1.5 text-[#454952] hover:bg-[#F4F5F6] disabled:opacity-30"><Minus className="h-3.5 w-3.5" /></button>
          <span className="w-12 text-center text-[11px] tabular-nums text-[#555A64]">{zoom}%</span>
          <button aria-label="Aumentar zoom" type="button" disabled={zoom >= 125} onClick={() => setZoom(n => Math.min(125, n + 25))}
            className="rounded p-1.5 text-[#454952] hover:bg-[#F4F5F6] disabled:opacity-30"><Plus className="h-3.5 w-3.5" /></button>
          <button type="button" onClick={() => setZoom(100)} className="ml-1 rounded border-l px-2 py-1 text-[11px] text-[#656A73] hover:bg-[#F4F5F6]">100%</button>
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
                  className={"w-full rounded-xl border bg-white p-4 text-left shadow-[0_1px_2px_rgba(16,24,40,0.05)] transition-all hover:border-[#A3B9ED] hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] " +
                    (node.id === selectedId ? "border-[#2563EB] ring-2 ring-[#2563EB]/15" : "border-[#E3E6EB]")}
                >
                  <div className="flex items-start gap-3">
                    <div className={"grid h-9 w-9 shrink-0 place-items-center rounded-lg border " + color[node.state]}>
                      <Icon className="h-[17px] w-[17px]" aria-hidden="true" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-semibold text-[#171A20]">{node.title}</p>
                      <p className="mt-1 text-[11px] leading-5 text-[#6F7782]">{node.description}</p>
                      <p className="mt-2 text-[10px] font-medium text-[#7C8490]">{label[node.state]}</p>
                    </div>
                    <span aria-hidden="true" className="mt-0.5 h-2 w-2 rounded-full bg-[#CCD1DA]" />
                  </div>
                </button>
                {index < nodes.length - 1 && <div aria-hidden="true" className="flex h-10 flex-col items-center">
                  <span className="h-8 border-l border-[#D4D8DF]" />
                  <span className="h-0 w-0 border-x-[4px] border-t-[5px] border-x-transparent border-t-[#D4D8DF]" />
                </div>}
              </div>
            );
          })}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E8E9EC] bg-white px-4 py-2.5">
        <p className="text-[11px] text-[#6E7480]">Setas ↑↓ para navegar · clique para inspecionar</p>
        <p className="text-[11px] text-[#6E7480]">Sem execução ou publicação neste editor</p>
      </div>
    </section>
  );
}
