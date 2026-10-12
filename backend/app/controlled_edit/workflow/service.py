"""CRUD facade for edit workflow templates."""

from __future__ import annotations

from app.controlled_edit.workflow.graph import validate_workflow
from app.controlled_edit.workflow.repository import WorkflowRepository, get_workflow_repository
from app.controlled_edit.workflow.schemas import (
    EditWorkflow,
    WorkflowCreateRequest,
    WorkflowUpdateRequest,
    WorkflowValidationError,
    utc_now,
)


class WorkflowService:
    """Own-scoped workflow template operations."""

    def __init__(self, repository: WorkflowRepository | None = None) -> None:
        self._repository = repository or get_workflow_repository()

    async def create(self, owner_key_id: str, body: WorkflowCreateRequest) -> EditWorkflow:
        """Validate and persist a new workflow."""
        workflow = EditWorkflow(
            owner_key_id=owner_key_id,
            title=body.title[:120] or "Untitled workflow",
            nodes=body.nodes,
            edges=body.edges,
            source_session_id=body.source_session_id,
        )
        validate_workflow(workflow)
        return await self._repository.create(workflow)

    async def get(self, owner_key_id: str, workflow_id: str) -> EditWorkflow:
        """Return an owned workflow or raise."""
        found = await self._repository.get(workflow_id, owner_key_id)
        if found is None:
            raise WorkflowValidationError(f"workflow not found: {workflow_id}")
        return found

    async def list(self, owner_key_id: str) -> list[EditWorkflow]:
        """List owned workflows."""
        return await self._repository.list(owner_key_id)

    async def update(
        self, owner_key_id: str, workflow_id: str, body: WorkflowUpdateRequest
    ) -> EditWorkflow:
        """Patch title and/or graph."""
        workflow = await self.get(owner_key_id, workflow_id)
        if body.title is not None:
            workflow.title = body.title[:120] or workflow.title
        if body.nodes is not None:
            workflow.nodes = body.nodes
        if body.edges is not None:
            workflow.edges = body.edges
        workflow.updated_at = utc_now()
        validate_workflow(workflow)
        return await self._repository.save(workflow)

    async def delete(self, owner_key_id: str, workflow_id: str) -> None:
        """Delete an owned workflow."""
        deleted = await self._repository.delete(workflow_id, owner_key_id)
        if not deleted:
            raise WorkflowValidationError(f"workflow not found: {workflow_id}")


_service: WorkflowService | None = None


def get_workflow_service() -> WorkflowService:
    """Process-wide workflow CRUD service."""
    global _service
    if _service is None:
        _service = WorkflowService()
    return _service
