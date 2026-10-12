"""Structural validation and traversal helpers for workflow DAGs."""

from __future__ import annotations

from collections import defaultdict, deque

from app.controlled_edit.workflow.schemas import (
    EdgeKind,
    EditWorkflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowValidationError,
)


def validate_workflow(workflow: EditWorkflow) -> None:
    """Raise ``WorkflowValidationError`` when the graph is not a valid template."""
    nodes = {node.id: node for node in workflow.nodes}
    if len(nodes) != len(workflow.nodes):
        raise WorkflowValidationError("duplicate node ids")
    edge_ids = [edge.id for edge in workflow.edges]
    if len(edge_ids) != len(set(edge_ids)):
        raise WorkflowValidationError("duplicate edge ids")

    inputs = [n for n in workflow.nodes if n.type == WorkflowNodeType.INPUT]
    outputs = [n for n in workflow.nodes if n.type == WorkflowNodeType.OUTPUT]
    if len(inputs) != 1:
        raise WorkflowValidationError(
            "workflow must have exactly one input node",
            details={"input_count": len(inputs)},
        )
    if not outputs:
        raise WorkflowValidationError("workflow must have at least one output node")

    for edge in workflow.edges:
        if edge.source not in nodes or edge.target not in nodes:
            raise WorkflowValidationError(
                f"edge {edge.id} references unknown node",
                details={"source": edge.source, "target": edge.target},
            )
        if edge.source == edge.target:
            raise WorkflowValidationError(f"edge {edge.id} is a self-loop")
        source = nodes[edge.source]
        if source.type == WorkflowNodeType.CONDITION:
            if edge.kind not in (EdgeKind.PASS, EdgeKind.FAIL):
                raise WorkflowValidationError(
                    f"condition node {source.id} edges must be pass or fail",
                    details={"edge_id": edge.id},
                )
        elif edge.kind != EdgeKind.DEFAULT:
            raise WorkflowValidationError(
                f"non-condition edge {edge.id} must use kind=default",
            )

    if _has_cycle(workflow.nodes, workflow.edges):
        raise WorkflowValidationError("workflow graph contains a cycle")

    reachable = _reachable_from(inputs[0].id, workflow.edges)
    for output in outputs:
        if output.id not in reachable:
            raise WorkflowValidationError(
                f"output node {output.id} is not reachable from input",
            )


def topological_layers(nodes: list[WorkflowNode], edges: list[WorkflowEdge]) -> list[list[str]]:
    """Return node ids in Kahn layers (ready sets), ignoring edge kind."""
    node_ids = {node.id for node in nodes}
    indegree = {node_id: 0 for node_id in node_ids}
    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.source in node_ids and edge.target in node_ids:
            children[edge.source].append(edge.target)
            indegree[edge.target] += 1
    queue = deque(sorted(node_id for node_id, deg in indegree.items() if deg == 0))
    layers: list[list[str]] = []
    seen = 0
    while queue:
        layer = list(queue)
        layers.append(layer)
        seen += len(layer)
        queue.clear()
        for node_id in layer:
            for child in children[node_id]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        queue = deque(sorted(queue))
    if seen != len(node_ids):
        raise WorkflowValidationError("workflow graph contains a cycle")
    return layers


def outgoing(edges: list[WorkflowEdge], source_id: str) -> list[WorkflowEdge]:
    """Return edges leaving ``source_id``."""
    return [edge for edge in edges if edge.source == source_id]


def incoming(edges: list[WorkflowEdge], target_id: str) -> list[WorkflowEdge]:
    """Return edges entering ``target_id``."""
    return [edge for edge in edges if edge.target == target_id]


def _has_cycle(nodes: list[WorkflowNode], edges: list[WorkflowEdge]) -> bool:
    try:
        topological_layers(nodes, edges)
    except WorkflowValidationError:
        return True
    return False


def _reachable_from(start: str, edges: list[WorkflowEdge]) -> set[str]:
    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        children[edge.source].append(edge.target)
    seen = {start}
    stack = [start]
    while stack:
        current = stack.pop()
        for child in children[current]:
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen
