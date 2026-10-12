"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { WorkflowEditor } from "@/studio/workflow/WorkflowEditor";

function WorkflowsInner() {
  const params = useSearchParams();
  const id = params.get("id") ?? undefined;
  return <WorkflowEditor initialWorkflowId={id} />;
}

export default function WorkflowsPage() {
  return (
    <Suspense fallback={<div className="p-4 text-sm text-faint">加载工作流…</div>}>
      <WorkflowsInner />
    </Suspense>
  );
}
