
import requests
import sys
import time
import subprocess
import os
import signal

def verify_metrics():
    # Set env var to enable prometheus
    env = os.environ.copy()
    env["METRICS__PROMETHEUS_ENABLED"] = "true"
    env["METRICS__PROMETHEUS_PORT"] = "8000"
    
    # Start monitor in background (run_once mode might not keep server alive long enough, 
    # but run_daemon does. We'll use run_daemon and kill it shortly).
    # Wait, run_daemon blocks.
    
    print("🚀 Starting monitor with metrics enabled...")
    process = subprocess.Popen(
        ["uv", "run", "python", "-m", "monitor.main"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    print("⏳ Waiting for server to start...")
    time.sleep(5)
    
    try:
        print("🔍 Checking metrics endpoint...")
        response = requests.get("http://localhost:8000/metrics")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Metrics endpoint is UP!")
            print(f"Content length: {len(response.text)}")
            print("Sample metrics:")
            print("\n".join(response.text.split("\n")[:5]))
            return True
        else:
            print(f"❌ Metrics endpoint returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return False
        
    finally:
        print("🛑 Stopping monitor...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

if __name__ == "__main__":
    if verify_metrics():
        sys.exit(0)
    else:
        sys.exit(1)
