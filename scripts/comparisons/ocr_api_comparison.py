#!/usr/bin/env python3
"""
OCR API Comparison and Recommendation Script
Helps choose the best OCR API for receipt processing based on accuracy, cost, and ease of use.
"""

import json
from typing import Dict, List


def get_ocr_api_comparison() -> Dict:
    """Get detailed comparison of OCR APIs."""
    return {
        "google_vision": {
            "name": "Google Cloud Vision API",
            "accuracy": "★★★★★ (95-98%)",
            "japanese_support": "★★★★★ (Native)",
            "receipt_specialization": "★★★★☆",
            "pricing": {
                "free_tier": "1,000 requests/month",
                "paid": "$1.50 per 1,000 requests",
                "additional_costs": "No setup fees"
            },
            "pros": [
                "Highest accuracy for receipts",
                "Excellent Japanese text recognition",
                "Handles complex layouts well",
                "Auto-detects text orientation",
                "Built-in preprocessing"
            ],
            "cons": [
                "Requires Google Cloud setup",
                "Slightly more complex authentication",
                "Not free beyond 1,000 requests"
            ],
            "setup_difficulty": "Medium",
            "best_for": "High-accuracy receipt processing, Japanese text"
        },

        "openai_vision": {
            "name": "OpenAI GPT-4 Vision",
            "accuracy": "★★★★★ (96-99%)",
            "japanese_support": "★★★★★ (Excellent)",
            "receipt_specialization": "★★★★★",
            "pricing": {
                "free_tier": "None",
                "paid": "$0.001275 per image (low detail), $0.00255 per image (high detail)",
                "additional_costs": "OpenAI API key required"
            },
            "pros": [
                "Highest accuracy with GPT-4 understanding",
                "Can extract structured data intelligently",
                "Excellent at understanding receipt context",
                "Handles various receipt formats",
                "Can answer questions about receipt content"
            ],
            "cons": [
                "Most expensive option",
                "Requires OpenAI API access",
                "Rate limits apply",
                "Less specialized for pure OCR"
            ],
            "setup_difficulty": "Easy",
            "best_for": "Maximum accuracy, intelligent data extraction"
        },

        "microsoft_azure": {
            "name": "Microsoft Azure Computer Vision",
            "accuracy": "★★★★☆ (90-95%)",
            "japanese_support": "★★★★☆ (Good)",
            "receipt_specialization": "★★★★☆",
            "pricing": {
                "free_tier": "5,000 transactions/month",
                "paid": "$1.50 per 1,000 transactions",
                "additional_costs": "Azure subscription required"
            },
            "pros": [
                "Good accuracy and Japanese support",
                "Competitive pricing",
                "Strong enterprise features",
                "Good documentation",
                "Handles various image formats"
            ],
            "cons": [
                "Slightly lower accuracy than Google/OpenAI",
                "Azure account required",
                "More complex pricing tiers"
            ],
            "setup_difficulty": "Medium",
            "best_for": "Enterprise deployments, balanced cost/accuracy"
        },

        "google_gemini": {
            "name": "Google Gemini Vision",
            "accuracy": "★★★★☆ (90-95%)",
            "japanese_support": "★★★★☆ (Good)",
            "receipt_specialization": "★★★★☆",
            "pricing": {
                "free_tier": "60 requests/minute",
                "paid": "$0.00025 per image (Gemini 1.5 Pro)",
                "additional_costs": "Google AI API key"
            },
            "pros": [
                "Good multimodal capabilities",
                "Competitive pricing",
                "Modern AI model",
                "Good Japanese support"
            ],
            "cons": [
                "Newer technology, less proven for OCR",
                "May have rate limits",
                "Less specialized for receipts"
            ],
            "setup_difficulty": "Easy",
            "best_for": "Modern AI approach, multimodal tasks"
        },

        "ocr_space_current": {
            "name": "OCR.space (Current - Free Tier)",
            "accuracy": "★★☆☆☆ (70-80%)",
            "japanese_support": "★★★☆☆ (Basic)",
            "receipt_specialization": "★★★☆☆",
            "pricing": {
                "free_tier": "25,000 requests/month",
                "paid": "$0.02 per page (Pro), $0.05 per page (Advanced)",
                "additional_costs": "File size limits (1MB)"
            },
            "pros": [
                "Free tier available",
                "Simple API",
                "No setup required"
            ],
            "cons": [
                "Poor accuracy for receipts",
                "1MB file size limit",
                "Rate limits",
                "Less reliable for Japanese"
            ],
            "setup_difficulty": "Very Easy",
            "best_for": "Basic OCR, development/testing"
        }
    }


