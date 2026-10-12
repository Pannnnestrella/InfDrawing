"""Persistence for edit workflow templates and runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import settings
from app.controlled_edit.workflow.schemas import EditWorkflow, WorkflowRun, utc_now
from app.production.models import EditWorkflowRow


class WorkflowRepository(Protocol):
    """Repository contract for workflow templates and runs."""

    async def create(self, workflow: EditWorkflow) -> EditWorkflow: ...

    async def get(self, workflow_id: str, owner_key_id: str) -> EditWorkflow | None: ...

    async def list(self, owner_key_id: str) -> list[EditWorkflow]: ...

    async def save(self, workflow: EditWorkflow) -> EditWorkflow: ...

    async def delete(self, workflow_id: str, owner_key_id: str) -> bool: ...

    async def create_run(self, run: WorkflowRun) -> WorkflowRun: ...

    async def get_run(self, run_id: str, owner_key_id: str) -> WorkflowRun | None: ...

    async def save_run(self, run: WorkflowRun) -> WorkflowRun: ...

    async def list_runs(self, owner_key_id: str, workflow_id: str | None = None) -> list[WorkflowRun]: ...


class MemoryWorkflowRepository:
    """In-memory workflow store for tests and local JSON backend."""

    def __init__(self) -> None:
        self._workflows: dict[str, EditWorkflow] = {}
        self._runs: dict[str, WorkflowRun] = {}
        self._lock = asyncio.Lock()

    async def create(self, workflow: EditWorkflow) -> EditWorkflow:
        """Insert a new workflow template."""
        async with self._lock:
            if workflow.id in self._workflows:
                raise ValueError(f"workflow already exists: {workflow.id}")
            self._workflows[workflow.id] = workflow.model_copy(deep=True)
        return workflow

    async def get(self, workflow_id: str, owner_key_id: str) -> EditWorkflow | None:
        """Return an owned workflow."""
        found = self._workflows.get(workflow_id)
        if found is None or found.owner_key_id != owner_key_id:
            return None
        return found.model_copy(deep=True)

    async def list(self, owner_key_id: str) -> list[EditWorkflow]:
        """Return owned workflows, newest first."""
        owned = [w for w in self._workflows.values() if w.owner_key_id == owner_key_id]
        owned.sort(key=lambda w: w.updated_at, reverse=True)
        return [w.model_copy(deep=True) for w in owned]

    async def save(self, workflow: EditWorkflow) -> EditWorkflow:
        """Overwrite an existing workflow."""
        async with self._lock:
            if workflow.id not in self._workflows:
                raise KeyError(f"workflow not found: {workflow.id}")
            workflow.updated_at = utc_now()
            self._workflows[workflow.id] = workflow.model_copy(deep=True)
        return workflow

    async def delete(self, workflow_id: str, owner_key_id: str) -> bool:
        """Delete an owned workflow; return whether it existed."""
        async with self._lock:
            found = self._workflows.get(workflow_id)
            if found is None or found.owner_key_id != owner_key_id:
                return False
            del self._workflows[workflow_id]
            return True

    async def create_run(self, run: WorkflowRun) -> WorkflowRun:
        """Insert a new workflow run."""
        async with self._lock:
            if run.id in self._runs:
                raise ValueError(f"run already exists: {run.id}")
            self._runs[run.id] = run.model_copy(deep=True)
        return run

    async def get_run(self, run_id: str, owner_key_id: str) -> WorkflowRun | None:
        """Return an owned run."""
        found = self._runs.get(run_id)
        if found is None or found.owner_key_id != owner_key_id:
            return None
        return found.model_copy(deep=True)

    async def save_run(self, run: WorkflowRun) -> WorkflowRun:
        """Overwrite an existing run."""
        async with self._lock:
            if run.id not in self._runs:
                raise KeyError(f"run not found: {run.id}")
            run.updated_at = utc_now()
            self._runs[run.id] = run.model_copy(deep=True)
        return run

    async def list_runs(
        self, owner_key_id: str, workflow_id: str | None = None
    ) -> list[WorkflowRun]:
        """Return owned runs, optionally filtered by workflow."""
        runs = [r for r in self._runs.values() if r.owner_key_id == owner_key_id]
        if workflow_id is not None:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        runs.sort(key=lambda r: r.updated_at, reverse=True)
        return [r.model_copy(deep=True) for r in runs]


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class JsonWorkflowRepository(MemoryWorkflowRepository):
    """Memory repository persisted to a JSON file."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._workflows = {
            key: EditWorkflow.model_validate(value)
            for key, value in (raw.get("workflows") or {}).items()
        }
        self._runs = {
            key: WorkflowRun.model_validate(value)
            for key, value in (raw.get("runs") or {}).items()
        }

    def _persist(self) -> None:
        _atomic_write_json(
            self._path,
            {
                "workflows": {
                    key: workflow.model_dump(mode="json")
                    for key, workflow in self._workflows.items()
                },
                "runs": {
                    key: run.model_dump(mode="json") for key, run in self._runs.items()
                },
            },
        )

    async def create(self, workflow: EditWorkflow) -> EditWorkflow:
        result = await super().create(workflow)
        self._persist()
        return result

    async def save(self, workflow: EditWorkflow) -> EditWorkflow:
        result = await super().save(workflow)
        self._persist()
        return result

    async def delete(self, workflow_id: str, owner_key_id: str) -> bool:
        result = await super().delete(workflow_id, owner_key_id)
        if result:
            self._persist()
        return result

    async def create_run(self, run: WorkflowRun) -> WorkflowRun:
        result = await super().create_run(run)
        self._persist()
        return result

    async def save_run(self, run: WorkflowRun) -> WorkflowRun:
        result = await super().save_run(run)
        self._persist()
        return result


