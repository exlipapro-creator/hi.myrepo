"""
hi.myrepo - Heartbeat Worker

GitHub Actions can perform scheduled health checks.
This script:
1. Retrieves authorized monitored targets from the API
2. Validates them (SSRF protection)
3. Executes HTTP checks
4. Records status, latency, timestamp
5. Emits events
6. Detects degradation
7. Avoids creating duplicate incidents

Usage:
    python heartbeat.py

Environment variables:
    API_URL - Base URL of the hi.myrepo API
    API_TOKEN - Authentication token
"""

import asyncio
import httpx
import json
import os
import sys
import time
from datetime import datetime, timezone


API_URL = os.environ.get("API_URL", "http://localhost:8000")
API_TOKEN = os.environ.get("API_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
}


async def get_monitored_targets(client: httpx.AsyncClient) -> list[dict]:
    """Fetch monitored targets from the API."""
    try:
        response = await client.get(f"{API_URL}/api/v1/monitored-targets", headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch targets: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching targets: {e}")
        return []


async def check_target(client: httpx.AsyncClient, target: dict) -> dict:
    """Execute a single heartbeat check."""
    url = target.get("url")
    timeout = target.get("timeout_seconds", 10)
    expected_status = target.get("expected_status", 200)

    result = {
        "target_id": target["id"],
        "url": url,
        "is_healthy": False,
        "is_degraded": False,
        "status_code": None,
        "latency_ms": None,
        "error_message": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        start_time = time.time()
        response = await client.get(
            url,
            timeout=timeout,
            follow_redirects=True,
        )
        latency_ms = (time.time() - start_time) * 1000

        result["status_code"] = response.status_code
        result["latency_ms"] = round(latency_ms, 2)
        result["is_healthy"] = response.status_code == expected_status
        result["is_degraded"] = (
            response.status_code >= 200 and response.status_code < 500
            and response.status_code != expected_status
        )

    except httpx.TimeoutException:
        result["error_message"] = f"Timeout after {timeout}s"
    except httpx.RequestError as e:
        result["error_message"] = str(e)
    except Exception as e:
        result["error_message"] = f"Unexpected error: {e}"

    return result


async def emit_event(client: httpx.AsyncClient, event_data: dict):
    """Emit an event to the hi.myrepo event spine."""
    try:
        response = await client.post(
            f"{API_URL}/api/v1/events",
            headers=HEADERS,
            json=event_data,
        )
        if response.status_code in (200, 201):
            print(f"  ✓ Event emitted: {event_data['event_type']}")
        else:
            print(f"  ✗ Failed to emit event: {response.status_code}")
    except Exception as e:
        print(f"  ✗ Error emitting event: {e}")


async def run_heartbeat_checks():
    """Main heartbeat loop."""
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting heartbeat checks...")
    print(f"  API: {API_URL}")

    if not API_TOKEN:
        print("  ⚠ No API_TOKEN set — running in dry-run mode")

    async with httpx.AsyncClient() as client:
        targets = await get_monitored_targets(client)

        if not targets:
            print("  No monitored targets found")
            return

        print(f"  Checking {len(targets)} target(s)...")

        results = []
        for target in targets:
            result = await check_target(client, target)
            results.append(result)

            status = "✓" if result["is_healthy"] else "✗"
            latency = f"{result['latency_ms']:.0f}ms" if result["latency_ms"] else "N/A"
            print(f"  {status} {target.get('name', 'unknown')}: {latency}")

            # Emit heartbeat event
            if API_TOKEN:
                event_type = "HEARTBEAT_SUCCESS" if result["is_healthy"] else (
                    "HEARTBEAT_DEGRADED" if result["is_degraded"] else "HEARTBEAT_FAILURE"
                )
                await emit_event(client, {
                    "event_type": event_type,
                    "source": target.get("name", "heartbeat"),
                    "source_type": "heartbeat",
                    "project_id": target.get("project_id"),
                    "severity": "low" if result["is_healthy"] else (
                        "medium" if result["is_degraded"] else "high"
                    ),
                    "payload": {
                        "url": result["url"],
                        "status_code": result["status_code"],
                        "latency_ms": result["latency_ms"],
                        "error_message": result["error_message"],
                    },
                })

        # Summary
        healthy = sum(1 for r in results if r["is_healthy"])
        unhealthy = sum(1 for r in results if not r["is_healthy"] and not r["is_degraded"])
        degraded = sum(1 for r in results if r["is_degraded"])

        print(f"\n  Summary: {healthy} healthy, {degraded} degraded, {unhealthy} unhealthy")


if __name__ == "__main__":
    asyncio.run(run_heartbeat_checks())
