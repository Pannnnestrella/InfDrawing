from fastapi import APIRouter

from app.system.capabilities import gather_capabilities
from app.system.schemas import CapabilitiesResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities() -> CapabilitiesResponse:
    """Return detected GPU, services, models and feature flags."""
    return await gather_capabilities()
