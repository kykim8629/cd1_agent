"""
EMR Batch Agent Lambda Handler.

Manages Oracle connection pool usage for batch jobs.

Actions:
- acquire: Request connection allocation before batch start
- release: Release connections after batch completion
- status: Get current connection usage status

Environment Variables:
- AWS_MOCK: Set to "true" for mock mode
- EMR_AGENT_TABLE_REGISTRY: DynamoDB registry table name
- EMR_AGENT_TABLE_LIMITS: DynamoDB limits table name
"""

import os
from typing import Any, Dict, Optional

from src.common.services.aws_client import AWSClient, AWSProvider
from src.agents.emr.services.admission_controller import AdmissionController
from src.agents.emr.services.hint_parser import parse_parallel_hint


# Module-level controller instance (singleton for Lambda warm starts)
_controller: Optional[AdmissionController] = None


def get_controller() -> AdmissionController:
    """Get or create the admission controller singleton."""
    global _controller

    if _controller is None:
        aws_client = get_aws_client()
        _controller = AdmissionController(aws_client)

    return _controller


def reset_controller() -> None:
    """Reset the controller (for testing)."""
    global _controller
    _controller = None


def get_aws_client() -> AWSClient:
    """Get AWS client based on environment."""
    if os.getenv("AWS_MOCK", "false").lower() == "true":
        return AWSClient(provider=AWSProvider.MOCK)
    return AWSClient(provider=AWSProvider.REAL)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    EMR Batch Agent Lambda handler.

    Args:
        event: Lambda event with action and parameters
        context: Lambda context (unused)

    Returns:
        Response dictionary based on action

    Event structure:
        {
            "action": "acquire" | "release" | "status",
            "dag_id": "batch_001",
            "dag_run_id": "batch_001_2024-01-25T00:05:00",
            "src_db_id": 4,
            "parallel_hint": 8,  # or hint string
            "table_name": "SALES_ORDER"
        }
    """
    action = event.get("action", "status")

    try:
        controller = get_controller()

        if action == "acquire":
            return handle_acquire(event, controller)
        elif action == "release":
            return handle_release(event, controller)
        elif action == "status":
            return handle_status(controller)
        else:
            return {
                "error": f"Unknown action: {action}",
                "valid_actions": ["acquire", "release", "status"],
            }

    except Exception as e:
        return {
            "error": str(e),
            "action": action,
        }


def handle_acquire(event: Dict[str, Any], controller: AdmissionController) -> Dict[str, Any]:
    """
    Handle acquire action.

    Required fields:
    - dag_id: DAG name
    - dag_run_id: DAG run ID
    - src_db_id: Source database ID

    Optional fields:
    - parallel_hint: Parallel degree (int) or hint string
    - table_name: Target table name
    """
    dag_id = event.get("dag_id")
    dag_run_id = event.get("dag_run_id")
    src_db_id = event.get("src_db_id")

    if not all([dag_id, dag_run_id, src_db_id]):
        return {
            "error": "Missing required fields",
            "required": ["dag_id", "dag_run_id", "src_db_id"],
        }

    # Parse parallel hint
    parallel_hint = event.get("parallel_hint", 8)
    if isinstance(parallel_hint, str):
        parallel_hint = parse_parallel_hint(parallel_hint)

    table_name = event.get("table_name", "unknown")

    result = controller.check_admission(
        src_db_id=int(src_db_id),
        dag_id=dag_id,
        dag_run_id=dag_run_id,
        table_name=table_name,
        parallel_hint=parallel_hint,
    )

    return result.to_response()


def handle_release(event: Dict[str, Any], controller: AdmissionController) -> Dict[str, Any]:
    """
    Handle release action.

    Required fields:
    - dag_run_id: DAG run ID
    - src_db_id: Source database ID
    """
    dag_run_id = event.get("dag_run_id")
    src_db_id = event.get("src_db_id")

    if not all([dag_run_id, src_db_id]):
        return {
            "error": "Missing required fields",
            "required": ["dag_run_id", "src_db_id"],
        }

    result = controller.release(
        src_db_id=int(src_db_id),
        dag_run_id=dag_run_id,
    )

    return result.to_response()


def handle_status(controller: AdmissionController) -> Dict[str, Any]:
    """Handle status action."""
    return controller.get_status()


# For local testing
if __name__ == "__main__":
    import json

    # Set mock mode
    os.environ["AWS_MOCK"] = "true"

    # Reset controller for clean test
    reset_controller()

    # Test acquire
    print("=== Test Acquire ===")
    result = lambda_handler(
        {
            "action": "acquire",
            "dag_id": "batch_001",
            "dag_run_id": "batch_001_2024-01-25T00:05:00",
            "src_db_id": 4,
            "parallel_hint": "/*+ PARALLEL(8) FULL(A) */",
            "table_name": "SALES_ORDER",
        },
        None,
    )
    print(json.dumps(result, indent=2))

    # Test status
    print("\n=== Test Status ===")
    result = lambda_handler({"action": "status"}, None)
    print(json.dumps(result, indent=2))

    # Test release
    print("\n=== Test Release ===")
    result = lambda_handler(
        {
            "action": "release",
            "dag_run_id": "batch_001_2024-01-25T00:05:00",
            "src_db_id": 4,
        },
        None,
    )
    print(json.dumps(result, indent=2))

    # Test status after release
    print("\n=== Test Status After Release ===")
    result = lambda_handler({"action": "status"}, None)
    print(json.dumps(result, indent=2))
