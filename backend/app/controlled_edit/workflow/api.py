"""HTTP API for controlled-edit workflow templates and runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.config import settings
from app.controlled_edit.service import (
    ControlledEditService,
    SessionNotFoundError,
    get_controlled_edit_service,
)
from app.controlled_edit.workflow.export import export_subgraph_to_workflow
from app.controlled_edit.workflow.repository import get_workflow_repository
from app.controlled_edit.workflow.runner import WorkflowRunner
from app.controlled_edit.workflow.schemas import (
    EditWorkflow,
    ExportWorkflowRequest,
    ManualResumeRequest,
    WorkflowCreateRequest,
    WorkflowRun,
    WorkflowUpdateRequest,
    WorkflowValidationError,
)
from app.controlled_edit.workflow.service import WorkflowService, get_workflow_service
from app.production.auth import ApiPrincipal, current_principal
from app.production.telemetry import record_audit

router = APIRouter(prefix="/controlled-edit", tags=["controlled-edit-workflows"])


def require_openai_configured() -> None:
    if not settings.openai_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key is not configured (controlled edit requires OpenAI)",
        )


def _workflows() -> WorkflowService:
    return get_workflow_service()


def _edits() -> ControlledEditService:
    return get_controlled_edit_service()


def _runner() -> WorkflowRunner:
    return WorkflowRunner(
        edit_service=get_controlled_edit_service(),
        workflow_repository=get_workflow_repository(),
    )


def _http(exc: WorkflowValidationError) -> HTTPException:
    message = str(exc)
    code = 404 if "not found" in message.lower() else 422
    return HTTPException(status_code=code, detail=message)


@router.post(
    "/workflows",
    response_model=EditWorkflow,
    status_code=201,
    dependencies=[Depends(require_openai_configured)],
)
async def create_workflow(
    body: WorkflowCreateRequest,
    principal: ApiPrincipal = Depends(current_principal),
    service: WorkflowService = Depends(_workflows),
) -> EditWorkflow:
    """Create a reusable edit workflow DAG."""
    try:
        workflow = await service.create(principal.key_id, body)
    except WorkflowValidationError as exc:
        raise _http(exc) from exc
    await record_audit(
        principal.key_id,
        "controlled_edit.create_workflow",
        "edit_workflow",
        workflow.id,
    )
    return workflow


@router.get("/workflows", response_model=list[EditWorkflow])
async def list_workflows(
    principal: ApiPrincipal = Depends(current_principal),
    service: WorkflowService = Depends(_workflows),
) -> list[EditWorkflow]:
    """List the caller's workflow templates."""
    return await service.list(principal.key_id)


@router.get("/workflows/{workflow_id}", response_model=EditWorkflow)
async def get_workflow(
    workflow_id: str,
    principal: ApiPrincipal = Depends(current_principal),
    service: WorkflowService = Depends(_workflows),
) -> EditWorkflow:
    """Return one owned workflow."""
    try:
        return await service.get(principal.key_id, workflow_id)
    except WorkflowValidationError as exc:
        raise _http(exc) from exc


@router.put("/workflows/{workflow_id}", response_model=EditWorkflow)
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdateRequest,
    principal: ApiPrincipal = Depends(current_principal),
    service: WorkflowService = Depends(_workflows),
) -> EditWorkflow:
    """Replace title and/or graph of a workflow."""
    try:
        return await service.update(principal.key_id, workflow_id, body)
    except WorkflowValidationError as exc:
        raise _http(exc) from exc


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    principal: ApiPrincipal = Depends(current_principal),
    service: WorkflowService = Depends(_workflows),
) -> None:
    """Delete an owned workflow template."""
    try:
        await service.delete(principal.key_id, workflow_id)
    except WorkflowValidationError as exc:
        raise _http(exc) from exc


@router.post(
    "/sessions/{session_id}/export-workflow",
    response_model=EditWorkflow,
    status_code=201,
)
async def export_workflow(
    session_id: str,
    body: ExportWorkflowRequest,
    principal: ApiPrincipal = Depends(current_principal),
    edits: ControlledEditService = Depends(_edits),
    workflows: WorkflowService = Depends(_workflows),
) -> EditWorkflow:
    """Export a connected version subgraph into a saved workflow template."""
    try:
        tree = await edits.get_tree(principal.key_id, session_id)
        draft = export_subgraph_to_workflow(
            tree,
            body.version_ids,
            owner_key_id=principal.key_id,
            title=body.title,
        )
        saved = await workflows.create(
            principal.key_id,
            WorkflowCreateRequest(
                title=draft.title,
                nodes=draft.nodes,
                edges=draft.edges,
                source_session_id=draft.source_session_id,
            ),
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkflowValidationError as exc:
        raise _http(exc) from exc
    await record_audit(
        principal.key_id,
        "controlled_edit.export_workflow",
        "edit_workflow",
        saved.id,
        details={"session_id": session_id},
    )
    return saved


@router.post(
    "/workflows/{workflow_id}/runs",
    response_model=WorkflowRun,
    status_code=202,
    dependencies=[Depends(require_openai_configured)],
)
async def start_workflow_run(
    workflow_id: str,
    image: UploadFile = File(...),
    title: str = Form(""),
    principal: ApiPrincipal = Depends(current_principal),
    runner: WorkflowRunner = Depends(_runner),
) -> WorkflowRun:
    """Upload a new image and execute the workflow into a fresh edit session."""
    data = await image.read()
    try:
        run = await runner.start_run(
            principal.key_id,
            workflow_id,
            data,
            image.content_type or "image/png",
            title=title or None,
        )
    except WorkflowValidationError as exc:
        raise _http(exc) from exc
    await record_audit(
        principal.key_id,
        "controlled_edit.start_workflow_run",
        "edit_workflow_run",
        run.id,
        details={"workflow_id": workflow_id, "session_id": run.session_id},
    )
    return run


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRun)
async def get_workflow_run(
    run_id: str,
    principal: ApiPrincipal = Depends(current_principal),
) -> WorkflowRun:
    """Return one workflow run."""
    run = await get_workflow_repository().get_run(run_id, principal.key_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return run


@router.get("/workflows/{workflow_id}/runs", response_model=list[WorkflowRun])
async def list_workflow_runs(
    workflow_id: str,
    principal: ApiPrincipal = Depends(current_principal),
) -> list[WorkflowRun]:
    """List runs for one workflow."""
    return await get_workflow_repository().list_runs(principal.key_id, workflow_id)


@router.post(
    "/workflow-runs/{run_id}/resume",
    response_model=WorkflowRun,
)
async def resume_workflow_run(
    run_id: str,
    body: ManualResumeRequest,
    principal: ApiPrincipal = Depends(current_principal),
    runner: WorkflowRunner = Depends(_runner),
) -> WorkflowRun:
    """Resume a run paused on a manual condition node."""
    try:
        return await runner.resume_manual(principal.key_id, run_id, passed=body.passed)
    except WorkflowValidationError as exc:
        raise _http(exc) from exc
