import os
import base64
from typing import Dict, Any, Optional
import requests
from PIL import Image
import io

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class OpenAIVisionExtractor:
    """OpenAI Vision API extractor for receipt OCR."""

    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.model = "gpt-4o-mini"  # Using the cost-effective vision model

    def extract_with_custom_prompt(self, image_data: bytes, custom_prompt: str, filename: str) -> Dict[str, Any]:
        """Extract data using a custom prompt for specialized corrections."""
        
        try:
            print(f"🤖 Starting OpenAI Vision correction for: {filename}")

            # Convert image to base64
            base64_image = self._encode_image(image_data)

            # Make API call with custom prompt
            response = self._call_openai_api(base64_image, custom_prompt)

            # Parse the response for correction
            corrected_data = self._parse_correction_response(response)

            print(f"🤖 OpenAI Vision correction completed")

            return corrected_data

        except Exception as e:
            print(f"❌ OpenAI Vision correction failed: {e}")
            raise

    def _encode_image(self, image_data: bytes) -> str:
        """Convert image bytes to base64 string."""
        return base64.b64encode(image_data).decode('utf-8')

    def _create_receipt_prompt(self) -> str:
        """Create the prompt for OpenAI Vision to analyze receipts."""
        return """
You are an expert at extracting structured data from Japanese receipts. Analyze this receipt image and extract the following information in JSON format:

Required fields:
- date: The receipt date in YYYY-MM-DD format
- vendor: The store/restaurant name
- total: The total amount as a number (without currency symbols)
- invoice_number: Any receipt/invoice number
- tax_category: "標準税率" (standard rate) or "軽減税率" (reduced rate)
- account_title: Expense category in Japanese (食費, 交通費, 接待交際費, etc.)
- subtotal: Subtotal amount if shown
- tax: Tax amount if shown
- currency: Always "JPY"

Instructions:
1. Look for Japanese text and numbers on the receipt
2. Extract dates in YYYY-MM-DD format (convert from Japanese format if needed)
3. Find the store name (usually at the top)
4. Locate the total amount (usually at the bottom)
5. Determine tax category from tax rate shown (8% = 軽減税率, 10% = 標準税率)
6. Categorize the expense based on the type of purchase
7. Return only valid JSON, no additional text

Example output:
{
  "date": "2025-01-15",
  "vendor": "セブンイレブン",
  "total": "1250",
  "invoice_number": "123456789",
  "tax_category": "軽減税率",
  "account_title": "食費",
  "subtotal": "1136",
  "tax": "114",
  "currency": "JPY"
}
"""

    def _call_openai_api(self, base64_image: str, prompt: str) -> Dict[str, Any]:
        """Make API call to OpenAI Vision."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.1  # Low temperature for consistent extraction
        }

        response = requests.post(self.api_url, headers=headers, json=payload)
        response.raise_for_status()

        return response.json()

    def _parse_openai_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the OpenAI API response and extract structured data."""
        try:
            content = response['choices'][0]['message']['content']

            # Try to extract JSON from the response
            import json
            import re

            # Look for JSON in the response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)

                # Validate required fields
                required_fields = ['date', 'vendor', 'total', 'currency']
                for field in required_fields:
                    if field not in data:
                        raise ValueError(f"Missing required field: {field}")

                # Ensure currency is JPY
                data['currency'] = 'JPY'

                return data
            else:
                raise ValueError("No JSON found in OpenAI response")

        except Exception as e:
            print(f"❌ Failed to parse OpenAI response: {e}")
            print(f"Raw response: {response}")
            raise

    def _parse_correction_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the OpenAI API response for text correction."""
        try:
            content = response['choices'][0]['message']['content']
            
            # For correction, we expect just the corrected text
            corrected_text = content.strip()
            
            return {
                'corrected_text': corrected_text,
                'original_response': content
            }

        except Exception as e:
            print(f"❌ Failed to parse OpenAI correction response: {e}")
            print(f"Raw response: {response}")
            raise
