"""Validate uploaded image and mask dimensions for inpaint."""

import io

from fastapi import HTTPException
from PIL import Image

from app.config import settings

_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
}


def sniff_image_mime(data: bytes) -> str | None:
    """Infer MIME from magic bytes when the client omits Content-Type."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def resolve_upload_mime(data: bytes, declared_mime: str | None) -> str:
    """Prefer a valid declared MIME; otherwise sniff from bytes."""
    declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    if declared in _SIGNATURES:
        return declared
    sniffed = sniff_image_mime(data)
    if sniffed is not None:
        return sniffed
    raise HTTPException(status_code=415, detail="unsupported image MIME type")


def validate_upload_image(
    data: bytes,
    declared_mime: str | None,
) -> tuple[int, int, str]:
    """Validate image size, declared MIME, signature, decoding, and pixels.

    Args:
        data: Uploaded image bytes.
        declared_mime: Content-Type supplied by the multipart parser.

    Returns:
        Width, height, and verified MIME type.

    Raises:
        HTTPException: If any upload security constraint is violated.
    """
    if not data:
        raise HTTPException(status_code=400, detail="empty image upload")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="image exceeds upload size limit")
    resolved_mime = resolve_upload_mime(data, declared_mime)
    signatures = _SIGNATURES[resolved_mime]
    if not any(data.startswith(signature) for signature in signatures):
        raise HTTPException(status_code=415, detail="image signature does not match MIME type")
    if resolved_mime == "image/webp" and data[8:12] != b"WEBP":
        raise HTTPException(status_code=415, detail="invalid WebP signature")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            verified_mime = Image.MIME.get(image.format or "", "")
    except (OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=400, detail="invalid image data") from exc
    if verified_mime != resolved_mime:
        raise HTTPException(status_code=415, detail="decoded image type does not match MIME type")
    if width * height > settings.max_image_pixels:
        raise HTTPException(status_code=413, detail="image exceeds pixel limit")
    return width, height, verified_mime


def validate_inpaint_image_mask_pair(
    image_bytes: bytes,
    mask_bytes: bytes,
    image_mime: str = "image/png",
    mask_mime: str = "image/png",
) -> None:
    """Ensure image and mask share the same pixel dimensions.

    Args:
        image_bytes: Raw bytes of the source image.
        mask_bytes: Raw bytes of the mask image.

    Raises:
        HTTPException: If either file is invalid or sizes differ.
    """
    image_size = validate_upload_image(image_bytes, image_mime)[:2]
    mask_size = validate_upload_image(mask_bytes, mask_mime)[:2]

    if image_size != mask_size:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Mask size {mask_size[0]}x{mask_size[1]} does not match "
                f"image size {image_size[0]}x{image_size[1]}"
            ),
        )
