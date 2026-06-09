from fastapi import APIRouter

from app.agent.router import plan_intent
from app.agent.schemas import AgentPlanRequest, AgentPlanResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/plan", response_model=AgentPlanResponse)
async def create_plan(request: AgentPlanRequest) -> AgentPlanResponse:
    plan = await plan_intent(request)
    return AgentPlanResponse(plan=plan)
