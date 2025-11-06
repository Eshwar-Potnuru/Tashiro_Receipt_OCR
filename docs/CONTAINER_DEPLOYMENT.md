# Container Deployment Guide

## Environment Variables for Railway Deployment

Set these environment variables in your Railway dashboard:

### Required
- `OCR_SPACE_API_KEY`: Your OCR.space API key
- `OPENAI_API_KEY`: Your OpenAI API key

### Optional (but recommended for best performance)
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to Google Vision credentials (set to `/app/config/google_vision_key.json`)

## Google Vision Setup

1. Upload your `google_vision_key.json` file to the Railway service
2. Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to `/app/config/google_vision_key.json`

## Fallback Behavior

The system will automatically fall back through these OCR engines:
1. Google Vision API (highest accuracy)
2. OpenAI Vision API (structured extraction)
3. PaddleOCR (free, good accuracy)
4. EasyOCR (basic fallback)
5. OCR.space API (external service)

If premium engines are not configured, the system will still work using OCR.space API.