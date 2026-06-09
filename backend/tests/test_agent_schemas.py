from app.agent.schemas import AgentPlanRequest, IntentPlan, IntentType


def test_intent_plan_defaults() -> None:
    plan = IntentPlan(
        intent=IntentType.INPAINT,
        refined_prompt="a red hat",
        target_tool="comfyui_inpaint_v1",
    )
    assert plan.intent == IntentType.INPAINT
    assert plan.target_tool == "comfyui_inpaint_v1"


def test_agent_plan_request_override() -> None:
    req = AgentPlanRequest(
        user_message="draw a cat",
        intent_override=IntentType.TXT2IMG,
    )
    assert req.intent_override == IntentType.TXT2IMG
