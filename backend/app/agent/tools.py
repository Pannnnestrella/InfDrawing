from app.agent.schemas import IntentType

TOOL_REGISTRY = {
    "comfyui_txt2img_v1": {
        "intent": IntentType.TXT2IMG,
        "workflow": "sd15_txt2img_api.json",
    },
    "comfyui_inpaint_v1": {
        "intent": IntentType.INPAINT,
        "workflow": "sd15_inpaint_api.json",
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
