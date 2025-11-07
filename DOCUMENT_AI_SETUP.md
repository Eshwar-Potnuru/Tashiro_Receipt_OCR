# Google Document AI Setup Guide

## Overview
Google Document AI provides superior structured document processing compared to basic text detection. It can automatically extract fields like totals, vendor names, dates, and line items from receipts and invoices.

## Setup Steps

### 1. Enable Document AI API
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Select your project (same one with Vision API)
3. Go to **APIs & Services > Library**
4. Search for "Document AI API"
5. Click **Enable**

### 2. Create a Document AI Processor
1. Go to **Document AI > Processors**
2. Click **CREATE PROCESSOR**
3. Select **Form Parser** (good for receipts/invoices)
4. Choose **Region**: us (United States)
5. Enter **Processor Name**: `receipt-parser`
6. Click **CREATE**

### 3. Get Processor Information
After creating the processor, you'll see:
- **Processor ID**: Copy this (looks like: `abc123def456`)
- **Location**: `us` 
- **Project ID**: Your Google Cloud project ID

### 4. Update Code Configuration
Edit `app/ocr/document_ai_ocr.py` and update line 37:
```python
# Replace YOUR_PROCESSOR_ID with your actual processor ID
self.processor_name = f"projects/{self.project_id}/locations/{self.location}/processors/YOUR_PROCESSOR_ID"
```

Example:
```python
self.processor_name = f"projects/{self.project_id}/locations/{self.location}/processors/abc123def456"
```

### 5. Test Document AI
Document AI will use the same credentials as Google Vision API (`config/google_vision_key.json`).

### 6. Processing Quotas
Document AI has monthly processing quotas:
- **Free Tier**: 1,000 documents/month
- **Paid Tier**: Pay per document

## Benefits of Document AI vs Vision API

| Feature | Vision API (Text Detection) | Document AI (Form Parser) |
|---------|---------------------------|-------------------------|
| Text Extraction | ✅ Good | ✅ Excellent |
| Structured Fields | ❌ Manual parsing needed | ✅ Automatic extraction |
| Receipt Understanding | ❌ No context | ✅ Understands receipts |
| Total Amount | ❌ Pattern matching | ✅ Automatic detection |
| Vendor Name | ❌ Pattern matching | ✅ Automatic detection |
| Line Items | ❌ Manual parsing | ✅ Table extraction |
| Confidence Scores | ❌ Limited | ✅ Per-field confidence |

## Expected Improvements
With Document AI, you should see:
- **Accurate totals**: Extracts correct amounts (3793 instead of 3)
- **Better vendor detection**: Handles complex store names
- **Structured line items**: Individual product extraction
- **Higher confidence**: Field-level accuracy scores
- **Reduced parsing errors**: Less regex pattern matching needed