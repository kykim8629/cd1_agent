#!/usr/bin/env python3
"""
Run MWAA Cluster Monitor with KakaoTalk Alert.

Usage:
    export KAKAO_ACCESS_TOKEN="your_access_token"
    python scripts/run_mwaa_monitor.py

    # Simulate issues
    python scripts/run_mwaa_monitor.py --simulate-issues

    # Healthy check (no simulated issues)
    python scripts/run_mwaa_monitor.py --healthy
"""

import argparse
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.mwaa.mock_mwaa_monitor import run_mwaa_health_check
from src.common.services.kakao_notifier import KakaoNotifier


def format_kakao_message(result: dict) -> str:
    """Format MWAA health check result for KakaoTalk.

    Args:
        result: Health check result dictionary

    Returns:
        Formatted message string
    """
    # Severity emoji
    severity_emoji = {
        "critical": "\U0001F6A8",  # 🚨
        "high": "\U0001F534",      # 🔴
        "medium": "\U0001F7E0",    # 🟠
        "low": "\U0001F7E2",       # 🟢
    }.get(result["severity"], "\U00002753")

    # Status emoji
    status_emoji = "\U00002705" if result["is_healthy"] else "\U0000274C"  # ✅ or ❌

    msg = f"{severity_emoji} [MWAA] {result['environment_name']}\n\n"
    msg += f"Status: {status_emoji} {result['status']}\n"

    # Components
    components = result["components"]
    msg += f"Scheduler: {components['scheduler']}\n"
    msg += f"Worker: {components['worker']}\n"

    # Metrics
    metrics = result["metrics"]
    msg += f"\nTasks: {metrics['running_tasks']} running, {metrics['queued_tasks']} queued\n"

    # Issues
    if result["issues"]:
        msg += f"\n\U000026A0 Issues:\n"  # ⚠️
        for issue in result["issues"][:2]:  # Max 2 issues
            msg += f"- {issue[:50]}\n"

    return msg[:200]  # Kakao limit


def main():
    """Run MWAA health check and send KakaoTalk alert."""

    parser = argparse.ArgumentParser(description="MWAA Cluster Monitor with KakaoTalk Alert")
    parser.add_argument("--simulate-issues", action="store_true", default=True,
                        help="Simulate random issues (default: True)")
    parser.add_argument("--healthy", action="store_true",
                        help="Run healthy check without simulated issues")
    parser.add_argument("--env-name", default="cd1-airflow-prod",
                        help="MWAA environment name")
    args = parser.parse_args()

    # Check for Kakao token
    access_token = os.getenv("KAKAO_ACCESS_TOKEN")
    if not access_token:
        print("Error: KAKAO_ACCESS_TOKEN environment variable is required")
        sys.exit(1)

    simulate_issues = not args.healthy

    print("=" * 60)
    print("MWAA Cluster Monitor - KakaoTalk Alert")
    print("=" * 60)
    print(f"\nEnvironment: {args.env_name}")
    print(f"Simulate Issues: {simulate_issues}")

    # Run health check
    print("\n[1/2] Running MWAA health check...")
    result = run_mwaa_health_check(
        environment_name=args.env_name,
        simulate_issues=simulate_issues,
    )

    # Display results
    print(f"\n{'='*40}")
    print(f"Environment: {result['environment_name']}")
    print(f"Status: {result['status']}")
    print(f"Healthy: {result['is_healthy']}")
    print(f"Severity: {result['severity']}")
    print(f"{'='*40}")

    print(f"\nComponents:")
    for comp, status in result["components"].items():
        emoji = "\U00002705" if status == "HEALTHY" else "\U0000274C"
        print(f"  {emoji} {comp}: {status}")

    print(f"\nMetrics:")
    print(f"  Running tasks: {result['metrics']['running_tasks']}")
    print(f"  Queued tasks: {result['metrics']['queued_tasks']}")
    print(f"  Scheduler heartbeat: {result['metrics']['scheduler_heartbeat_seconds_ago']}s ago")

    print(f"\nDAGs:")
    print(f"  Total: {result['dags']['total']}")
    print(f"  Active: {result['dags']['active']}")
    print(f"  Failed (24h): {result['dags']['failed_24h']}")

    print(f"\nResources:")
    print(f"  Scheduler CPU: {result['resources']['scheduler_cpu_percent']}%")
    print(f"  Scheduler Memory: {result['resources']['scheduler_memory_percent']}%")
    print(f"  Worker CPU: {result['resources']['worker_cpu_percent']}%")
    print(f"  Worker Memory: {result['resources']['worker_memory_percent']}%")

    if result["issues"]:
        print(f"\n\U000026A0 Issues:")
        for issue in result["issues"]:
            print(f"  - {issue}")

    if result["failed_dags"]:
        print(f"\nFailed DAGs:")
        for dag in result["failed_dags"]:
            print(f"  - {dag['dag_id']}")

    # Send KakaoTalk alert
    print(f"\n[2/2] Sending KakaoTalk alert...")

    notifier = KakaoNotifier(access_token=access_token)
    message = format_kakao_message(result)

    success = notifier.send_text(message)

    if success:
        print("  KakaoTalk alert sent successfully!")
    else:
        print("  Failed to send KakaoTalk alert")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)

    # Return result for programmatic use
    return result


if __name__ == "__main__":
    main()
