from __future__ import annotations

import math
from typing import Optional

import cv2
import numpy as np
from PIL import Image


def _pil_to_cv(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def _cv_to_pil(image: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def deskew(image: Image.Image) -> Image.Image:
    cv_img = _pil_to_cv(image)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = cv_img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(cv_img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return _cv_to_pil(rotated)


def denoise_image(image: Image.Image) -> Image.Image:
    cv_img = _pil_to_cv(image)
    denoised = cv2.fastNlMeansDenoisingColored(cv_img, None, 10, 10, 7, 21)
    return _cv_to_pil(denoised)


def enhance_contrast(image: Image.Image) -> Image.Image:
    cv_img = _pil_to_cv(image)
    lab = cv2.cvtColor(cv_img, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l_channel)


def advanced_japanese_preprocessing(image: Image.Image) -> Image.Image:
    """
    Advanced preprocessing specifically optimized for Japanese receipts
    Combines multiple techniques to improve OCR accuracy on poor quality images
    """
    cv_img = _pil_to_cv(image)
    
    # 1. Resize to optimal dimensions for OCR
    height, width = cv_img.shape[:2]
    if width < 800:
        # Upscale small images using high-quality interpolation
        scale_factor = 800 / width
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        cv_img = cv2.resize(cv_img, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
    
    # 2. Convert to grayscale for better text detection
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    
    # 3. Advanced denoising - reduce image noise while preserving text
    denoised = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    
    # 4. Adaptive histogram equalization for better contrast
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    
    # 5. Sharpening filter to improve text edges
    kernel = np.array([[-1, -1, -1],
                      [-1,  9, -1],
                      [-1, -1, -1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    
    # 6. Morphological operations to improve text structure
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
    morphed = cv2.morphologyEx(sharpened, cv2.MORPH_CLOSE, kernel)
    
    # 7. Gaussian blur to smooth text (very light)
    blurred = cv2.GaussianBlur(morphed, (1, 1), 0)
    
    # Convert back to RGB for PIL
    result = cv2.cvtColor(blurred, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(result)


def preprocess_for_ocr_space(image: Image.Image) -> Image.Image:
    """
    Preprocessing optimized specifically for OCR.space API
    OCR.space works better with high contrast, clean images
    """
    cv_img = _pil_to_cv(image)
    
    # 1. Ensure minimum resolution for OCR.space
    height, width = cv_img.shape[:2]
    if width < 1000 or height < 1000:
        # Scale up to at least 1000px on shortest side
        min_dimension = min(width, height)
        scale_factor = 1000 / min_dimension
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        cv_img = cv2.resize(cv_img, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
    
    # 2. Convert to grayscale
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    
    # 3. Light denoising (OCR.space is sensitive to over-processing)
    denoised = cv2.medianBlur(gray, 3)
    
    # 4. Adaptive thresholding for better text separation
    adaptive_thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    
    # 5. Light morphological cleaning
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
    cleaned = cv2.morphologyEx(adaptive_thresh, cv2.MORPH_OPEN, kernel)
    
    # Convert back to RGB
    result = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(result)
    limg = cv2.merge((cl, a_channel, b_channel))
    enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    return _cv_to_pil(enhanced)


def binarize(image: Image.Image) -> Image.Image:
    cv_img = _pil_to_cv(image)
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 15)
    return Image.fromarray(thresh)


def resize(image: Image.Image, max_width: int = 1600) -> Image.Image:
    if image.width <= max_width:
        return image
    ratio = max_width / float(image.width)
    new_height = int(image.height * ratio)
    return image.resize((max_width, new_height), Image.Resampling.LANCZOS)


def preprocess_image(
    image: Image.Image,
    apply_binarize: bool = False,
    max_width: Optional[int] = 1600,
    min_width: Optional[int] = None,
    apply_deskew: bool = False,
    apply_denoise: bool = False,
    apply_contrast_enhance: bool = False,
) -> Image.Image:
    processed = image.convert("RGB")
    
    # Enhanced preprocessing order for Japanese receipts
    if apply_contrast_enhance:
        processed = enhance_contrast(processed)
    
    # Apply denoising before deskewing for better results
    if apply_denoise:
        processed = denoise_image(processed)
    
    if apply_deskew:
        processed = deskew(processed)
    
    # Resize handling with better quality preservation
    if min_width and processed.width < min_width:
        scale = math.ceil(min_width / processed.width)
        new_size = (processed.width * scale, processed.height * scale)
        # Use LANCZOS for better quality
        processed = processed.resize(new_size, Image.Resampling.LANCZOS)
    
    if max_width and processed.width > max_width:
        processed = resize(processed, max_width=max_width)
    
    # For Japanese text, avoid binarization unless specifically needed
    if apply_binarize:
        processed = binarize(processed)
    else:
        # Ensure RGB format for consistency
        processed = processed.convert("RGB")
    
    return processed
