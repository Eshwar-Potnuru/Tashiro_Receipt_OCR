import io
import hashlib
from typing import Dict, Tuple
from PIL import Image

MAX_DIMENSION = 1600
JPEG_QUALITY = 85


def optimize_image_for_ocr(image_bytes: bytes) -> Tuple[bytes, Dict[str, str]]:
    """Normalize receipt images so OCR engines receive consistent payloads."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        original_format = image.format or "UNKNOWN"
        original_mode = image.mode
        original_size = image.size

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        elif image.mode == "L":
            image = image.convert("L")

        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

        optimized_buffer = io.BytesIO()
        save_format = "JPEG" if image.mode != "L" else "PNG"
        if save_format == "JPEG":
            image.save(optimized_buffer, format=save_format, quality=JPEG_QUALITY, optimize=True)
        else:
            image.save(optimized_buffer, format=save_format, optimize=True)

        optimized_bytes = optimized_buffer.getvalue()

    stats = {
        "original_format": original_format,
        "original_mode": original_mode,
        "original_size": f"{original_size[0]}x{original_size[1]}",
        "optimized_size_bytes": str(len(optimized_bytes)),
        "optimized_hash": hashlib.sha1(optimized_bytes).hexdigest(),
    }

    return optimized_bytes, stats
