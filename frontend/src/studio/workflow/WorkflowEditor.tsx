"use client";

import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createWorkflow,
  getWorkflow,
  getWorkflowRun,
  listWorkflows,
  resumeWorkflowRun,
  startWorkflowRun,
  updateWorkflow,
  type EditWorkflow,
  type WorkflowEdge as ApiEdge,
  type WorkflowNode as ApiNode,
  type WorkflowNodeType,
  type WorkflowRun,
} from "@/lib/workflow-api";

type FlowNodeData = {
  nodeType: WorkflowNodeType;
  label: string;
  instruction?: string;
  lockRoles?: string;
  conditionKind?: string;
  mergeMode?: string;
};

function WorkflowFlowNode({ data }: NodeProps) {
  const d = data as FlowNodeData;
  const tone =
    d.nodeType === "input"
      ? "border-sky-500"
      : d.nodeType === "output"
        ? "border-emerald-500"
        : d.nodeType === "condition"
          ? "border-amber-500"
          : d.nodeType === "merge"
            ? "border-violet-500"
            : "border-line-strong";
  return (
    <div className={`min-w-[140px] rounded-md border-2 bg-surface-1 px-3 py-2 shadow-sm ${tone}`}>
      <Handle type="target" position={Position.Left} className="!bg-ink" />
      <div className="text-[10px] uppercase tracking-wide text-faint">{d.nodeType}</div>
      <div className="text-xs font-semibold text-ink">{d.label || d.nodeType}</div>
      {d.instruction ? (
        <div className="mt-1 max-w-[180px] truncate text-[10px] text-faint">{d.instruction}</div>
      ) : null}
      <Handle type="source" position={Position.Right} className="!bg-ink" />
    </div>
  );
}

const nodeTypes = { workflow: WorkflowFlowNode };

function toFlow(workflow: EditWorkflow): { nodes: Node[]; edges: Edge[] } {
  return {
    nodes: workflow.nodes.map((n) => ({
      id: n.id,
      type: "workflow",
      position: { x: n.position.x, y: n.position.y },
      data: {
        nodeType: n.type,
        label: n.label,
        instruction: n.edit?.instruction,
        lockRoles: n.edit?.lock_roles.join(","),
        conditionKind: n.condition?.kind,
        mergeMode: n.merge?.mode,
      } satisfies FlowNodeData,
    })),
    edges: workflow.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.kind === "default" ? undefined : e.kind,
      data: { kind: e.kind },
    })),
  };
}

function fromFlow(nodes: Node[], edges: Edge[], title: string): {
  title: string;
  nodes: ApiNode[];
  edges: ApiEdge[];
} {
  return {
    title,
    nodes: nodes.map((n) => {
      const d = n.data as FlowNodeData;
      const base: ApiNode = {
        id: n.id,
        type: d.nodeType,
        label: d.label || d.nodeType,
        position: { x: n.position.x, y: n.position.y },
      };
      if (d.nodeType === "edit") {
        base.edit = {
          instruction: d.instruction?.trim() || "edit",
          lock_roles: (d.lockRoles || "")
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          target_roles: [],
        };
      }
      if (d.nodeType === "condition") {
        base.condition = {
          kind: (d.conditionKind as "target_applied") || "target_applied",
        };
      }
      if (d.nodeType === "merge") {
        base.merge = { mode: (d.mergeMode as "multi_ref") || "multi_ref" };
      }
      return base;
    }),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      kind: ((e.data as { kind?: string } | undefined)?.kind ||
        (e.label === "pass" || e.label === "fail" ? e.label : "default")) as ApiEdge["kind"],
    })),
  };
}

function newId(): string {
  return crypto.randomUUID();
}

