from app.agent.prompts import SYSTEM_PROMPT
from app.agent.providers import IntentProvider, ProviderError, build_intent_provider
from app.agent.schemas import AgentPlanRequest, IntentPlan, IntentType
from app.agent.tools import TOOL_REGISTRY
from app.config import settings

_TOOL_BY_INTENT = {
    IntentType.TXT2IMG: "comfyui_txt2img_v1",
    IntentType.INPAINT: "comfyui_inpaint_v1",
    IntentType.IMAGE_EDIT: "openai_image_edit_v1",
    IntentType.DECOMPOSE: "comfyui_decompose_v1",
    IntentType.TEXT_EDIT: "comfyui_text_edit_v1",
}


class RoutingValidationError(ValueError):
    """Raised when a routed tool is inconsistent with context or capabilities."""


def _deterministic_plan(request: AgentPlanRequest, reason: str) -> IntentPlan:
    """Build a deterministic plan for overrides or provider degradation."""
    message = request.user_message.lower()
    intent = request.intent_override
    if intent is None:
        if any(word in message for word in ("文字", "文本", "text", "replace words")):
            intent = IntentType.TEXT_EDIT
        elif any(word in message for word in ("拆", "分层", "layer", "decompose")):
            intent = IntentType.DECOMPOSE
        elif any(word in message for word in ("蒙版", "mask", "inpaint", "刷选")):
            intent = IntentType.INPAINT
        elif any(
            word in message
            for word in ("改图", "修改图片", "把图", "换成", "改成", "image edit", "edit the")
        ):
            intent = IntentType.IMAGE_EDIT
        else:
            intent = IntentType.TXT2IMG
    return IntentPlan(
        intent=intent,
        refined_prompt=request.user_message,
        target_tool=_TOOL_BY_INTENT[intent],
        confidence=1.0 if request.intent_override else 0.55,
        reasoning=reason,
    )


def validate_plan(plan: IntentPlan, request: AgentPlanRequest) -> IntentPlan:
    """Validate registry, capabilities, context, and clarification semantics."""
    tool = TOOL_REGISTRY.get(plan.target_tool)
    if tool is None or tool["intent"] != plan.intent:
        raise RoutingValidationError("target_tool does not match the routed intent")

    context = request.context
    if context and context.capabilities.get(plan.intent.value) is False:
        raise RoutingValidationError(f"capability is disabled: {plan.intent.value}")

    missing: list[str] = []
    if plan.intent in {
        IntentType.INPAINT,
        IntentType.IMAGE_EDIT,
        IntentType.DECOMPOSE,
        IntentType.TEXT_EDIT,
    }:
        if context is None or not context.image_id:
            missing.append("image_id")
    if plan.intent == IntentType.INPAINT and (context is None or not context.mask_id):
        missing.append("mask_id")
    if plan.intent == IntentType.TEXT_EDIT:
        if context is None or context.bbox is None:
            missing.append("bbox")
        routed_text = plan.params.get("new_text")
        if isinstance(routed_text, str) and routed_text.strip():
            plan.params["new_text"] = routed_text.strip()
        elif request.intent_override and context and context.new_text:
            plan.params["new_text"] = context.new_text
        else:
            missing.append("new_text")
    if missing:
        plan.clarification_required = True
        plan.clarification_question = f"请补充以下输入：{', '.join(missing)}"
    elif plan.confidence < settings.intent_confidence_threshold:
        plan.clarification_required = True
        plan.clarification_question = "请确认希望执行的编辑类型和目标区域。"
    return plan


async def plan_intent(
    request: AgentPlanRequest,
    provider: IntentProvider | None = None,
) -> IntentPlan:
    """Route an agent request, giving explicit overrides highest priority."""
    if request.intent_override:
        return validate_plan(_deterministic_plan(request, "explicit user override"), request)
    try:
        selected_provider = provider or build_intent_provider()
        plan = await selected_provider.classify(SYSTEM_PROMPT, request.user_message)
    except ProviderError:
        plan = _deterministic_plan(request, "provider unavailable; deterministic routing")
    return validate_plan(plan, request)
