# preprocess.py
import cv2
import numpy as np
from PIL import Image
from io import BytesIO

def pil_to_cv(image: Image.Image):
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

def cv_to_pil(cv_img):
    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))

def enhance_contrast(pil_image: Image.Image) -> Image.Image:
    """
    Apply CLAHE and light sharpening to improve Japanese text legibility.
    """
    cv_img = pil_to_cv(pil_image.convert("RGB"))
    lab = cv2.cvtColor(cv_img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    cl = clahe.apply(l)
    limg = cv2.merge((cl,a,b))
    enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    # slight unsharp mask
    gaussian = cv2.GaussianBlur(enhanced, (0,0), 3)
    unsharp = cv2.addWeighted(enhanced, 1.2, gaussian, -0.2, 0)
    return cv_to_pil(unsharp)

def compress_for_api(pil_image: Image.Image, max_size_kb=1024) -> bytes:
    """
    Compress image for OCR.space or other size-limited APIs without double-saving.
    For Google Vision prefer higher quality, so call compress only for engines requiring it.
    """
    buf = BytesIO()
    pil_image.save(buf, format="JPEG", quality=90)
    data = buf.getvalue()
    if len(data) / 1024 <= max_size_kb:
        return data
    # Resize proportionally (max dimension)
    w, h = pil_image.size
    ratio = (1600 / max(w,h)) if max(w,h) > 1600 else 1.0
    new_sz = (int(w*ratio), int(h*ratio))
    img2 = pil_image.resize(new_sz, Image.LANCZOS)
    buf = BytesIO()
    img2.save(buf, format="JPEG", quality=85)
    return buf.getvalue()

def preprocess_for_engine(pil_image: Image.Image, engine: str) -> bytes:
    """
    Engine-specific preprocessing dispatcher returns image bytes ready for that engine.
    """
    # Always enhance contrast first
    enhanced = enhance_contrast(pil_image)
    if engine == "google_vision":
        # Google performs better with higher quality images; return PNG bytes
        buf = BytesIO()
        enhanced.save(buf, format="PNG")
        return buf.getvalue()
    else:
        # For OCR.space or other engines, compress to meet size limits
        return compress_for_api(enhanced)