def print_comparison_table(apis: Dict):
    """Print a formatted comparison table."""
    print("\n🔍 OCR API Comparison for Receipt Processing")
    print("=" * 80)

    headers = ["API", "Accuracy", "Japanese", "Pricing", "Setup", "Best For"]
    print(f"{headers[0]:<20} {headers[1]:<12} {headers[2]:<10} {headers[3]:<15} {headers[4]:<8} {headers[5]}")
    print("-" * 80)

    for api_key, api_data in apis.items():
        name = api_data['name'][:19]  # Truncate long names
        accuracy = api_data['accuracy'].split()[0]  # Just the stars
        japanese = api_data['japanese_support'].split()[0]
        pricing = api_data['pricing']['paid'][:14]  # Truncate pricing
        setup = api_data['setup_difficulty']
        best_for = api_data['best_for'][:25]  # Truncate

        print(f"{name:<20} {accuracy:<12} {japanese:<10} {pricing:<15} {setup:<8} {best_for}")


def get_recommendation(current_accuracy_issue: bool = True) -> str:
    """Get personalized recommendation based on requirements."""

    if current_accuracy_issue:
        return """
🎯 **RECOMMENDATION: Google Cloud Vision API**

**Why Google Vision is BEST for your receipt OCR needs:**

1. **Superior Accuracy**: 95-98% vs OCR.space's 70-80%
2. **Japanese Excellence**: Native Japanese OCR support
3. **Receipt Specialization**: Designed for document processing
4. **Cost Effective**: $1.50 per 1,000 requests (very reasonable)
5. **Easy Integration**: Drop-in replacement for OCR.space

**Expected Improvements:**
- ✅ Much higher accuracy on amounts and item details
- ✅ Better Japanese character recognition
- ✅ Handles complex receipt layouts
- ✅ No 1MB file size limits
- ✅ Faster processing

**Setup Process:**
1. Run: `python setup_google_vision.py`
2. Follow the guided setup (5-10 minutes)
3. Update your code to use GoogleVisionExtractor
4. Deploy and test

**Pricing Breakdown:**
- Free tier: 1,000 requests/month
- Paid: $1.50 per 1,000 requests
- For 10,000 receipts/month: ~$15/month
- Much cheaper than GPT-4 Vision ($25-50/month)

**Why not others:**
- OpenAI GPT-4: Too expensive ($25-50/month vs $15)
- Microsoft Azure: Similar pricing but lower accuracy
- Gemini: Good but less proven for OCR
        """
    else:
        return "Please specify your accuracy requirements for a better recommendation."


def show_setup_instructions():
    """Show setup instructions for the recommended API."""
    print("\n🛠️  SETUP INSTRUCTIONS - Google Cloud Vision API")
    print("=" * 55)

    print("""
1. 📦 Install dependencies:
   pip install google-cloud-vision

2. 🔐 Create Google Cloud Project:
   - Go to: https://console.cloud.google.com/
   - Create new project or select existing
   - Enable Cloud Vision API

3. 🔑 Create Service Account:
   - IAM & Admin → Service Accounts
   - Create service account: "receipt-ocr-service"
   - Role: "Cloud Vision Client" or "Viewer"

4. 📥 Download JSON Key:
   - Service Account → Keys → Add Key → JSON
   - Download and save as 'google_credentials.json'

5. ⚙️  Configure Environment:
   Set GOOGLE_APPLICATION_CREDENTIALS=path/to/google_credentials.json

6. 🧪 Test Setup:
   python -c "from app.extractors.google_vision_extractor import test_google_vision_connection; test_google_vision_connection()"

7. 🔄 Update Code:
   Replace OCRSpaceExtractor with GoogleVisionExtractor in your main.py

8. 🚀 Deploy:
   Your accuracy should improve significantly!
    """)


def main():
    """Main function."""
    apis = get_ocr_api_comparison()

    # Print comparison table
    print_comparison_table(apis)

    # Show detailed recommendation
    print(get_recommendation())

    # Show setup instructions
    show_setup_instructions()

    print("\n❓ Questions? The setup script will guide you through everything!")
    print("💡 Run: python setup_google_vision.py")


if __name__ == "__main__":
    main()