function WorkflowEditorCanvas({ initialWorkflowId }: { initialWorkflowId?: string }) {
  const [workflows, setWorkflows] = useState<EditWorkflow[]>([]);
  const [activeId, setActiveId] = useState<string | null>(initialWorkflowId ?? null);
  const [title, setTitle] = useState("Untitled workflow");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [busy, setBusy] = useState(false);

  const reloadList = useCallback(async () => {
    const list = await listWorkflows();
    setWorkflows(list);
  }, []);

  const loadWorkflow = useCallback(
    async (workflowId: string) => {
      const wf = await getWorkflow(workflowId);
      setActiveId(wf.id);
      setTitle(wf.title);
      const flow = toFlow(wf);
      setNodes(flow.nodes);
      setEdges(flow.edges);
    },
    [setEdges, setNodes],
  );

  /* Fetch templates (and optional ?id=) once on mount. */
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const list = await listWorkflows();
        if (!cancelled) setWorkflows(list);
        if (!cancelled && initialWorkflowId) {
          const wf = await getWorkflow(initialWorkflowId);
          if (cancelled) return;
          setActiveId(wf.id);
          setTitle(wf.title);
          const flow = toFlow(wf);
          setNodes(flow.nodes);
          setEdges(flow.edges);
        }
      } catch (err) {
        if (!cancelled) setStatus(err instanceof Error ? err.message : "加载失败");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount bootstrap from API
  }, []);

  useEffect(() => {
    if (!run || run.status === "succeeded" || run.status === "failed") return;
    const timer = window.setInterval(() => {
      void getWorkflowRun(run.id)
        .then((latest) => setRun(latest))
        .catch((err: Error) => setStatus(err.message));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [run]);

  const onConnect = useCallback(
    (connection: Connection) => {
      const source = nodes.find((n) => n.id === connection.source);
      const sourceType = (source?.data as FlowNodeData | undefined)?.nodeType;
      const kind = sourceType === "condition" ? "pass" : "default";
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: newId(),
            label: kind === "default" ? undefined : kind,
            data: { kind },
          },
          eds,
        ),
      );
    },
    [nodes, setEdges],
  );

  const addNode = (type: WorkflowNodeType) => {
    const id = newId();
    setNodes((prev) => [
      ...prev,
      {
        id,
        type: "workflow",
        position: { x: 120 + prev.length * 40, y: 80 + prev.length * 30 },
        data: {
          nodeType: type,
          label: type,
          instruction: type === "edit" ? "describe the change" : undefined,
          lockRoles: type === "edit" ? "face" : undefined,
          conditionKind: type === "condition" ? "target_applied" : undefined,
          mergeMode: type === "merge" ? "multi_ref" : undefined,
        } satisfies FlowNodeData,
      },
    ]);
  };

  const handleSave = async () => {
    setBusy(true);
    setStatus(null);
    try {
      const body = fromFlow(nodes, edges, title);
      if (activeId) {
        const saved = await updateWorkflow(activeId, body);
        setStatus(`已保存 ${saved.title}`);
      } else {
        const saved = await createWorkflow(body);
        setActiveId(saved.id);
        setStatus(`已创建 ${saved.title}`);
      }
      await reloadList();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRun = async (file: File | null) => {
    if (!file || !activeId) {
      setStatus("请先保存工作流并选择图片");
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      // Persist graph before running.
      await updateWorkflow(activeId, fromFlow(nodes, edges, title));
      const started = await startWorkflowRun(activeId, file, `Run: ${title}`);
      setRun(started);
      setStatus(`已开始运行 ${started.id.slice(0, 8)}…`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "运行失败");
    } finally {
      setBusy(false);
    }
  };

  const selected = useMemo(
    () => workflows.find((w) => w.id === activeId) ?? null,
    [workflows, activeId],
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface-0 text-ink">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <Link href="/" className="text-xs text-faint hover:text-ink">
          ← 画布
        </Link>
        <h1 className="text-sm font-semibold">编辑工作流</h1>
        <input
          className="min-w-[160px] flex-1 rounded border border-line bg-surface-1 px-2 py-1 text-xs"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          aria-label="工作流标题"
        />
        <select
          className="rounded border border-line bg-surface-1 px-2 py-1 text-xs"
          value={activeId ?? ""}
          onChange={(e) => {
            const id = e.target.value;
            if (id) void loadWorkflow(id);
            else {
              setActiveId(null);
              setNodes([]);
              setEdges([]);
            }
          }}
        >
          <option value="">新建 / 选择…</option>
          {workflows.map((w) => (
            <option key={w.id} value={w.id}>
              {w.title}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleSave()}
          className="rounded bg-ink px-3 py-1 text-xs text-surface-0 disabled:opacity-40"
        >
          保存
        </button>
        <label className="cursor-pointer rounded border border-line px-3 py-1 text-xs hover:bg-surface-1">
          运行…
          <input
            type="file"
            accept="image/*"
            className="hidden"
            disabled={busy || !activeId}
            onChange={(e) => void handleRun(e.target.files?.[0] ?? null)}
          />
        </label>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-48 shrink-0 flex-col gap-2 border-r border-line p-3 text-xs">
          <p className="font-semibold">添加节点</p>
          {(["input", "edit", "condition", "merge", "output"] as WorkflowNodeType[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => addNode(t)}
              className="rounded border border-line px-2 py-1 text-left hover:bg-surface-1"
            >
              + {t}
            </button>
          ))}
          <p className="mt-2 text-[10px] text-faint">
            条件出边：在边 data.kind 设为 pass/fail（保存后从列表重载可编辑）。分叉=多条出边；合并用 merge 节点。
          </p>
          {selected?.source_session_id ? (
            <p className="text-[10px] text-faint">来源会话 {selected.source_session_id.slice(0, 8)}…</p>
          ) : null}
          {status ? <p className="text-[11px] text-accent">{status}</p> : null}
          {run ? (
            <div className="mt-2 space-y-1 rounded border border-line p-2">
              <p>运行：{run.status}</p>
              {run.session_id ? (
                <p className="break-all text-[10px] text-faint">session {run.session_id}</p>
              ) : null}
              {run.error ? <p className="text-danger">{run.error}</p> : null}
              {run.status === "waiting_manual" ? (
                <div className="flex gap-1">
                  <button
                    type="button"
                    className="rounded bg-ink px-2 py-0.5 text-surface-0"
                    onClick={() => void resumeWorkflowRun(run.id, true).then(setRun)}
                  >
                    通过
                  </button>
                  <button
                    type="button"
                    className="rounded border border-line px-2 py-0.5"
                    onClick={() => void resumeWorkflowRun(run.id, false).then(setRun)}
                  >
                    失败边
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
        </aside>
        <div className="min-h-0 flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
          >
            <Background />
            <MiniMap />
            <Controls />
          </ReactFlow>
        </div>
      </div>
    </div>
  );
}

export function WorkflowEditor({ initialWorkflowId }: { initialWorkflowId?: string }) {
  return (
    <ReactFlowProvider>
      <WorkflowEditorCanvas initialWorkflowId={initialWorkflowId} />
    </ReactFlowProvider>
  );
}
