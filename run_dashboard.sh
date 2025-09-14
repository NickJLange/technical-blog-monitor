#!/bin/bash
# Run the Technical Blog Monitor Dashboard

echo "🚀 Starting Technical Blog Monitor Dashboard..."
echo "=================================================="

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment and install dependencies if needed
source .venv/bin/activate

# Check if uvicorn is installed
if ! python -c "import uvicorn" 2>/dev/null; then
    echo "Installing dependencies..."
    uv pip install fastapi uvicorn jinja2 python-multipart structlog pydantic pydantic-settings
fi

# Run the dashboard
echo ""
echo "📊 Dashboard starting on http://localhost:8080"
echo "   Open your browser to view the dashboard"
echo "   Press Ctrl+C to stop"
echo ""

python test_dashboard.py