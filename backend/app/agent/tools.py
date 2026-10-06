"""Map agent tool names (IntentPlan.target_tool) to pipeline workflows.

``workflow`` values are keys of :data:`app.pipeline.workflow_registry.WORKFLOWS`;
``None`` marks multi-step pipelines that orchestrate their own workflows.
"""

from app.agent.schemas import IntentType

TOOL_REGISTRY = {
    "comfyui_txt2img_v1": {
        "intent": IntentType.TXT2IMG,
        "workflow": "sd15_txt2img",
    },
    "comfyui_inpaint_v1": {
        "intent": IntentType.INPAINT,
        "workflow": "sd15_inpaint",
    },
    "openai_image_edit_v1": {
        "intent": IntentType.IMAGE_EDIT,
        "workflow": None,
    },
    "comfyui_decompose_v1": {
        "intent": IntentType.DECOMPOSE,
        "workflow": None,
    },
    "comfyui_text_edit_v1": {
        "intent": IntentType.TEXT_EDIT,
        "workflow": None,
    },
}
