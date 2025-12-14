#!/bin/bash
# Run the Technical Blog Monitor Dashboard

echo "🚀 Starting Technical Blog Monitor Dashboard..."
echo "=================================================="

# Ensure we are running from the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Check if uv is installed
if ! command -v uv &> /dev/null
then
    echo "uv could not be found, please install it"
    exit
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Run the dashboard
echo ""
echo "📊 Dashboard starting on http://localhost:8080"
echo "   Open your browser to view the dashboard"
echo "   Press Ctrl+C to stop"
echo ""

export PYTHONPATH=.
python monitor/dashboard.py
