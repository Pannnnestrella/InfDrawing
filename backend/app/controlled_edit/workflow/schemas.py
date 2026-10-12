"""Domain models for reusable controlled-edit workflow graphs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def new_id() -> str:
    """Return a random identifier."""
    return str(uuid4())


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class WorkflowNodeType(str, Enum):
    """Kinds of nodes in a workflow template."""

    INPUT = "input"
    EDIT = "edit"
    CONDITION = "condition"
    MERGE = "merge"
    OUTPUT = "output"


class EditNodeConfig(BaseModel):
    """Parameters for one edit step when replaying on a new image."""

    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1, max_length=2_000)
    lock_roles: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    prompt_style: Literal["preserve", "target_only"] | None = None
    image_provider: Literal["dashscope", "openai"] | None = None
    image_model: str | None = Field(default=None, max_length=120)


class ConditionKind(str, Enum):
    """How a condition node decides pass vs fail."""

    TARGET_APPLIED = "target_applied"
    LOCKED_SCORE = "locked_score"
    ENTITY_ROLE_EXISTS = "entity_role_exists"
    MANUAL = "manual"


class ConditionNodeConfig(BaseModel):
    """Gate evaluated against the predecessor version (or user resume)."""

    model_config = ConfigDict(extra="forbid")

    kind: ConditionKind = ConditionKind.TARGET_APPLIED
    min_locked_score: float = Field(default=0.7, ge=0.0, le=1.0)
    role: str | None = Field(default=None, max_length=80)


class MergeMode(str, Enum):
    """How multiple predecessor images are combined."""

    MULTI_REF = "multi_ref"
    SELECT_BEST = "select_best"


class MergeNodeConfig(BaseModel):
    """Join configuration for fan-in nodes."""

    model_config = ConfigDict(extra="forbid")

    mode: MergeMode = MergeMode.MULTI_REF


class NodePosition(BaseModel):
    """Canvas coordinates for the workflow editor."""

    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0


class WorkflowNode(BaseModel):
    """One node in a workflow template DAG."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    type: WorkflowNodeType
    label: str = Field(default="", max_length=120)
    position: NodePosition = Field(default_factory=NodePosition)
    edit: EditNodeConfig | None = None
    condition: ConditionNodeConfig | None = None
    merge: MergeNodeConfig | None = None

    @model_validator(mode="after")
    def config_matches_type(self) -> WorkflowNode:
        """Require type-specific config blocks and clear unused ones."""
        if self.type == WorkflowNodeType.EDIT:
            if self.edit is None:
                raise ValueError("edit nodes require edit config")
        elif self.edit is not None:
            raise ValueError(f"{self.type.value} nodes must not include edit config")
        if self.type == WorkflowNodeType.CONDITION:
            if self.condition is None:
                self.condition = ConditionNodeConfig()
        elif self.condition is not None:
            raise ValueError(f"{self.type.value} nodes must not include condition config")
        if self.type == WorkflowNodeType.MERGE:
            if self.merge is None:
                self.merge = MergeNodeConfig()
        elif self.merge is not None:
            raise ValueError(f"{self.type.value} nodes must not include merge config")
        return self


class EdgeKind(str, Enum):
    """Edge semantics; condition nodes use pass/fail."""

    DEFAULT = "default"
    PASS = "pass"
    FAIL = "fail"


class WorkflowEdge(BaseModel):
    """Directed edge between workflow nodes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    kind: EdgeKind = EdgeKind.DEFAULT


class EditWorkflow(BaseModel):
    """Reusable controlled-edit workflow template."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    owner_key_id: str
    title: str = Field(default="Untitled workflow", max_length=120)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    source_session_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowCreateRequest(BaseModel):
    """Body for creating or replacing a workflow graph."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="Untitled workflow", max_length=120)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    source_session_id: str | None = None


class WorkflowUpdateRequest(BaseModel):
    """Partial update for an existing workflow."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)
    nodes: list[WorkflowNode] | None = None
    edges: list[WorkflowEdge] | None = None


class ExportWorkflowRequest(BaseModel):
    """Export a connected version subgraph into a workflow template."""

    model_config = ConfigDict(extra="forbid")

    version_ids: list[str] = Field(min_length=1)
    title: str = Field(default="Exported workflow", max_length=120)


class WorkflowRunStatus(str, Enum):
    """Lifecycle of one workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_MANUAL = "waiting_manual"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkflowRun(BaseModel):
    """One execution of a workflow template against a new image."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    workflow_id: str
    owner_key_id: str
    session_id: str | None = None
    status: WorkflowRunStatus = WorkflowRunStatus.PENDING
    node_version_map: dict[str, str] = Field(default_factory=dict)
    waiting_node_id: str | None = None
    output_version_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ManualResumeRequest(BaseModel):
    """Resume a run paused on a manual condition node."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = True


class WorkflowValidationError(ValueError):
    """Raised when a workflow graph is structurally invalid."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}
