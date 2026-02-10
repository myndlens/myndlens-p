#!/usr/bin/env python3
"""MyndLens DAI Deployment Script.

Submits a deploy request to ObeGee's Deployment Authority Interface.
Per Dev Agent Contract: MyndLens may ONLY request deploys. ObeGee executes.

Usage:
    python deploy.py --env staging --tag gitsha-abc123 --reason "release v0.2.0"
    python deploy.py --env prod --tag gitsha-abc123 --reason "promote staging"
    python deploy.py --status <deploy_id>
    python deploy.py --rollback --env staging --reason "revert bad deploy"
"""
import argparse
import json
import sys

try:
    import requests
except ImportError:
    import urllib.request
    import urllib.error

DAI_BASE = "http://178.62.42.175:8001/internal/myndlens"
API_KEY = "obegee_internal_production_key_2026"


def deploy(env: str, tag: str, reason: str):
    """Submit deploy request."""
    if env == "prod":
        print("WARNING: Production deploy. Ensure staging passed first.")
        confirm = input("Type 'yes' to confirm: ")
        if confirm != "yes":
            print("Aborted.")
            return

    payload = {
        "env": env,
        "image_tag": tag,
        "reason": reason,
        "requested_by": "myndlens_ci",
    }

    print(f"Submitting deploy: env={env} tag={tag}")
    resp = _post(f"{DAI_BASE}/deploy", payload)
    print(json.dumps(resp, indent=2))


def status(deploy_id: str):
    """Check deploy status."""
    resp = _get(f"{DAI_BASE}/deploy/{deploy_id}")
    print(json.dumps(resp, indent=2))


def rollback(env: str, reason: str):
    """Request rollback."""
    payload = {
        "env": env,
        "reason": reason,
        "requested_by": "myndlens_ci",
    }
    print(f"Requesting rollback: env={env}")
    resp = _post(f"{DAI_BASE}/rollback", payload)
    print(json.dumps(resp, indent=2))


def _post(url, payload):
    try:
        import requests
        r = requests.post(url, json=payload, headers={"X-Internal-API-Key": API_KEY}, timeout=30)
        return r.json()
    except Exception:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "X-Internal-API-Key": API_KEY},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())


def _get(url):
    try:
        import requests
        r = requests.get(url, headers={"X-Internal-API-Key": API_KEY}, timeout=30)
        return r.json()
    except Exception:
        req = urllib.request.Request(url, headers={"X-Internal-API-Key": API_KEY})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MyndLens DAI Deploy")
    parser.add_argument("--env", choices=["staging", "prod"], help="Target environment")
    parser.add_argument("--tag", help="Docker image tag (e.g., gitsha-abc123)")
    parser.add_argument("--reason", default="release", help="Deploy reason")
    parser.add_argument("--status", help="Check deploy status by ID")
    parser.add_argument("--rollback", action="store_true", help="Request rollback")
    args = parser.parse_args()

    if args.status:
        status(args.status)
    elif args.rollback:
        if not args.env:
            print("--env required for rollback")
            sys.exit(1)
        rollback(args.env, args.reason)
    elif args.env and args.tag:
        deploy(args.env, args.tag, args.reason)
    else:
        parser.print_help()
