#!/bin/bash
# OpenAI Vision OCR Setup Script

echo "🚀 Setting up OpenAI Vision OCR for Tashiro Receipt OCR"
echo "======================================================"

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo "❌ Python is not installed. Please install Python 3.8+ first."
    exit 1
fi

echo "✅ Python found: $(python --version)"

# Install/update requirements
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies. Please check your Python environment."
    exit 1
fi

echo "✅ Dependencies installed successfully"

# Check for OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo ""
    echo "⚠️  OpenAI API key not found in environment variables."
    echo ""
    echo "To get your OpenAI API key:"
    echo "1. Go to https://platform.openai.com/api-keys"
    echo "2. Create a new API key"
    echo "3. Copy the key and set it as an environment variable:"
    echo ""
    echo "   # Option 1: Set in your shell profile (~/.bashrc or ~/.zshrc)"
    echo "   export OPENAI_API_KEY='your-api-key-here'"
    echo ""
    echo "   # Option 2: Set temporarily for this session"
    echo "   export OPENAI_API_KEY='your-api-key-here'"
    echo ""
    echo "   # Option 3: Add to .env file (recommended)"
    echo "   Edit the .env file and replace 'your_openai_api_key_here' with your actual key"
    echo ""
    read -p "Do you have your OpenAI API key ready? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Please get your API key from https://platform.openai.com/api-keys"
        echo "Then run this setup script again."
        exit 1
    fi
else
    echo "✅ OpenAI API key found in environment"
fi

# Test the setup
echo ""
echo "🧪 Testing the setup..."
python -c "
try:
    from app.extractors.openai_vision_extractor import OpenAIVisionExtractor
    extractor = OpenAIVisionExtractor()
    print('✅ OpenAI Vision extractor initialized successfully')
except Exception as e:
    print(f'❌ OpenAI Vision setup failed: {e}')
    print('Please check your OPENAI_API_KEY')
"

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Usage:"
echo "1. Make sure your OPENAI_API_KEY is set in the .env file or environment"
echo "2. Run the application: python run.py"
echo "3. The system will now use OpenAI Vision for OCR (with OCR.space as fallback)"
echo ""
echo "Pricing Information:"
echo "- OpenAI GPT-4o: $0.001275 per image (512x512), $0.00255 for larger"
echo "- Much more accurate than OCR.space for Japanese receipts"
echo "- No file size limits (vs OCR.space 1MB limit)"
echo ""
echo "For support, contact your development team."