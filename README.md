# Tashiro Ironworks Receipt OCR System

Professional receipt processing system for field operations with AI-powered OCR and automated expense categorization.

## 🚀 Quick Start

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application (no auto-reload)
python server.py

# Run with auto-reload for local dev
python server.py --reload
```

Access the application at:
- **Desktop Interface**: http://localhost:8000/
- **Mobile Interface**: http://localhost:8000/mobile
- **API Documentation**: http://localhost:8000/docs

### Railway Deployment

1. **Connect to Railway**:
   - Push this repository to GitHub
   - Connect your GitHub repo to Railway
   - Railway will auto-detect the Python app and deploy

2. **Environment Variables** (set in Railway dashboard):
   ```
   OCR_SPACE_API_KEY=<your_ocr_space_key>
   OPENAI_API_KEY=<your_openai_key>
   GOOGLE_VISION_CREDENTIALS_JSON=<service_account_json>
   # or provide GOOGLE_VISION_CREDENTIALS_B64 when pasting base64-encoded JSON
   ```
   The Google Vision credential value can be copied directly from the JSON service-account file. Railway keeps long strings, so you no longer need to commit `config/google_vision_key.json`.

3. **Access Your Deployed App**:
   - Railway will provide a public URL (e.g., `https://your-app.railway.app`)
   - Use this URL for both desktop and mobile testing

## 📱 Features

- **Unified Interface**: Works seamlessly on desktop and mobile
- **Camera Capture**: Live camera feed for receipt photos (HTTPS required)
- **File Upload**: Drag & drop or select from gallery
- **AI OCR**: Powered by OCR.space API with Japanese language support
- **Field Extraction**: Automatic extraction of A-F fields (Date, Vendor, Total, etc.)
- **Tax Calculation**: Automatic tax category detection and calculation
- **Excel Export**: Professional Excel format for HQ workflow
- **History Tracking**: Submission history with verification status
- **Manual Corrections**: Edit AI-suggested categories on-the-spot

## 🏗️ Architecture

- **Backend**: FastAPI (Python)
- **OCR Engine**: OCR.space API
- **Frontend**: HTML5/CSS3/JavaScript (responsive)
- **Data Export**: Excel (openpyxl)
- **Deployment**: Railway (Python app hosting)

## 📋 Requirements

- Python 3.8+
- Valid OCR.space API key
- HTTPS for camera functionality (automatic on Railway)
- The Docker image installs the lightweight `requirements.txt` (FastAPI + OpenAI/Google Vision). If you need PaddleOCR, swap the Dockerfile `COPY requirements.txt` back to `requirements_production.txt` or install the optional packages manually.

## 🔧 Configuration

### Environment Variables
- `OCR_SPACE_API_KEY`: OCR.space API key (required)
- `OPENAI_API_KEY`: Enables OpenAI Vision engine
- `GOOGLE_VISION_CREDENTIALS_JSON` or `GOOGLE_VISION_CREDENTIALS_B64`: Inline Google Vision service-account credentials (useful for Railway)
- `GOOGLE_APPLICATION_CREDENTIALS`: Optional path to a mounted JSON key if running on your own VM

### File Structure
```
receipt-ocr/
├── app/
│   ├── main.py              # FastAPI application
│   ├── api/routes.py        # API endpoints
│   ├── extractors/          # OCR field extraction
│   ├── exporters/           # Excel export functionality
│   ├── history/             # Submission tracking
│   ├── templates/           # HTML templates
│   └── static/              # CSS/JS assets
├── requirements.txt         # Python dependencies
├── run.py                   # Development server
├── railway.json             # Railway deployment config
└── .env                     # Environment variables
```

#### Accumulation Workbooks

Each save to HQ updates `app/Data/accumulation/<LOCATION>_Accumulated.xlsx` and mirrors the workbook to `artifacts/accumulation/`. The artifacts directory is exposed at `/artifacts/...`, so remote testers (Railway) can download the latest Excel by visiting, for example, `https://your-app.railway.app/artifacts/accumulation/Tokyo_Accumulated.xlsx`.

## 🚀 Deployment Status

✅ **Ready for Railway Deployment**
- All core components tested and working
- Dependencies properly configured
- Environment variables set
- HTTPS-ready for camera functionality

## ✅ Testing & Diagnostics

```bash
# Run the lightweight unit tests
pytest tests/test_image_processing.py tests/test_submission_history.py

# Exercise the live OCR pipeline (requires server running)
python scripts/manual_async_probe.py "Sample reciepts/sample1.jpg" --mode async
```

The manual probe uploads a receipt to `/api/mobile/analyze`, polls `/api/mobile/analyze/status/{queue_id}`, and prints the resulting JSON. Use it to validate async queueing, caching, and vendor normalization end-to-end.

## 📞 Support

For deployment issues or feature requests, contact the development team.