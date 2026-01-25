#!/usr/bin/env python3
"""
Run BDP Agent with KakaoTalk Alert.

Usage:
    # Set environment variables
    export KAKAO_ACCESS_TOKEN="your_access_token"

    # Run
    python scripts/run_with_kakao_alert.py

    # Or with inline token
    KAKAO_ACCESS_TOKEN="xxx" python scripts/run_with_kakao_alert.py
"""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set mock providers if not specified
os.environ.setdefault("AWS_PROVIDER", "mock")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("RDS_PROVIDER", "mock")

from src.agents.bdp.handler import handler
from src.common.services.kakao_notifier import KakaoNotifier


def main():
    """Run BDP detection and send KakaoTalk alert."""

    # Check for Kakao token
    access_token = os.getenv("KAKAO_ACCESS_TOKEN")
    if not access_token:
        print("Error: KAKAO_ACCESS_TOKEN environment variable is required")
        print("\nUsage:")
        print('  export KAKAO_ACCESS_TOKEN="your_token"')
        print("  python scripts/run_with_kakao_alert.py")
        sys.exit(1)

    print("=" * 60)
    print("CD1 BDP Agent - Running with KakaoTalk Alert")
    print("=" * 60)

    # Run BDP detection
    print("\n[1/3] Running anomaly detection...")
    event = {"detection_type": "scheduled"}
    response = handler(event, None)

    # Parse response
    body = json.loads(response.get("body", "{}"))

    if not body.get("success"):
        print(f"Detection failed: {body.get('error')}")
        sys.exit(1)

    data = body.get("data", {})
    total_anomalies = data.get("total_anomalies", 0)

    print(f"\n[2/3] Detection complete!")
    print(f"  - Total anomalies: {total_anomalies}")

    # Show details
    log_detection = data.get("log_detection", {})
    for service, result in log_detection.items():
        if result.get("anomalies_detected"):
            print(f"  - Log anomaly in {service}: {result.get('anomaly_count', 0)} issues")

    pattern_detection = data.get("pattern_detection", {})
    if pattern_detection.get("anomalies_detected"):
        print(f"  - Pattern anomalies: {pattern_detection.get('anomaly_count', 0)} detected")
        for record in pattern_detection.get("anomaly_records", [])[:5]:
            print(f"    * {record.get('pattern_name')} ({record.get('severity')})")

    # Send KakaoTalk alert
    print(f"\n[3/3] Sending KakaoTalk alert...")

    notifier = KakaoNotifier(access_token=access_token)

    if total_anomalies > 0:
        success = notifier.send_detection_result(data)
    else:
        success = notifier.send_text(
            "CD1 Agent: No anomalies detected. All systems normal."
        )

    if success:
        print("  KakaoTalk alert sent successfully!")
    else:
        print("  Failed to send KakaoTalk alert")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
