"""
Chat Tools - 대화형 에이전트용 Tool 래퍼.
"""

from typing import Callable, Dict

from src.services.aws_client import AWSClient
from src.chat.tools.cloudwatch import (
    get_cloudwatch_metrics,
    query_cloudwatch_logs,
    create_cloudwatch_tools,
)
from src.chat.tools.service_health import (
    get_service_health,
    check_recent_deployments,
    create_service_health_tools,
)
from src.chat.tools.prometheus import (
    get_prometheus_metrics,
    get_pod_status,
    create_prometheus_tools,
)


def create_chat_tools(aws_client: AWSClient) -> Dict[str, Callable]:
    """
    Chat 에이전트용 전체 Tool 세트 생성.

    Args:
        aws_client: AWS 클라이언트

    Returns:
        Tool 딕셔너리
    """
    tools = {}

    # CloudWatch Tools
    tools.update(create_cloudwatch_tools(aws_client))

    # Service Health Tools
    tools.update(create_service_health_tools(aws_client))

    # Prometheus Tools (Mock)
    tools.update(create_prometheus_tools())

    return tools


__all__ = [
    "create_chat_tools",
    "get_cloudwatch_metrics",
    "query_cloudwatch_logs",
    "get_service_health",
    "check_recent_deployments",
    "get_prometheus_metrics",
    "get_pod_status",
]
