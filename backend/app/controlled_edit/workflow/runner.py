"""Execute a workflow DAG into a controlled-edit session tree."""

from __future__ import annotations

import asyncio
import logging

from app.config import Settings, settings
from app.controlled_edit.schemas import (
    EditTurnRequest,
    EditVersion,
    EntityStatus,
    VersionStatus,
)
from app.controlled_edit.service import ControlledEditService
from app.controlled_edit.workflow.graph import incoming, outgoing, validate_workflow
from app.controlled_edit.workflow.repository import WorkflowRepository
from app.controlled_edit.workflow.roles import match_roles
from app.controlled_edit.workflow.schemas import (
    ConditionKind,
    EdgeKind,
    EditWorkflow,
    MergeMode,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowValidationError,
    utc_now,
)

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """Topology-driven executor that materializes versions via ControlledEditService."""

    def __init__(
        self,
        *,
        edit_service: ControlledEditService,
        workflow_repository: WorkflowRepository,
        config: Settings | None = None,
    ) -> None:
        self._edits = edit_service
        self._workflows = workflow_repository
        self._config = config or settings

    async def start_run(
        self,
        owner_key_id: str,
        workflow_id: str,
        image_bytes: bytes,
        media_type: str,
        title: str | None = None,
    ) -> WorkflowRun:
        """Create a session from the image and begin executing the workflow."""
        workflow = await self._workflows.get(workflow_id, owner_key_id)
        if workflow is None:
            raise WorkflowValidationError(f"workflow not found: {workflow_id}")
        validate_workflow(workflow)
        tree = await self._edits.create_session(
            owner_key_id,
            image_bytes,
            media_type,
            title=title or f"Run: {workflow.title}"[:120],
        )
        run = WorkflowRun(
            workflow_id=workflow.id,
            owner_key_id=owner_key_id,
            session_id=tree.session.id,
            status=WorkflowRunStatus.RUNNING,
        )
        input_node = next(n for n in workflow.nodes if n.type == WorkflowNodeType.INPUT)
        run.node_version_map[input_node.id] = tree.versions[0].id
        await self._workflows.create_run(run)
        asyncio.create_task(
            self._safe_execute(owner_key_id, workflow, run.id),
            name=f"workflow-run-{run.id}",
        )
        return run

    async def resume_manual(
        self,
        owner_key_id: str,
        run_id: str,
        *,
        passed: bool,
    ) -> WorkflowRun:
        """Continue a run paused on a manual condition node."""
        run = await self._require_run(owner_key_id, run_id)
        if run.status != WorkflowRunStatus.WAITING_MANUAL or not run.waiting_node_id:
            raise WorkflowValidationError("run is not waiting for manual confirmation")
        workflow = await self._workflows.get(run.workflow_id, owner_key_id)
        if workflow is None:
            raise WorkflowValidationError("workflow missing for run")
        node_id = run.waiting_node_id
        run.waiting_node_id = None
        run.status = WorkflowRunStatus.RUNNING
        await self._workflows.save_run(run)
        asyncio.create_task(
            self._safe_execute(
                owner_key_id,
                workflow,
                run.id,
                bootstrap_edge_kind=EdgeKind.PASS if passed else EdgeKind.FAIL,
                bootstrap_from=node_id,
            ),
            name=f"workflow-resume-{run.id}",
        )
        return await self._require_run(owner_key_id, run_id)

    async def _safe_execute(
        self,
        owner_key_id: str,
        workflow: EditWorkflow,
        run_id: str,
        *,
        bootstrap_edge_kind: EdgeKind | None = None,
        bootstrap_from: str | None = None,
    ) -> None:
        try:
            await self._execute(
                owner_key_id,
                workflow,
                run_id,
                bootstrap_edge_kind=bootstrap_edge_kind,
                bootstrap_from=bootstrap_from,
            )
        except Exception as exc:
            logger.exception("workflow run %s failed", run_id)
            run = await self._workflows.get_run(run_id, owner_key_id)
            if run is None:
                return
            run.status = WorkflowRunStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"[:500]
            run.updated_at = utc_now()
            await self._workflows.save_run(run)

    async def _execute(
        self,
        owner_key_id: str,
        workflow: EditWorkflow,
        run_id: str,
        *,
        bootstrap_edge_kind: EdgeKind | None = None,
        bootstrap_from: str | None = None,
    ) -> None:
        run = await self._require_run(owner_key_id, run_id)
        nodes = {node.id: node for node in workflow.nodes}
        activated: set[tuple[str, str, str]] = set()
        completed: set[str] = set()

        if bootstrap_from and bootstrap_edge_kind:
            completed.add(bootstrap_from)
            for edge in outgoing(workflow.edges, bootstrap_from):
                if edge.kind == bootstrap_edge_kind:
                    activated.add((edge.source, edge.target, edge.kind.value))
            # Preserve already-mapped nodes as completed.
            completed.update(run.node_version_map.keys())
        else:
            input_node = next(n for n in workflow.nodes if n.type == WorkflowNodeType.INPUT)
            completed.add(input_node.id)
            for edge in outgoing(workflow.edges, input_node.id):
                activated.add((edge.source, edge.target, edge.kind.value))

        semaphore = asyncio.Semaphore(max(1, int(self._config.cedit_workflow_concurrency)))

        while True:
            run = await self._require_run(owner_key_id, run_id)
            if run.status in (
                WorkflowRunStatus.FAILED,
                WorkflowRunStatus.SUCCEEDED,
                WorkflowRunStatus.WAITING_MANUAL,
            ):
                return

            ready = self._ready_nodes(nodes, workflow, activated, completed)
            if not ready:
                if self._has_pending_work(workflow, activated, completed):
                    run.status = WorkflowRunStatus.FAILED
                    run.error = "workflow stalled with no runnable nodes"
                    await self._workflows.save_run(run)
                    return
                outputs = [
                    n.id
                    for n in workflow.nodes
                    if n.type == WorkflowNodeType.OUTPUT and n.id in completed
                ]
                if outputs:
                    run.status = WorkflowRunStatus.SUCCEEDED
                    run.output_version_ids = [
                        run.node_version_map[oid]
                        for oid in outputs
                        if oid in run.node_version_map
                    ]
                    await self._workflows.save_run(run)
                    return
                run.status = WorkflowRunStatus.FAILED
                run.error = "workflow finished without reaching an output"
                await self._workflows.save_run(run)
                return

            async def run_one(node_id: str) -> EdgeKind | None:
                async with semaphore:
                    return await self._run_node(
                        owner_key_id, workflow, run_id, node_id, activated
                    )

            results = await asyncio.gather(*(run_one(node_id) for node_id in ready))
            run = await self._require_run(owner_key_id, run_id)
            if run.status == WorkflowRunStatus.WAITING_MANUAL:
                return

            for node_id, cond_kind in zip(ready, results, strict=True):
                completed.add(node_id)
                node = nodes[node_id]
                if node.type == WorkflowNodeType.CONDITION and cond_kind is not None:
                    for edge in outgoing(workflow.edges, node_id):
                        if edge.kind == cond_kind:
                            activated.add((edge.source, edge.target, edge.kind.value))
                elif node.type != WorkflowNodeType.CONDITION:
                    for edge in outgoing(workflow.edges, node_id):
                        activated.add((edge.source, edge.target, edge.kind.value))

    def _ready_nodes(
        self,
        nodes: dict[str, WorkflowNode],
        workflow: EditWorkflow,
        activated: set[tuple[str, str, str]],
        completed: set[str],
    ) -> list[str]:
        ready: list[str] = []
        for node in workflow.nodes:
            if node.id in completed or node.type == WorkflowNodeType.INPUT:
                continue
            ins = incoming(workflow.edges, node.id)
            active_ins = [
                edge
                for edge in ins
                if (edge.source, edge.target, edge.kind.value) in activated
            ]
            if not active_ins:
                continue
            if node.type == WorkflowNodeType.MERGE:
                # Wait for every static predecessor to finish (including condition
                # nodes) so a parallel branch cannot merge before the other path.
                predecessors = {edge.source for edge in ins}
                if predecessors <= completed and active_ins:
                    ready.append(node.id)
            elif all(edge.source in completed for edge in active_ins):
                ready.append(node.id)
        return ready

    def _has_pending_work(
        self,
        workflow: EditWorkflow,
        activated: set[tuple[str, str, str]],
        completed: set[str],
    ) -> bool:
        """True when an incomplete node still has unfinished predecessors on path."""
        for node in workflow.nodes:
            if node.id in completed or node.type == WorkflowNodeType.INPUT:
                continue
            ins = incoming(workflow.edges, node.id)
            active_ins = [
                edge
                for edge in ins
                if (edge.source, edge.target, edge.kind.value) in activated
            ]
            if node.type == WorkflowNodeType.MERGE:
                predecessors = {edge.source for edge in ins}
                if not predecessors <= completed:
                    # A static predecessor may still run and activate a merge edge.
                    if any(pred not in completed for pred in predecessors):
                        # Only wait if that predecessor is reachable via activated edges.
                        if self._ancestor_may_run(workflow, predecessors - completed, activated, completed):
                            return True
                continue
            if active_ins and not all(edge.source in completed for edge in active_ins):
                return True
        return False

    def _ancestor_may_run(
        self,
        workflow: EditWorkflow,
        pending: set[str],
        activated: set[tuple[str, str, str]],
        completed: set[str],
    ) -> bool:
        """Return True if any pending node is still reachable from the active frontier."""
        for node_id in pending:
            ins = incoming(workflow.edges, node_id)
            if any(
                (edge.source, edge.target, edge.kind.value) in activated
                or edge.source in completed
                for edge in ins
            ):
                return True
        return False

    async def _run_node(
        self,
        owner_key_id: str,
        workflow: EditWorkflow,
        run_id: str,
        node_id: str,
        activated: set[tuple[str, str, str]],
    ) -> EdgeKind | None:
        run = await self._require_run(owner_key_id, run_id)
        assert run.session_id is not None
        node = next(n for n in workflow.nodes if n.id == node_id)
        if node.type == WorkflowNodeType.EDIT:
            await self._run_edit(owner_key_id, workflow, run, node, activated)
            return None
        if node.type == WorkflowNodeType.CONDITION:
            return await self._run_condition(owner_key_id, workflow, run, node, activated)
        if node.type == WorkflowNodeType.MERGE:
            await self._run_merge(owner_key_id, workflow, run, node, activated)
            return None
        if node.type == WorkflowNodeType.OUTPUT:
            await self._run_output(workflow, run, node, activated)
            return None
        raise WorkflowValidationError(f"cannot execute node type {node.type}")

    async def _run_edit(
        self,
        owner_key_id: str,
        workflow: EditWorkflow,
        run: WorkflowRun,
        node: WorkflowNode,
        activated: set[tuple[str, str, str]],
    ) -> None:
        assert node.edit is not None and run.session_id is not None
        parent_version_id = self._primary_parent_version(workflow, run, node.id, activated)
        tree = await self._edits.get_tree(owner_key_id, run.session_id)
        parent_ver = next(v for v in tree.versions if v.id == parent_version_id)

        for entity in match_roles(parent_ver.entities, node.edit.lock_roles):
            if entity.status != EntityStatus.LOCKED:
                await self._edits.update_entity_status(
                    owner_key_id,
                    run.session_id,
                    parent_version_id,
                    entity.id,
                    EntityStatus.LOCKED,
                )

        tree = await self._edits.get_tree(owner_key_id, run.session_id)
        parent_ver = next(v for v in tree.versions if v.id == parent_version_id)
        targets = [e.id for e in match_roles(parent_ver.entities, node.edit.target_roles)]
        missing_locks = [
            role
            for role in node.edit.lock_roles
            if not match_roles(parent_ver.entities, [role])
        ]
        if missing_locks:
            run.warnings.append(
                f"edit node {node.id}: unmatched lock roles {missing_locks}"
            )

        extra_refs = [
            artifact_id
            for artifact_id in parent_ver.reference_artifact_ids
            if artifact_id
        ]
        child = await self._edits.submit_turn(
            owner_key_id,
            run.session_id,
            EditTurnRequest(
                parent_version_id=parent_version_id,
                instruction=node.edit.instruction,
                target_entity_ids=targets,
                prompt_style=node.edit.prompt_style,
                image_provider=node.edit.image_provider,
                image_model=node.edit.image_model,
            ),
            run_in_background=False,
            extra_reference_artifact_ids=extra_refs,
        )
        run.node_version_map[node.id] = child.id
        if child.status == VersionStatus.FAILED:
            run.warnings.append(f"edit node {node.id} failed: {child.error}")
        await self._workflows.save_run(run)

    async def _run_condition(
        self,
        owner_key_id: str,
        workflow: EditWorkflow,
        run: WorkflowRun,
        node: WorkflowNode,
        activated: set[tuple[str, str, str]],
    ) -> EdgeKind | None:
        assert node.condition is not None and run.session_id is not None
        parent_version_id = self._primary_parent_version(workflow, run, node.id, activated)
        version = await self._require_version(owner_key_id, run.session_id, parent_version_id)
        run.node_version_map[node.id] = parent_version_id

        if node.condition.kind == ConditionKind.MANUAL:
            run.status = WorkflowRunStatus.WAITING_MANUAL
            run.waiting_node_id = node.id
            await self._workflows.save_run(run)
            return None

        passed = self._eval_condition(node, version)
        await self._workflows.save_run(run)
        return EdgeKind.PASS if passed else EdgeKind.FAIL

    def _eval_condition(self, node: WorkflowNode, version: EditVersion) -> bool:
        assert node.condition is not None
        kind = node.condition.kind
        if kind == ConditionKind.TARGET_APPLIED:
            if version.verification is None:
                return version.status == VersionStatus.SUCCEEDED
            return bool(version.verification.target_applied)
        if kind == ConditionKind.LOCKED_SCORE:
            if version.verification is None:
                return False
            scores = [item.score for item in version.verification.preserved]
            if not scores:
                return True
            return min(scores) >= node.condition.min_locked_score
        if kind == ConditionKind.ENTITY_ROLE_EXISTS:
            role = node.condition.role or ""
            return bool(match_roles(version.entities, [role]))
        return False

    async def _run_merge(
        self,
        owner_key_id: str,
        workflow: EditWorkflow,
        run: WorkflowRun,
        node: WorkflowNode,
        activated: set[tuple[str, str, str]],
    ) -> None:
        assert node.merge is not None and run.session_id is not None
        ins = [
            edge
            for edge in incoming(workflow.edges, node.id)
            if (edge.source, edge.target, edge.kind.value) in activated
        ]
        input_version_ids = [
            run.node_version_map[edge.source]
            for edge in ins
            if edge.source in run.node_version_map
        ]
        if not input_version_ids:
            raise WorkflowValidationError(f"merge node {node.id} has no inputs")

        tree = await self._edits.get_tree(owner_key_id, run.session_id)
        versions = {v.id: v for v in tree.versions}
        inputs = [versions[vid] for vid in input_version_ids if vid in versions]
        if not inputs:
            raise WorkflowValidationError(f"merge node {node.id} inputs missing")

        if node.merge.mode == MergeMode.SELECT_BEST:
            primary = max(inputs, key=_version_score)
        else:
            primary = inputs[0]

        secondary_artifacts = [
            v.image_artifact_id
            for v in inputs
            if v.id != primary.id and v.image_artifact_id
        ]
        merge_version = await self._edits.create_passthrough_version(
            owner_key_id,
            run.session_id,
            parent_version_id=primary.id,
            input_version_ids=[v.id for v in inputs],
            reference_artifact_ids=[a for a in secondary_artifacts if a],
            instruction=f"[workflow:merge {node.merge.mode.value}]",
        )
        run.node_version_map[node.id] = merge_version.id
        await self._workflows.save_run(run)

    async def _run_output(
        self,
        workflow: EditWorkflow,
        run: WorkflowRun,
        node: WorkflowNode,
        activated: set[tuple[str, str, str]],
    ) -> None:
        parent_version_id = self._primary_parent_version(workflow, run, node.id, activated)
        run.node_version_map[node.id] = parent_version_id
        await self._workflows.save_run(run)

    def _primary_parent_version(
        self,
        workflow: EditWorkflow,
        run: WorkflowRun,
        node_id: str,
        activated: set[tuple[str, str, str]],
    ) -> str:
        ins = [
            edge
            for edge in incoming(workflow.edges, node_id)
            if (edge.source, edge.target, edge.kind.value) in activated
        ]
        if not ins:
            raise WorkflowValidationError(f"node {node_id} has no activated parent")
        source = ins[0].source
        version_id = run.node_version_map.get(source)
        if not version_id:
            raise WorkflowValidationError(f"parent node {source} has no version")
        return version_id

    async def _require_run(self, owner_key_id: str, run_id: str) -> WorkflowRun:
        run = await self._workflows.get_run(run_id, owner_key_id)
        if run is None:
            raise WorkflowValidationError(f"run not found: {run_id}")
        return run

    async def _require_version(
        self, owner_key_id: str, session_id: str, version_id: str
    ) -> EditVersion:
        tree = await self._edits.get_tree(owner_key_id, session_id)
        version = next((v for v in tree.versions if v.id == version_id), None)
        if version is None:
            raise WorkflowValidationError(f"version not found: {version_id}")
        return version


def _version_score(version: EditVersion) -> float:
    if version.verification is None:
        return 0.0 if version.status != VersionStatus.SUCCEEDED else 0.5
    score = 1.0 if version.verification.target_applied else 0.0
    if version.verification.composition_score is not None:
        score += version.verification.composition_score
    if version.verification.preserved:
        score += sum(p.score for p in version.verification.preserved) / len(
            version.verification.preserved
        )
    return score
