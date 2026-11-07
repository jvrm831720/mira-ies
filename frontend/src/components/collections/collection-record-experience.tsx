"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { collectionsApi, type CollectionCaseDetail } from "@/lib/collections-api";
import { collectionDetailHref, collectionReturnHref } from "@/lib/navigation-context";
import { RecordDrawer } from "@/components/record/record-drawer";
import { RecordPage } from "@/components/record/record-page";
import { RecordSections } from "@/components/record/record-sections";
import { RecordProperties } from "@/components/record/record-properties";
import { RecordRelations } from "@/components/record/record-relations";
import { Record360Overview } from "@/components/record/record-360-overview";
import { RecordLoadState } from "@/components/record/record-load-state";
import { RecordActivity } from "@/components/record/record-activity";
import {
  collectionRecordIdentity, collectionRecordProperties, collectionRecordRelations,
  collectionRecordTimeline,
} from "@/components/record/collection-record-data";
import { canReadCollectionRecord } from "./collection-record-access";
import { Header } from "@/components/layout/header";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function FinancialSourceNotice() {
  return <p role="note" className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3 text-xs text-[var(--color-slate-600)]">
    Este registro é somente leitura. Valores, situações e eventos foram informados pela origem
    e não constituem comprovante de pagamento, execução de cobrança ou conciliação bancária.
  </p>;
}

/** The same domain projection is used in preview and full page. */
function CaseSections({
  detail, compact,
}: {
  detail: CollectionCaseDetail; compact: boolean;
}) {
  const groups = collectionRecordProperties(detail.case);
  const relations = collectionRecordRelations(detail.case);
  const timeline = collectionRecordTimeline(detail);
  return <RecordSections key={detail.case.id} sections={[
    {
      id: "overview", label: "Propriedades",
      content: <div className="space-y-4">
        {compact
          ? <Record360Overview groups={groups} relations={relations} compact />
          : <RecordRelations relations={relations} />}
        <FinancialSourceNotice />
      </div>,
    },
    {
      id: "activity", label: "Atividade financeira",
      content: <RecordActivity events={timeline.events} truncated={timeline.truncated}
        emptyMessage="Nenhum evento financeiro confirmado foi disponibilizado pela origem." />,
    },
  ]} />;
}

function useCaseDetail(id: string | null, tenantId: string | undefined, userId: string | undefined, allowed: boolean) {
  return useQuery({
    queryKey: ["collections", "detail", tenantId, userId, id],
    queryFn: () => collectionsApi.detail(id!),
    enabled: allowed && Boolean(tenantId && userId && id && UUID.test(id)),
    retry: false, staleTime: 20_000,
  });
}

/** Case preview follows the same dialog and property / activity contract as StudentDrawer. */
export function CollectionCaseDrawer({
  caseId, onClose, listingHref, tenantId, userId, allowed,
}: {
  caseId: string | null; onClose: () => void; listingHref: string;
  tenantId?: string; userId?: string; allowed: boolean;
}) {
  const validId = caseId && UUID.test(caseId) ? caseId : null;
  const q = useCaseDetail(validId, tenantId, userId, allowed);
  const record = validId ? collectionRecordIdentity(validId, q.data?.case) : null;
  const ready = allowed && q.data?.case;
  return <RecordDrawer record={record} onClose={onClose}
    fullPageHref={ready && validId ? collectionDetailHref(validId, listingHref) : undefined}
    actions={ready ? [{ id: "refresh", label: q.isFetching ? "Atualizando…" : "Atualizar",
      disabled: q.isFetching, onClick: () => void q.refetch() }] : []}>
    {!allowed ? <RecordLoadState state="denied" domain="caso financeiro" />
      : !validId ? <RecordLoadState state="missing" domain="caso financeiro" />
      : q.isLoading ? <RecordLoadState state="loading" domain="caso financeiro" />
      : q.isError ? <RecordLoadState state="error" onRetry={() => void q.refetch()} domain="caso financeiro" />
      : q.data?.case ? <CaseSections detail={q.data} compact />
      : <RecordLoadState state="missing" domain="caso financeiro" />}
  </RecordDrawer>;
}

/** Full record route. The back link is validated to exactly /cobranca, never an external URL. */
export function CollectionCaseFullPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const caseId = params.id;
  const me = useQuery({ queryKey: ["org-me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const allowed = canReadCollectionRecord(me.data);
  const q = useCaseDetail(caseId, me.data?.tenant_id, me.data?.user_id, allowed);
  const backHref = collectionReturnHref(search.get("from"));
  return <>
    <Header title="Caso financeiro" compact />
    {me.isLoading ? <main className="mira-page mx-auto max-w-[1400px] p-6">
      <RecordLoadState state="loading" domain="caso financeiro" /></main>
      : me.isError || !allowed ? <main className="mira-page mx-auto max-w-[1400px] p-6">
        <RecordLoadState state="denied" domain="caso financeiro" /></main>
      : !UUID.test(caseId) ? <main className="mira-page mx-auto max-w-[1400px] p-6">
        <RecordLoadState state="missing" domain="caso financeiro" /></main>
      : q.isLoading ? <main className="mira-page mx-auto max-w-[1400px] p-6">
        <RecordLoadState state="loading" domain="caso financeiro" /></main>
      : q.isError ? <main className="mira-page mx-auto max-w-[1400px] p-6">
        <RecordLoadState state="error" onRetry={() => void q.refetch()} domain="caso financeiro" /></main>
      : q.data?.case ? <RecordPage
        record={collectionRecordIdentity(caseId, q.data.case)}
        backHref={backHref}
        actions={[{ id: "refresh", label: q.isFetching ? "Atualizando…" : "Atualizar",
          disabled: q.isFetching, onClick: () => void q.refetch() }]}
        aside={<RecordProperties compact groups={collectionRecordProperties(q.data.case)} />}>
        <CaseSections detail={q.data} compact={false} />
      </RecordPage>
      : <main className="mira-page mx-auto max-w-[1400px] p-6">
        <RecordLoadState state="missing" domain="caso financeiro" /></main>}
  </>;
}
