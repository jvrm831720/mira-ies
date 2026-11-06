"use client";

import { useParams } from "next/navigation";
import { WorkflowExperience } from "@/components/workflows/workflow-experience";

export default function WorkflowDetailPage() {
  const params = useParams<{ kind: string; id: string }>();
  return <WorkflowExperience selectedKind={params.kind} selectedId={params.id} />;
}
