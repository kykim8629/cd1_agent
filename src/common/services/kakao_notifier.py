"""
Kakao Talk Notification Service.

Sends anomaly detection alerts to KakaoTalk via "Send to Me" API.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class KakaoNotifier:
    """KakaoTalk notification service using 'Send to Me' API."""

    TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

    def __init__(
        self,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        """Initialize KakaoNotifier.

        Args:
            access_token: Kakao API access token
            refresh_token: Kakao API refresh token (for auto-refresh)
            client_id: Kakao REST API key
            client_secret: Kakao client secret
        """
        self.access_token = access_token or os.getenv("KAKAO_ACCESS_TOKEN")
        self.refresh_token = refresh_token or os.getenv("KAKAO_REFRESH_TOKEN")
        self.client_id = client_id or os.getenv("KAKAO_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("KAKAO_CLIENT_SECRET")

        if not self.access_token:
            raise ValueError("KAKAO_ACCESS_TOKEN is required")

    def _refresh_access_token(self) -> bool:
        """Refresh access token using refresh token.

        Returns:
            True if refresh succeeded, False otherwise
        """
        if not self.refresh_token or not self.client_id:
            logger.warning("Cannot refresh token: missing refresh_token or client_id")
            return False

        try:
            with httpx.Client() as client:
                data = {
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "refresh_token": self.refresh_token,
                }
                if self.client_secret:
                    data["client_secret"] = self.client_secret

                response = client.post(self.TOKEN_URL, data=data)
                result = response.json()

                if "access_token" in result:
                    self.access_token = result["access_token"]
                    if "refresh_token" in result:
                        self.refresh_token = result["refresh_token"]
                    logger.info("Access token refreshed successfully")
                    return True
                else:
                    logger.error(f"Token refresh failed: {result}")
                    return False
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False

    def send_text(self, text: str, link_url: Optional[str] = None) -> bool:
        """Send text message to KakaoTalk.

        Args:
            text: Message text (max 200 chars)
            link_url: Optional link URL

        Returns:
            True if sent successfully, False otherwise
        """
        template = {
            "object_type": "text",
            "text": text[:200],  # Kakao limit
            "link": {"web_url": link_url or "https://github.com/lks21c/cd1-agent"},
        }

        return self._send_message(template)

    def send_anomaly_alert(
        self,
        anomaly_type: str,
        service_name: str,
        severity: str,
        summary: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send anomaly alert to KakaoTalk.

        Args:
            anomaly_type: Type of anomaly (log_anomaly, metric_anomaly, pattern_anomaly)
            service_name: Affected service name
            severity: Severity level (critical, high, medium, low)
            summary: Brief summary of the anomaly
            details: Additional details

        Returns:
            True if sent successfully, False otherwise
        """
        # Severity emoji
        severity_emoji = {
            "critical": "\U0001F6A8",  # 🚨
            "high": "\U0001F534",      # 🔴
            "medium": "\U0001F7E0",    # 🟠
            "low": "\U0001F7E1",       # 🟡
        }.get(severity.lower(), "\U00002753")  # ❓

        # Format message
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        text = f"{severity_emoji} [{severity.upper()}] CD1 Alert\n\n"
        text += f"Service: {service_name}\n"
        text += f"Type: {anomaly_type}\n"
        text += f"Time: {timestamp}\n\n"
        text += f"{summary[:100]}"

        return self.send_text(text)

    def send_detection_result(self, result: Dict[str, Any]) -> bool:
        """Send detection result summary to KakaoTalk.

        Args:
            result: Detection result from BDP agent

        Returns:
            True if sent successfully, False otherwise
        """
        total_anomalies = result.get("total_anomalies", 0)

        if total_anomalies == 0:
            # No anomalies - optional: skip notification
            return True

        # Build summary
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        text = f"\U0001F6A8 [CD1 Agent] Anomaly Detected!\n\n"
        text += f"Total: {total_anomalies} anomalies\n"
        text += f"Time: {timestamp}\n\n"

        # Log detection summary
        log_detection = result.get("log_detection", {})
        for service, data in log_detection.items():
            if data.get("anomalies_detected"):
                count = data.get("anomaly_count", 0)
                text += f"\U0001F4DD Log: {service} ({count})\n"

        # Pattern detection summary
        pattern_detection = result.get("pattern_detection", {})
        if pattern_detection.get("anomalies_detected"):
            records = pattern_detection.get("anomaly_records", [])
            for record in records[:3]:  # Top 3
                name = record.get("pattern_name", "unknown")
                sev = record.get("severity", "medium")
                emoji = "\U0001F534" if sev in ("critical", "high") else "\U0001F7E0"
                text += f"{emoji} {name}\n"

        return self.send_text(text[:200])

    def _send_message(self, template: Dict[str, Any]) -> bool:
        """Send message using Kakao API.

        Args:
            template: Message template object

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            with httpx.Client() as client:
                response = client.post(
                    self.SEND_URL,
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"template_object": json.dumps(template)},
                )

                result = response.json()

                if result.get("result_code") == 0:
                    logger.info("KakaoTalk message sent successfully")
                    return True
                elif result.get("code") == -401:
                    # Token expired - try refresh
                    logger.warning("Access token expired, attempting refresh...")
                    if self._refresh_access_token():
                        return self._send_message(template)
                    return False
                else:
                    logger.error(f"KakaoTalk send failed: {result}")
                    return False

        except Exception as e:
            logger.error(f"KakaoTalk send error: {e}")
            return False


# Convenience function for quick alerts
def send_kakao_alert(
    message: str,
    access_token: Optional[str] = None,
) -> bool:
    """Send a quick alert to KakaoTalk.

    Args:
        message: Alert message
        access_token: Optional access token (uses env var if not provided)

    Returns:
        True if sent successfully
    """
    try:
        notifier = KakaoNotifier(access_token=access_token)
        return notifier.send_text(message)
    except Exception as e:
        logger.error(f"Failed to send Kakao alert: {e}")
        return False
