from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntentType(str, Enum):
    TXT2IMG = "txt2img"
    INPAINT = "inpaint"
    IMAGE_EDIT = "image_edit"
    DECOMPOSE = "decompose"
    TEXT_EDIT = "text_edit"


class IntentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentType
    refined_prompt: str
    negative_prompt: str = "blurry, low quality, distorted, ugly"
    target_tool: str
    params: dict = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str | None = None
    clarification_required: bool = False
    clarification_question: str | None = None


class AgentContext(BaseModel):
    """Inputs and capability snapshot available to routing."""

    image_id: str | None = None
    mask_id: str | None = None
    bbox: list[int] | None = Field(default=None, min_length=4, max_length=4)
    new_text: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentPlanRequest(BaseModel):
    user_message: str
    intent_override: IntentType | None = None
    context: AgentContext | None = None


class AgentPlanResponse(BaseModel):
    plan: IntentPlan


class GenerateTaskResponse(BaseModel):
    task_id: str
