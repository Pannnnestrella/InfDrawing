"""Build a workflow template from a connected version-tree subgraph."""

from __future__ import annotations

from app.controlled_edit.schemas import EditVersion, SessionTree, VersionStatus
from app.controlled_edit.workflow.graph import validate_workflow
from app.controlled_edit.workflow.roles import entity_role, locked_roles, role_token
from app.controlled_edit.workflow.schemas import (
    EditNodeConfig,
    EditWorkflow,
    EdgeKind,
    NodePosition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowValidationError,
    new_id,
)


def export_subgraph_to_workflow(
    tree: SessionTree,
    version_ids: list[str],
    *,
    owner_key_id: str,
    title: str = "Exported workflow",
) -> EditWorkflow:
    """Convert a connected set of versions into an edit workflow DAG.

    The session root (or the unique parent outside the selection) becomes the
    ``input`` node. Each selected non-root succeeded version with an instruction
    becomes an ``edit`` node. Edges follow ``parent_id``. Condition nodes are not
    inferred from history; users can add them in the editor.
    """
    selected = set(version_ids)
    by_id = {version.id: version for version in tree.versions}
    missing = selected - by_id.keys()
    if missing:
        raise WorkflowValidationError(
            "unknown version ids in export selection",
            details={"missing": sorted(missing)},
        )
    if not _is_connected(selected, by_id):
        raise WorkflowValidationError("selected versions must form a connected subgraph")

    roots_in_selection = [
        vid
        for vid in selected
        if by_id[vid].parent_id is None or by_id[vid].parent_id not in selected
    ]
    if len(roots_in_selection) != 1:
        raise WorkflowValidationError(
            "selection must have exactly one root entry",
            details={"roots": roots_in_selection},
        )
    entry_id = roots_in_selection[0]
    entry = by_id[entry_id]

    input_node = WorkflowNode(
        id=new_id(),
        type=WorkflowNodeType.INPUT,
        label="Input",
        position=NodePosition(x=0, y=0),
    )
    version_to_node: dict[str, str] = {}
    # Map the entry version (usually session root) to the input node.
    version_to_node[entry_id] = input_node.id

    nodes: list[WorkflowNode] = [input_node]
    edges: list[WorkflowEdge] = []
    lane = 0
    depth_cache: dict[str, int] = {entry_id: 0}

    ordered = sorted(
        (by_id[vid] for vid in selected if vid != entry_id),
        key=lambda v: v.created_at,
    )
    for version in ordered:
        if version.status != VersionStatus.SUCCEEDED and version.instruction is None:
            continue
        parent_id = version.parent_id
        if parent_id is None or parent_id not in version_to_node:
            raise WorkflowValidationError(
                f"version {version.id} has no mapped parent in the selection",
            )
        parent = by_id[parent_id]
        lock_roles = locked_roles(parent.entities)
        target_roles = [
            role_token(entity_id)
            for entity_id in (version.intent.target_entity_ids if version.intent else [])
        ]
        # Prefer leaf roles from known entities when present.
        if version.intent:
            resolved: list[str] = []
            for entity_id in version.intent.target_entity_ids:
                entity = next((e for e in parent.entities if e.id == entity_id), None)
                resolved.append(entity_role(entity) if entity else role_token(entity_id))
            target_roles = resolved

        instruction = (version.instruction or "").strip()
        if not instruction:
            raise WorkflowValidationError(
                f"version {version.id} has no instruction to export",
            )
        prompt_style = None
        if version.prompt_style in ("preserve", "target_only"):
            prompt_style = version.prompt_style
        provider = None
        if version.image_provider in ("dashscope", "openai"):
            provider = version.image_provider

        depth = depth_cache.get(parent_id, 0) + 1
        depth_cache[version.id] = depth
        node = WorkflowNode(
            id=new_id(),
            type=WorkflowNodeType.EDIT,
            label=(instruction[:40] + ("…" if len(instruction) > 40 else "")),
            position=NodePosition(x=float(depth * 220), y=float(lane * 120)),
            edit=EditNodeConfig(
                instruction=instruction,
                lock_roles=lock_roles,
                target_roles=target_roles,
                prompt_style=prompt_style,
                image_provider=provider,
                image_model=version.image_model,
            ),
        )
        lane += 1
        nodes.append(node)
        version_to_node[version.id] = node.id
        edges.append(
            WorkflowEdge(
                source=version_to_node[parent_id],
                target=node.id,
                kind=EdgeKind.DEFAULT,
            )
        )

    # Leaves in the selection become outputs.
    children: dict[str, list[str]] = {vid: [] for vid in selected}
    for vid in selected:
        parent_id = by_id[vid].parent_id
        if parent_id in selected:
            children[parent_id].append(vid)
    leaves = [vid for vid in selected if not children[vid] and vid in version_to_node]
    if entry_id in leaves and len(selected) == 1:
        # Only root selected: still allow a trivial input→output workflow.
        out = WorkflowNode(
            id=new_id(),
            type=WorkflowNodeType.OUTPUT,
            label="Output",
            position=NodePosition(x=220, y=0),
        )
        nodes.append(out)
        edges.append(WorkflowEdge(source=input_node.id, target=out.id))
    else:
        for index, leaf_id in enumerate(leaves):
            if leaf_id == entry_id:
                continue
            out = WorkflowNode(
                id=new_id(),
                type=WorkflowNodeType.OUTPUT,
                label="Output" if len(leaves) == 1 else f"Output {index + 1}",
                position=NodePosition(
                    x=float((depth_cache.get(leaf_id, 1) + 1) * 220),
                    y=float(index * 120),
                ),
            )
            nodes.append(out)
            edges.append(
                WorkflowEdge(source=version_to_node[leaf_id], target=out.id)
            )

    if not any(n.type == WorkflowNodeType.OUTPUT for n in nodes):
        raise WorkflowValidationError("export produced no output nodes")

    workflow = EditWorkflow(
        owner_key_id=owner_key_id,
        title=title[:120] or "Exported workflow",
        nodes=nodes,
        edges=edges,
        source_session_id=tree.session.id,
    )
    validate_workflow(workflow)
    return workflow


def _is_connected(selected: set[str], by_id: dict[str, EditVersion]) -> bool:
    if not selected:
        return False
    start = next(iter(selected))
    stack = [start]
    seen = {start}
    # Undirected traversal along parent links within the selection.
    undirected: dict[str, set[str]] = {vid: set() for vid in selected}
    for vid in selected:
        parent_id = by_id[vid].parent_id
        if parent_id in selected:
            undirected[vid].add(parent_id)
            undirected[parent_id].add(vid)
    while stack:
        current = stack.pop()
        for neighbor in undirected[current]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return seen == selected
