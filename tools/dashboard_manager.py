#!/usr/bin/env python3
"""
Dashboard Manager

A tool to export dashboards from Grafana to the local repository
and import them from the local repository to Grafana.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3001")
GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_PASSWORD", "admin")
DASHBOARD_FILE = Path("grafana/dashboards/main_dashboard.json")


def get_auth() -> requests.auth.HTTPBasicAuth:
    """Get HTTP Basic Auth credentials."""
    return requests.auth.HTTPBasicAuth(GRAFANA_USER, GRAFANA_PASSWORD)


def export_dashboard(uid: str, output_file: Path) -> None:
    """Export a dashboard from Grafana to a JSON file."""
    print(f"Exporting dashboard {uid} from {GRAFANA_URL}...")
    
    response = requests.get(
        f"{GRAFANA_URL.rstrip('/')}/api/dashboards/uid/{uid}",
        auth=get_auth(),
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 404:
        print(f"Error: Dashboard with UID '{uid}' not found.")
        sys.exit(1)
        
    response.raise_for_status()
    data = response.json()
    
    dashboard = data.get("dashboard")
    if not dashboard:
        print("Error: No dashboard data found in response.")
        sys.exit(1)
        
    # Clean up metadata that shouldn't be version controlled
    keys_to_remove = ["id", "version", "iteration"]
    for key in keys_to_remove:
        dashboard.pop(key, None)
        
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(dashboard, f, indent=2)
        
    print(f"Successfully exported dashboard to {output_file}")


def import_dashboard(input_file: Path, overwrite: bool = False) -> None:
    """Import a dashboard from a JSON file to Grafana."""
    print(f"Importing dashboard from {input_file} to {GRAFANA_URL}...")
    
    if not input_file.exists():
        print(f"Error: File {input_file} not found.")
        sys.exit(1)
        
    with open(input_file, "r") as f:
        dashboard = json.load(f)
        
    payload = {
        "dashboard": dashboard,
        "overwrite": overwrite,
        "folderId": 0  # 0 is the General folder
    }
    
    response = requests.post(
        f"{GRAFANA_URL.rstrip('/')}/api/dashboards/db",
        auth=get_auth(),
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 412:
        print("Error: Dashboard already exists (Precondition Failed). Use --overwrite to update.")
        sys.exit(1)
        
    if not response.ok:
        print(f"Error importing dashboard: {response.status_code} - {response.text}")
        sys.exit(1)
        
    data = response.json()
    print(f"Successfully imported dashboard: {data.get('url')}")


def list_dashboards() -> None:
    """List available dashboards in Grafana."""
    response = requests.get(
        f"{GRAFANA_URL.rstrip('/')}/api/search",
        auth=get_auth(),
        headers={"Content-Type": "application/json"}
    )
    
    response.raise_for_status()
    dashboards = response.json()
    
    if not dashboards:
        print("No dashboards found.")
        return
        
    print(f"{'UID':<20} | {'Title'}")
    print("-" * 40)
    for db in dashboards:
        if db.get("type") == "dash-db":
            print(f"{db.get('uid'):<20} | {db.get('title')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Grafana dashboards")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--export", help="Export dashboard by UID", metavar="UID")
    group.add_argument("--import", dest="import_file", help="Import dashboard from file", nargs="?", const=str(DASHBOARD_FILE))
    group.add_argument("--list", action="store_true", help="List all dashboards")
    
    parser.add_argument("--file", help=f"Output/Input file path (default: {DASHBOARD_FILE})", default=DASHBOARD_FILE)
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing dashboard on import")
    
    args = parser.parse_args()
    
    try:
        if args.list:
            list_dashboards()
        elif args.export:
            export_dashboard(args.export, Path(args.file))
        elif args.import_file:
            path = Path(args.import_file) if args.import_file else Path(args.file)
            import_dashboard(path, args.overwrite)
            
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to Grafana at {GRAFANA_URL}. Is it running?")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