class SqlWorkflowRepository:
    """PostgreSQL repository storing serialized workflows in JSON columns."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._runs = MemoryWorkflowRepository()

    async def create(self, workflow: EditWorkflow) -> EditWorkflow:
        async with self.sessions.begin() as db:
            db.add(
                EditWorkflowRow(
                    id=workflow.id,
                    owner_key_id=workflow.owner_key_id,
                    data=workflow.model_dump(mode="json"),
                )
            )
        return workflow

    async def get(self, workflow_id: str, owner_key_id: str) -> EditWorkflow | None:
        async with self.sessions() as db:
            row = await db.scalar(
                select(EditWorkflowRow).where(
                    EditWorkflowRow.id == workflow_id,
                    EditWorkflowRow.owner_key_id == owner_key_id,
                )
            )
        return EditWorkflow.model_validate(row.data) if row else None

    async def list(self, owner_key_id: str) -> list[EditWorkflow]:
        async with self.sessions() as db:
            rows = await db.scalars(
                select(EditWorkflowRow)
                .where(EditWorkflowRow.owner_key_id == owner_key_id)
                .order_by(EditWorkflowRow.updated_at.desc())
            )
            return [EditWorkflow.model_validate(row.data) for row in rows]

    async def save(self, workflow: EditWorkflow) -> EditWorkflow:
        workflow.updated_at = utc_now()
        async with self.sessions.begin() as db:
            row = await db.get(EditWorkflowRow, workflow.id)
            if row is None:
                raise KeyError(f"workflow not found: {workflow.id}")
            row.data = workflow.model_dump(mode="json")
        return workflow

    async def delete(self, workflow_id: str, owner_key_id: str) -> bool:
        async with self.sessions.begin() as db:
            row = await db.scalar(
                select(EditWorkflowRow).where(
                    EditWorkflowRow.id == workflow_id,
                    EditWorkflowRow.owner_key_id == owner_key_id,
                )
            )
            if row is None:
                return False
            await db.delete(row)
            return True

    async def create_run(self, run: WorkflowRun) -> WorkflowRun:
        return await self._runs.create_run(run)

    async def get_run(self, run_id: str, owner_key_id: str) -> WorkflowRun | None:
        return await self._runs.get_run(run_id, owner_key_id)

    async def save_run(self, run: WorkflowRun) -> WorkflowRun:
        return await self._runs.save_run(run)

    async def list_runs(
        self, owner_key_id: str, workflow_id: str | None = None
    ) -> list[WorkflowRun]:
        return await self._runs.list_runs(owner_key_id, workflow_id)


_repository: WorkflowRepository | None = None


def get_workflow_repository() -> WorkflowRepository:
    """Return the configured workflow repository."""
    global _repository
    if _repository is not None:
        return _repository
    if settings.persistence_backend == "memory":
        _repository = JsonWorkflowRepository(settings.data_dir / "cedit" / "workflows.json")
    elif settings.persistence_backend == "postgres":
        from app.production.models import create_engine

        _repository = SqlWorkflowRepository(create_engine())
    else:
        raise RuntimeError(f"unsupported persistence backend: {settings.persistence_backend}")
    return _repository
