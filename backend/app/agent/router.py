import json
import re

import httpx

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.schemas import AgentPlanRequest, IntentPlan, IntentType
from app.config import settings


def _fallback_plan(request: AgentPlanRequest) -> IntentPlan:
    intent = request.intent_override or IntentType.TXT2IMG
    tool_by_intent = {
        IntentType.TXT2IMG: "comfyui_txt2img_v1",
        IntentType.INPAINT: "comfyui_inpaint_v1",
        IntentType.DECOMPOSE: "comfyui_decompose_v1",
        IntentType.TEXT_EDIT: "comfyui_text_edit_v1",
    }
    tool = tool_by_intent.get(intent, "comfyui_txt2img_v1")
    return IntentPlan(
        intent=intent,
        refined_prompt=request.user_message,
        target_tool=tool,
        confidence=0.5,
        reasoning="fallback plan",
    )


def _extract_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


async def plan_intent(request: AgentPlanRequest) -> IntentPlan:
    if request.intent_override:
        return _fallback_plan(request) # 直接用用户选的 intent
     # 调 Ollama ...
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": request.user_message},
        ],
        "stream": False,
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = _extract_json(content)
            return IntentPlan.model_validate(data)
    except Exception:
        return _fallback_plan(request)
