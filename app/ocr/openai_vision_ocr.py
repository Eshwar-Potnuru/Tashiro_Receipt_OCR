"""
OpenAI Vision API OCR Engine
Uses GPT-4 Vision for text extraction from images
Compatible with requests-based API calls
"""

import logging
import base64
import io
import os
import requests
from typing import Optional
from PIL import Image

logger = logging.getLogger(__name__)

class OpenAIVisionOCR:
    """OpenAI GPT-4 Vision OCR Engine"""
    
    def __init__(self):
        """Initialize OpenAI Vision OCR"""
        self.api_key = None
        
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
            # Encode image to base64
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            
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
            
            # Make API request
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")
            
            # Extract text from response
            result = response.json()
            extracted_text = result['choices'][0]['message']['content']
            
            logger.info(f"OpenAI Vision extracted {len(extracted_text)} characters")
            return extracted_text
            
        except Exception as e:
            logger.error(f"OpenAI Vision extraction failed: {str(e)}")
            raise