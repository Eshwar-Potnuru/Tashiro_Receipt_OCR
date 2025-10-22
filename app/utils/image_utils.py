from __future__ import annotations

import base64
import io
from typing import Iterable, Tuple

from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_bytes
from pdf2image.exceptions import (  # type: ignore[attr-defined]
    PDFInfoNotInstalledError,
    PDFPageCountError,
    PDFSyntaxError,
)

SUPPORTED_IMAGE_FORMATS: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")


class PDFConversionError(RuntimeError):
    """Raised when a PDF cannot be converted into images."""


def load_image_from_bytes(data: bytes) -> Image.Image:
    """Load an image from a byte sequence into a PIL Image object."""
    return Image.open(io.BytesIO(data)).convert("RGB")


def pdf_to_images(pdf_bytes: bytes, dpi: int = 300) -> list[Image.Image]:
    """Convert PDF bytes into a list of PIL Images."""
    try:
        images = convert_from_bytes(pdf_bytes, dpi=dpi)
        return [img.convert("RGB") for img in images]
    except (PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError) as exc:
        raise PDFConversionError("Unable to convert PDF to images. Ensure poppler is installed.") from exc


def image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def ensure_iterable(obj: Image.Image | Iterable[Image.Image]) -> Iterable[Image.Image]:
    if isinstance(obj, Image.Image):
        return [obj]
    return obj


def annotate_fields(image: Image.Image, boxes: dict[str, list[list[float]]]) -> Image.Image:
    annotated = image.convert("RGB").copy()
    draw = ImageDraw.Draw(annotated)
    font = _load_font()
    colors = {
        "vendor": "#FF5733",
        "date": "#1F618D",
        "currency": "#117A65",
        "subtotal": "#6C3483",
        "tax": "#7D6608",
        "total": "#CB4335",
    }
    for field, box in boxes.items():
        if not box:
            continue
        flat = list(box)
        if len(flat) != 4:
            continue
        color = colors.get(field, "#2E86C1")
        draw.polygon([(point[0], point[1]) for point in flat], outline=color, width=3)
        label_position = (flat[0][0], max(flat[0][1] - 15, 0))
        draw.text(label_position, field, fill=color, font=font)
    return annotated


def _load_font() -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", 16)
    except (OSError, IOError):  # pragma: no cover - platform dependent
        return ImageFont.load_default()
