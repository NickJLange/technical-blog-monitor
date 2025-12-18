#!/usr/bin/env python3
"""
Configure Prometheus Datasource

Authorizes with the standalone Grafana instance and configures
the Prometheus datasource pointing to the blog-monitor network.
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3001")
GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_PASSWORD", "admin")

DATASOURCE_PAYLOAD = {
    "name": "Prometheus",
    "type": "prometheus",
    "url": "http://blogmon-prometheus:9090",
    "access": "proxy",
    "isDefault": True,
    "jsonData": {
        "httpMethod": "POST"
    }
}

def configure_datasource():
    print(f"Configuring datasource at {GRAFANA_URL}...")
    auth = requests.auth.HTTPBasicAuth(GRAFANA_USER, GRAFANA_PASSWORD)
    
    # Check if exists first
    try:
        response = requests.get(
            f"{GRAFANA_URL.rstrip('/')}/api/datasources/name/Prometheus",
            auth=auth
        )
        if response.status_code == 200:
            print("Datasource 'Prometheus' already exists.")
            # Optionally update it
            ds_id = response.json().get("id")
            print(f"Updating datasource ID {ds_id}...")
            update_resp = requests.put(
                f"{GRAFANA_URL.rstrip('/')}/api/datasources/{ds_id}",
                auth=auth,
                json=DATASOURCE_PAYLOAD
            )
            update_resp.raise_for_status()
            print("Datasource updated successfully.")
            return

    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {GRAFANA_URL}. Is Grafana running?")
        sys.exit(1)

    # Create if not exists
    create_resp = requests.post(
        f"{GRAFANA_URL.rstrip('/')}/api/datasources",
        auth=auth,
        json=DATASOURCE_PAYLOAD
    )
    
    if create_resp.status_code == 409:
        print("Datasource already exists (Conflict).")
    elif not create_resp.ok:
        print(f"Failed to create datasource: {create_resp.status_code} - {create_resp.text}")
        sys.exit(1)
    else:
        print("Datasource 'Prometheus' created successfully.")

if __name__ == "__main__":
    configure_datasource()
