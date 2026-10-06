"""Domain models for controlled multi-turn editing."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*(\.[a-z0-9][a-z0-9_]*)*$")
BBOX_TOLERANCE = 0.02


def new_id() -> str:
    """Return a random identifier for sessions and versions."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class EntityStatus(str, Enum):
    """How strongly an entity is protected during edits."""

    LOCKED = "locked"
    APPROVED = "approved"
    EDITABLE = "editable"


class BBoxSource(str, Enum):
    """Who produced an entity's bounding box."""

    MODEL = "model"
    MANUAL = "manual"


class EditOperation(str, Enum):
    """Kind of change requested by the user."""

    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"
    RESTYLE = "restyle"
    RECOLOR = "recolor"
    OTHER = "other"


class VersionStatus(str, Enum):
    """Lifecycle of a version node."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BBox(BaseModel):
    """Normalized bounding box; all values are fractions of image width/height."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    w: float
    h: float

    @model_validator(mode="after")
    def clip_to_image(self) -> BBox:
        """Clip small overflows and reject boxes that are clearly outside the image."""
        lo, hi = -BBOX_TOLERANCE, 1 + BBOX_TOLERANCE
        if self.w <= 0 or self.h <= 0:
            raise ValueError("bbox width and height must be positive")
        if not (lo <= self.x <= hi and lo <= self.y <= hi):
            raise ValueError("bbox origin is outside the image")
        if self.x + self.w > hi or self.y + self.h > hi:
            raise ValueError("bbox extends outside the image")
        x0, y0 = max(0.0, self.x), max(0.0, self.y)
        x1, y1 = min(1.0, self.x + self.w), min(1.0, self.y + self.h)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("bbox is empty after clipping")
        self.x, self.y, self.w, self.h = x0, y0, x1 - x0, y1 - y0
        return self


class SceneEntity(BaseModel):
    """One semantic element of the scene and its protection state."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    parent_id: str | None = None
    description: str = Field(default="", max_length=400)
    bbox: BBox | None = None
    bbox_source: BBoxSource = BBoxSource.MODEL
    status: EntityStatus = EntityStatus.EDITABLE
    anchor_version_id: str | None = None
    anchor_artifact_id: str | None = None

    @field_validator("id", "parent_id")
    @classmethod
    def validate_entity_id(cls, value: str | None) -> str | None:
        """Require dotted snake_case identifiers such as ``character.face``."""
        if value is not None and not ENTITY_ID_PATTERN.match(value):
            raise ValueError(f"invalid entity id: {value!r}")
        return value


class EditIntent(BaseModel):
    """Structured interpretation of one user instruction."""

    model_config = ConfigDict(extra="forbid")

    operation: EditOperation
    target_entity_ids: list[str] = Field(default_factory=list)
    new_entity_name: str | None = Field(default=None, max_length=80)
    location_hint: str | None = Field(default=None, max_length=300)
    change_description: str = Field(min_length=1, max_length=1_000)


class EntityPreservation(BaseModel):
    """Verifier score for one protected entity."""

    entity_id: str
    score: float = Field(ge=0.0, le=1.0)
    comment: str = ""


class VerificationResult(BaseModel):
    """VLM judgement of one generated candidate."""

    target_applied: bool
    target_comment: str = ""
    composition_score: float | None = Field(default=None, ge=0.0, le=1.0)
    composition_comment: str = ""
    preserved: list[EntityPreservation] = Field(default_factory=list)
    passed: bool
    warnings: list[str] = Field(default_factory=list)


class EditVersion(BaseModel):
    """One node of the version tree."""

    id: str = Field(default_factory=new_id)
    session_id: str
    parent_id: str | None = None
    status: VersionStatus = VersionStatus.PENDING
    progress_step: str | None = None
    image_artifact_id: str | None = None
    width: int | None = None
    height: int | None = None
    instruction: str | None = None
    intent: EditIntent | None = None
    compiled_prompt: str | None = None
    prompt_style: str | None = None
    image_provider: str | None = None
    reference_artifact_ids: list[str] = Field(default_factory=list)
    entities: list[SceneEntity] = Field(default_factory=list)
    verification: VerificationResult | None = None
    attempts: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EditSession(BaseModel):
    """A controlled editing session rooted at one uploaded image."""

    id: str = Field(default_factory=new_id)
    owner_key_id: str
    title: str = Field(default="Untitled", max_length=120)
    root_version_id: str | None = None
    current_version_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SessionTree(BaseModel):
    """A session together with every version node."""

    session: EditSession
    versions: list[EditVersion]


class EditTurnRequest(BaseModel):
    """Request body for one edit turn."""

    model_config = ConfigDict(extra="forbid")

    parent_version_id: str
    instruction: str = Field(min_length=1, max_length=2_000)
    target_entity_ids: list[str] = Field(default_factory=list)
    prompt_style: Literal["preserve", "target_only"] | None = None
    image_provider: Literal["dashscope", "openai"] | None = None


class EntityStatusUpdate(BaseModel):
    """Request body for changing one entity's protection status."""

    model_config = ConfigDict(extra="forbid")

    status: EntityStatus


class EntityBBoxUpdate(BaseModel):
    """Request body for manually correcting one entity's bounding box."""

    model_config = ConfigDict(extra="forbid")

    bbox: BBox


class CheckoutRequest(BaseModel):
    """Request body for moving the session cursor to another version."""

    model_config = ConfigDict(extra="forbid")

    version_id: str
