"""
OpenAI Vision API OCR Engine
Uses GPT-4 Vision for text extraction from images
Compatible with requests-based API calls
"""

import logging
import base64
import io
import os
import time
import requests
from requests import exceptions as requests_exceptions
from typing import Optional
from PIL import Image

logger = logging.getLogger(__name__)

class OpenAIVisionOCR:
    """OpenAI GPT-4 Vision OCR Engine"""
    
    def __init__(self):
        """Initialize OpenAI Vision OCR"""
        self.api_key = None
        self.max_image_dim = int(os.getenv('OPENAI_IMAGE_MAX_DIM', '1600'))
        self.retry_attempts = int(os.getenv('OPENAI_RETRY_ATTEMPTS', '3'))
        self.connect_timeout = int(os.getenv('OPENAI_CONNECT_TIMEOUT', '5'))
        self.read_timeout = int(os.getenv('OPENAI_READ_TIMEOUT', '13'))
        
        # Detect Railway environment and adjust timeouts for cloud deployment
        is_railway = os.getenv('RAILWAY_ENVIRONMENT') is not None or os.getenv('RAILWAY_PROJECT_ID') is not None
        if is_railway:
            logger.info("Railway environment detected - increasing OpenAI timeouts for cloud deployment")
            self.read_timeout = max(self.read_timeout, 23)  # Increase to 20s minimum
            self.retry_attempts = max(self.retry_attempts, 5)  # Increase to 5 retries minimum
        
        # Check for OpenAI API key
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            try:
                self.api_key = api_key
                logger.info("OpenAI Vision API initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI Vision API: {str(e)}")
        else:
            logger.warning("OpenAI API key not found")
    
    def is_available(self) -> bool:
        """Check if OpenAI Vision is available"""
        return self.api_key is not None
    
    def extract_text(self, image_data: bytes) -> str:
        """
        Extract text from image using OpenAI Vision
        
        Args:
            image_data: Image bytes
            
        Returns:
            Extracted text string
        """
        if not self.is_available():
            raise Exception("OpenAI Vision not available")
        
        try:
            prepared_image = self._prepare_image_payload(image_data)
            image_b64 = base64.b64encode(prepared_image).decode('utf-8')
            
            # Prepare request headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # Prepare request payload
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract ALL text from this image exactly as it appears. Include all numbers, Japanese characters, symbols, and formatting. Return only the text, no explanations."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 2000
            }
            
            last_error: Optional[Exception] = None
            for attempt in range(1, self.retry_attempts + 1):
                try:
                    response = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=(self.connect_timeout, self.read_timeout)
                    )

                    if response.status_code != 200:
                        raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")

                    result = response.json()
                    extracted_text = result['choices'][0]['message']['content']

                    logger.info(f"OpenAI Vision extracted {len(extracted_text)} characters")
                    return extracted_text

                except (requests_exceptions.Timeout, requests_exceptions.ConnectionError) as net_err:
                    last_error = net_err
                    logger.warning(f"OpenAI Vision request timeout (attempt {attempt}/{self.retry_attempts}): {net_err}")
                    if attempt < self.retry_attempts:
                        time.sleep(attempt)
                except Exception as e:
                    last_error = e
                    logger.error(f"OpenAI Vision extraction failed on attempt {attempt}: {e}")
                    if attempt < self.retry_attempts:
                        time.sleep(attempt)
                    else:
                        raise

            raise last_error or Exception("OpenAI Vision extraction failed after retries")

        except Exception as e:
            logger.error(f"OpenAI Vision extraction failed: {str(e)}")
            raise

    def _prepare_image_payload(self, image_data: bytes) -> bytes:
        """Downscale and compress the image to reduce upload size for OpenAI Vision."""
        try:
            image = Image.open(io.BytesIO(image_data))
            image = image.convert('RGB')
            width, height = image.size
            max_dim = max(width, height)

            if max_dim > self.max_image_dim:
                resize_ratio = self.max_image_dim / float(max_dim)
                new_size = (int(width * resize_ratio), int(height * resize_ratio))
                image = image.resize(new_size, Image.LANCZOS)

            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85, optimize=True)
            return buffer.getvalue()
        except Exception as e:
            logger.warning(f"OpenAI Vision image prep failed, sending original bytes: {e}")
            return image_data