"""
Create an Omni dashboard from a prepared import payload.

Usage:
    python3 create_dashboard.py \
        --base-url https://yourcompany.omniapp.co \
        --api-key omni_osk_... \
        --model-id <shared-model-uuid> \
        --connection-id <connection-uuid> \
        --payload dashboard-payload.json \
        --name "Dashboard Name"

The payload JSON should follow the tile structure from templates/dashboard-payload.json.
This script injects the model ID, connection ID, and name, then posts to the import API.
"""

import argparse
import json
import os
import sys
import requests


def load_payload(payload_path):
    with open(payload_path, "r") as f:
        return json.load(f)


def inject_ids(payload, model_id, connection_id, name=None):
    payload["baseModelId"] = model_id
    payload["document"]["connectionId"] = connection_id
    payload["workbookModel"]["connection_id"] = connection_id
    payload["workbookModel"]["base_model_id"] = model_id

    if name:
        payload["dashboard"]["name"] = name
        payload["document"]["name"] = name

    return payload


def deploy(base_url, api_key, payload):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{base_url}/api/unstable/documents/import"
    resp = requests.post(url, headers=headers, json=payload)
    return resp


def main():
    parser = argparse.ArgumentParser(description="Deploy an Omni dashboard from a payload JSON.")
    parser.add_argument("--base-url", required=True, help="Omni base URL")
    parser.add_argument("--api-key", required=True, help="Omni API key")
    parser.add_argument("--model-id", required=True, help="Shared model UUID")
    parser.add_argument("--connection-id", required=True, help="Connection UUID")
    parser.add_argument("--payload", required=True, help="Path to dashboard payload JSON")
    parser.add_argument("--name", default=None, help="Override dashboard name")
    parser.add_argument("--output", default=None, help="Path to save API response JSON")
    args = parser.parse_args()

    payload = load_payload(args.payload)
    payload = inject_ids(payload, args.model_id, args.connection_id, args.name)

    print(f"Deploying dashboard to {args.base_url}...")
    resp = deploy(args.base_url, args.api_key, payload)

    if resp.status_code in (200, 201):
        result = resp.json()
        print(f"Success: {resp.status_code}")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Response saved to {args.output}")

        # Attempt to find and print dashboard URL
        try:
            from omni_python_sdk import OmniAPI
            api = OmniAPI(api_key=args.api_key, base_url=args.base_url)
            docs = api.list_documents()
            for r in docs.get("records", []):
                dash_name = args.name or payload.get("dashboard", {}).get("name", "")
                if dash_name and dash_name in r.get("name", ""):
                    print(f"Dashboard URL: {r['url']}")
                    break
        except ImportError:
            print("Install omni-python-sdk to auto-detect dashboard URL")

        return 0
    else:
        print(f"Failed: {resp.status_code}")
        print(resp.text[:3000])
        return 1


if __name__ == "__main__":
    sys.exit(main())
