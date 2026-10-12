"""Tests for edit workflow graph validation, export, repository, and runner."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
import pytest
from pydantic import ValidationError

from app.controlled_edit.repository import MemoryEditRepository
from app.controlled_edit.schemas import (
    EditIntent,
    EditOperation,
    EditSession,
    EditTurnRequest,
    EditVersion,
    EntityStatus,
    SceneEntity,
    SessionTree,
    VerificationResult,
    VersionStatus,
)
from app.controlled_edit.service import ControlledEditService
from app.controlled_edit.workflow.export import export_subgraph_to_workflow
from app.controlled_edit.workflow.graph import validate_workflow
from app.controlled_edit.workflow.repository import MemoryWorkflowRepository
from app.controlled_edit.workflow.roles import locked_roles, match_roles
from app.controlled_edit.workflow.runner import WorkflowRunner
from app.controlled_edit.workflow.schemas import (
    ConditionKind,
    ConditionNodeConfig,
    EditNodeConfig,
    EditWorkflow,
    EdgeKind,
    MergeMode,
    MergeNodeConfig,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowRunStatus,
    WorkflowValidationError,
)


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _entity(entity_id: str, status: EntityStatus = EntityStatus.EDITABLE) -> SceneEntity:
    return SceneEntity(id=entity_id, name=entity_id.split(".")[-1], status=status)


def _linear_workflow(owner: str = "owner") -> EditWorkflow:
    inp = WorkflowNode(id="in", type=WorkflowNodeType.INPUT, label="in")
    edit = WorkflowNode(
        id="e1",
        type=WorkflowNodeType.EDIT,
        label="hat",
        edit=EditNodeConfig(instruction="add a hat", lock_roles=["face"]),
    )
    out = WorkflowNode(id="out", type=WorkflowNodeType.OUTPUT, label="out")
    return EditWorkflow(
        owner_key_id=owner,
        title="linear",
        nodes=[inp, edit, out],
        edges=[
            WorkflowEdge(id="a", source="in", target="e1"),
            WorkflowEdge(id="b", source="e1", target="out"),
        ],
    )


def test_validate_rejects_cycle_and_missing_input() -> None:
    wf = _linear_workflow()
    validate_workflow(wf)
    wf.edges.append(WorkflowEdge(id="loop", source="out", target="e1"))
    with pytest.raises(WorkflowValidationError, match="cycle"):
        validate_workflow(wf)

    broken = EditWorkflow(
        owner_key_id="o",
        nodes=[WorkflowNode(id="out", type=WorkflowNodeType.OUTPUT)],
        edges=[],
    )
    with pytest.raises(WorkflowValidationError, match="exactly one input"):
        validate_workflow(broken)


def test_condition_edges_must_be_pass_or_fail() -> None:
    nodes = [
        WorkflowNode(id="in", type=WorkflowNodeType.INPUT),
        WorkflowNode(
            id="c",
            type=WorkflowNodeType.CONDITION,
            condition=ConditionNodeConfig(kind=ConditionKind.TARGET_APPLIED),
        ),
        WorkflowNode(id="out", type=WorkflowNodeType.OUTPUT),
    ]
    edges = [
        WorkflowEdge(id="a", source="in", target="c"),
        WorkflowEdge(id="b", source="c", target="out", kind=EdgeKind.DEFAULT),
    ]
    with pytest.raises(WorkflowValidationError, match="pass or fail"):
        validate_workflow(EditWorkflow(owner_key_id="o", nodes=nodes, edges=edges))


def test_role_matching_and_locked_roles() -> None:
    entities = [
        _entity("character.face", EntityStatus.LOCKED),
        _entity("character.sword", EntityStatus.EDITABLE),
        _entity("environment.sky"),
    ]
    assert [e.id for e in match_roles(entities, ["face", "sword"])] == [
        "character.face",
        "character.sword",
    ]
    assert locked_roles(entities) == ["face"]


def test_export_branched_subgraph() -> None:
    session = EditSession(owner_key_id="owner", title="knight")
    root = EditVersion(
        session_id=session.id,
        status=VersionStatus.SUCCEEDED,
        image_artifact_id="img0",
        entities=[_entity("character.face", EntityStatus.LOCKED)],
    )
    session.root_version_id = root.id
    a = EditVersion(
        session_id=session.id,
        parent_id=root.id,
        status=VersionStatus.SUCCEEDED,
        image_artifact_id="img1",
        instruction="swap the sword",
        intent=EditIntent(
            operation=EditOperation.REPLACE,
            target_entity_ids=["character.sword"],
            change_description="swap sword",
        ),
        entities=[_entity("character.face", EntityStatus.LOCKED), _entity("character.sword")],
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    b = EditVersion(
        session_id=session.id,
        parent_id=root.id,
        status=VersionStatus.SUCCEEDED,
        image_artifact_id="img2",
        instruction="change the hat",
        intent=EditIntent(
            operation=EditOperation.RESTYLE,
            target_entity_ids=["character.hat"],
            change_description="hat",
        ),
        entities=[_entity("character.face", EntityStatus.LOCKED)],
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
    )
    tree = SessionTree(session=session, versions=[root, a, b])
    workflow = export_subgraph_to_workflow(
        tree, [root.id, a.id, b.id], owner_key_id="owner", title="two-branch"
    )
    validate_workflow(workflow)
    edits = [n for n in workflow.nodes if n.type == WorkflowNodeType.EDIT]
    assert len(edits) == 2
    assert {e.edit.instruction for e in edits if e.edit} == {
        "swap the sword",
        "change the hat",
    }
    assert all(e.edit and "face" in e.edit.lock_roles for e in edits)
    assert len([n for n in workflow.nodes if n.type == WorkflowNodeType.OUTPUT]) == 2


def test_workflow_repository_owner_scoped() -> None:
    async def scenario() -> None:
        repo = MemoryWorkflowRepository()
        wf = _linear_workflow("owner")
        await repo.create(wf)
        assert await repo.get(wf.id, "intruder") is None
        assert len(await repo.list("owner")) == 1
        assert await repo.delete(wf.id, "owner") is True

    _run(scenario())


def test_edit_node_requires_config() -> None:
    with pytest.raises(ValidationError):
        WorkflowNode(id="x", type=WorkflowNodeType.EDIT)


class _FakeArtifacts:
    async def create_image(self, owner: str, data: bytes, media_type: str) -> Any:
        class A:
            id = "art-" + str(len(data))

        return A()

    async def read_owned(self, artifact_id: str, owner: str) -> tuple[str, bytes] | None:
        return ("image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def _png() -> bytes:
    # Minimal valid-ish bytes; create_session is mocked in runner tests.
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def test_runner_linear_branch_condition_merge() -> None:
    async def scenario() -> None:
        edit_repo = MemoryEditRepository()
        wf_repo = MemoryWorkflowRepository()

        async def fake_create_session(
            owner_key_id: str, image_bytes: bytes, media_type: str, title: str = "Untitled"
        ) -> SessionTree:
            session = EditSession(owner_key_id=owner_key_id, title=title)
            root = EditVersion(
                session_id=session.id,
                status=VersionStatus.SUCCEEDED,
                image_artifact_id="root-img",
                entities=[
                    _entity("character.face", EntityStatus.EDITABLE),
                    _entity("character.sword"),
                ],
            )
            session.root_version_id = root.id
            session.current_version_id = root.id
            await edit_repo.create_session(session)
            await edit_repo.add_version(root)
            return SessionTree(session=session, versions=[root])

        service = ControlledEditService(
            repository=edit_repo,
            artifacts=_FakeArtifacts(),  # type: ignore[arg-type]
            vision_factory=lambda: None,  # type: ignore[arg-type,return-value]
            editor_factory=lambda _provider, _model=None: None,  # type: ignore[arg-type,return-value]
        )
        service.create_session = fake_create_session  # type: ignore[method-assign]

        async def fake_submit(
            owner_key_id: str,
            session_id: str,
            request: EditTurnRequest,
            *,
            run_in_background: bool = True,
            extra_reference_artifact_ids: list[str] | None = None,
        ) -> EditVersion:
            parent = await edit_repo.get_version(session_id, request.parent_version_id)
            assert parent is not None
            child = EditVersion(
                session_id=session_id,
                parent_id=parent.id,
                status=VersionStatus.SUCCEEDED,
                image_artifact_id=f"img-{request.instruction[:8]}",
                instruction=request.instruction,
                intent=EditIntent(
                    operation=EditOperation.OTHER,
                    target_entity_ids=request.target_entity_ids,
                    change_description=request.instruction,
                ),
                entities=[e.model_copy() for e in parent.entities],
                reference_artifact_ids=list(extra_reference_artifact_ids or []),
                verification=VerificationResult(
                    target_applied=True,
                    passed=True,
                    preserved=[],
                ),
            )
            await edit_repo.add_version(child)
            return child

        service.submit_turn = fake_submit  # type: ignore[method-assign]

        # Build: input -> e1 -> cond -> merge <- e2 ; merge -> out
        # Also input -> e2
        nodes = [
            WorkflowNode(id="in", type=WorkflowNodeType.INPUT),
            WorkflowNode(
                id="e1",
                type=WorkflowNodeType.EDIT,
                edit=EditNodeConfig(instruction="branch A", lock_roles=["face"]),
            ),
            WorkflowNode(
                id="e2",
                type=WorkflowNodeType.EDIT,
                edit=EditNodeConfig(instruction="branch B"),
            ),
            WorkflowNode(
                id="cond",
                type=WorkflowNodeType.CONDITION,
                condition=ConditionNodeConfig(kind=ConditionKind.TARGET_APPLIED),
            ),
            WorkflowNode(
                id="merge",
                type=WorkflowNodeType.MERGE,
                merge=MergeNodeConfig(mode=MergeMode.MULTI_REF),
            ),
            WorkflowNode(id="out", type=WorkflowNodeType.OUTPUT),
        ]
        edges = [
            WorkflowEdge(id="1", source="in", target="e1"),
            WorkflowEdge(id="2", source="in", target="e2"),
            WorkflowEdge(id="3", source="e1", target="cond"),
            WorkflowEdge(id="4", source="cond", target="merge", kind=EdgeKind.PASS),
            WorkflowEdge(id="5", source="e2", target="merge"),
            WorkflowEdge(id="6", source="merge", target="out"),
        ]
        workflow = EditWorkflow(
            owner_key_id="owner", title="fan", nodes=nodes, edges=edges
        )
        validate_workflow(workflow)
        await wf_repo.create(workflow)

        runner = WorkflowRunner(edit_service=service, workflow_repository=wf_repo)
        run = await runner.start_run("owner", workflow.id, _png(), "image/png")
        for _ in range(50):
            latest = await wf_repo.get_run(run.id, "owner")
            assert latest is not None
            if latest.status in (WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED):
                run = latest
                break
            await asyncio.sleep(0.02)
        assert run.status == WorkflowRunStatus.SUCCEEDED
        assert run.session_id is not None
        tree = await service.get_tree("owner", run.session_id)
        # root + 2 edits + 1 merge (+ condition shares parent version, no new node)
        assert len(tree.versions) >= 4
        merge_nodes = [v for v in tree.versions if v.instruction and "merge" in v.instruction]
        assert len(merge_nodes) == 1
        assert len(merge_nodes[0].input_version_ids) == 2

    _run(scenario())


def test_condition_fail_path() -> None:
    async def scenario() -> None:
        edit_repo = MemoryEditRepository()
        wf_repo = MemoryWorkflowRepository()

        async def fake_create_session(
            owner_key_id: str, image_bytes: bytes, media_type: str, title: str = "Untitled"
        ) -> SessionTree:
            session = EditSession(owner_key_id=owner_key_id, title=title)
            root = EditVersion(
                session_id=session.id,
                status=VersionStatus.SUCCEEDED,
                image_artifact_id="root-img",
                entities=[_entity("character.face")],
            )
            session.root_version_id = root.id
            session.current_version_id = root.id
            await edit_repo.create_session(session)
            await edit_repo.add_version(root)
            return SessionTree(session=session, versions=[root])

        service = ControlledEditService(
            repository=edit_repo,
            artifacts=_FakeArtifacts(),  # type: ignore[arg-type]
            vision_factory=lambda: None,  # type: ignore[arg-type,return-value]
            editor_factory=lambda _provider, _model=None: None,  # type: ignore[arg-type,return-value]
        )
        service.create_session = fake_create_session  # type: ignore[method-assign]

        async def fake_submit(
            owner_key_id: str,
            session_id: str,
            request: EditTurnRequest,
            *,
            run_in_background: bool = True,
            extra_reference_artifact_ids: list[str] | None = None,
        ) -> EditVersion:
            parent = await edit_repo.get_version(session_id, request.parent_version_id)
            assert parent is not None
            applied = "good" in request.instruction
            child = EditVersion(
                session_id=session_id,
                parent_id=parent.id,
                status=VersionStatus.SUCCEEDED,
                image_artifact_id="img",
                instruction=request.instruction,
                intent=EditIntent(
                    operation=EditOperation.OTHER,
                    change_description=request.instruction,
                ),
                entities=[e.model_copy() for e in parent.entities],
                verification=VerificationResult(
                    target_applied=applied,
                    passed=applied,
                    preserved=[],
                ),
            )
            await edit_repo.add_version(child)
            return child

        service.submit_turn = fake_submit  # type: ignore[method-assign]

        nodes = [
            WorkflowNode(id="in", type=WorkflowNodeType.INPUT),
            WorkflowNode(
                id="e1",
                type=WorkflowNodeType.EDIT,
                edit=EditNodeConfig(instruction="bad edit"),
            ),
            WorkflowNode(
                id="cond",
                type=WorkflowNodeType.CONDITION,
                condition=ConditionNodeConfig(kind=ConditionKind.TARGET_APPLIED),
            ),
            WorkflowNode(
                id="ok",
                type=WorkflowNodeType.EDIT,
                edit=EditNodeConfig(instruction="good recovery"),
            ),
            WorkflowNode(id="out_pass", type=WorkflowNodeType.OUTPUT, label="pass"),
            WorkflowNode(id="out_fail", type=WorkflowNodeType.OUTPUT, label="fail"),
        ]
        # fail path: cond -fail-> out_fail ; pass path: cond -pass-> ok -> out_pass
        edges = [
            WorkflowEdge(id="1", source="in", target="e1"),
            WorkflowEdge(id="2", source="e1", target="cond"),
            WorkflowEdge(id="3", source="cond", target="ok", kind=EdgeKind.PASS),
            WorkflowEdge(id="4", source="cond", target="out_fail", kind=EdgeKind.FAIL),
            WorkflowEdge(id="5", source="ok", target="out_pass"),
        ]
        # out_pass unreachable when fail — validation requires all outputs reachable.
        # Use single output on fail path only for this test by making both reachable
        # from input via pass/fail (both reachable in graph sense).
        workflow = EditWorkflow(
            owner_key_id="owner", title="cond", nodes=nodes, edges=edges
        )
        # Both outputs are reachable ignoring edge kind — validate_workflow uses
        # undirected? No, directed from input. pass and fail both leave cond so both
        # out_fail and ok/out_pass are reachable. Good.
        validate_workflow(workflow)
        await wf_repo.create(workflow)

        runner = WorkflowRunner(edit_service=service, workflow_repository=wf_repo)
        run = await runner.start_run("owner", workflow.id, _png(), "image/png")
        for _ in range(50):
            latest = await wf_repo.get_run(run.id, "owner")
            assert latest is not None
            if latest.status in (WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED):
                run = latest
                break
            await asyncio.sleep(0.02)
        assert run.status == WorkflowRunStatus.SUCCEEDED
        assert "out_fail" in run.node_version_map
        assert "ok" not in run.node_version_map

    _run(scenario())
