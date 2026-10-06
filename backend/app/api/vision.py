from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.pipeline.image_validation import validate_upload_image
from app.pipeline.text_detect import detect_text_regions, easyocr_available

router = APIRouter(prefix="/vision", tags=["vision"])


class TextRegionOut(BaseModel):
    text: str
    bbox: list[int] = Field(min_length=4, max_length=4)
    confidence: float


class DetectTextResponse(BaseModel):
    regions: list[TextRegionOut]
    image_width: int
    image_height: int


@router.post("/detect-text", response_model=DetectTextResponse)
async def detect_text(image: UploadFile = File(...)) -> DetectTextResponse:
    """Detect text regions in an uploaded image via EasyOCR."""
    if not easyocr_available():
        raise HTTPException(status_code=503, detail="easyocr not installed")
    image_bytes = await image.read()
    validate_upload_image(image_bytes, image.content_type)
    try:
        regions, width, height = detect_text_regions(image_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return DetectTextResponse(
        regions=[
            TextRegionOut(
                text=region.text,
                bbox=list(region.bbox),
                confidence=region.confidence,
            )
            for region in regions
        ],
        image_width=width,
        image_height=height,
    )
