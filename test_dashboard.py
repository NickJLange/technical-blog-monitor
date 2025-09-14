#!/usr/bin/env python3
"""
Test script to run the web dashboard for the technical blog monitor.
"""
import asyncio
import sys
import uvicorn
from pathlib import Path

# Add the project root to the Python path if needed
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from monitor.web.app import create_app
from monitor.config import load_settings

def main():
    """Run the web dashboard."""
    print("🚀 Starting Technical Blog Monitor Dashboard...")
    print("=" * 50)
    
    try:
        # Try to load settings, but continue even if it fails
        settings = None
        try:
            settings = load_settings()
            print("✅ Loaded configuration from .env")
        except Exception as e:
            print(f"⚠️  Could not load settings: {e}")
            print("   Using mock data for demo")
    
        # Create the FastAPI app
        app = create_app(settings)
        
        # Run the server
        print("\n📊 Dashboard starting on http://localhost:8080")
        print("   Open your browser to view the dashboard")
        print("   Press Ctrl+C to stop\n")
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8080,
            log_level="info",
            access_log=True
        )
    
    except KeyboardInterrupt:
        print("\n\n👋 Dashboard stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())