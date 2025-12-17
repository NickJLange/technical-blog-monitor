#!/usr/bin/env python3
"""Run the web dashboard on an available port."""
import asyncio
import sys
import uvicorn
from pathlib import Path
import socket

sys.path.insert(0, str(Path(__file__).parent))

from monitor.web.app import create_app
from monitor.config import load_settings

def find_available_port(start_port=8080, max_attempts=10):
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            continue
    return None

def main():
    """Run the web dashboard."""
    print("🚀 Starting Technical Blog Monitor Dashboard...")
    print("=" * 50)
    
    try:
        settings = load_settings()
        print("✅ Loaded configuration from .env")
        
        app = create_app(settings)
        
        # Find available port
        port = find_available_port(8080)
        if not port:
            print("❌ No available ports found (tried 8080-8089)")
            return 1
        
        print(f"\n📊 Dashboard starting on http://localhost:{port}")
        print("   Open your browser to view the dashboard")
        print("   Press Ctrl+C to stop\n")
        
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="info",
            access_log=True
        )
    
    except KeyboardInterrupt:
        print("\n\n👋 Dashboard stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
