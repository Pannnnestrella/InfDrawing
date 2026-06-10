from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    TXT2IMG = "txt2img"
    INPAINT = "inpaint"
    DECOMPOSE = "decompose"
    TEXT_EDIT = "text_edit"


class IntentPlan(BaseModel):
    intent: IntentType
    refined_prompt: str
    negative_prompt: str = "blurry, low quality, distorted, ugly"
    target_tool: str
    params: dict = Field(default_factory=dict)
    confidence: float = 1.0
    reasoning: str | None = None


class AgentPlanRequest(BaseModel):
    user_message: str
    intent_override: IntentType | None = None
    context: dict | None = None


class AgentPlanResponse(BaseModel):
    plan: IntentPlan


class GenerateTaskResponse(BaseModel):
    task_id: str
