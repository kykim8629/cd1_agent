"""Tests for EMR Batch Agent Lambda handler."""

import os
import pytest
from src.agents.emr.handler import lambda_handler, reset_controller


@pytest.fixture(autouse=True)
def mock_mode():
    """Enable mock mode and reset controller for each test."""
    os.environ["AWS_MOCK"] = "true"
    reset_controller()  # Fresh controller for each test
    yield
    reset_controller()
    os.environ.pop("AWS_MOCK", None)


class TestLambdaHandler:
    """Tests for lambda_handler function."""

    def test_acquire_success(self):
        """Acquire action succeeds with valid input."""
        result = lambda_handler(
            {
                "action": "acquire",
                "dag_id": "batch_001",
                "dag_run_id": "batch_001_2024-01-25T00:05:00",
                "src_db_id": 4,
                "parallel_hint": 8,
                "table_name": "SALES_ORDER",
            },
            None,
        )

        assert result["allowed"] is True
        assert result["current_usage"] == 8

    def test_acquire_with_hint_string(self):
        """Acquire parses hint string correctly."""
        result = lambda_handler(
            {
                "action": "acquire",
                "dag_id": "batch_002",
                "dag_run_id": "batch_002_2024-01-25T00:05:00",
                "src_db_id": 4,
                "parallel_hint": "/*+ PARALLEL(16) FULL(A) */",
                "table_name": "ORDERS",
            },
            None,
        )

        assert result["allowed"] is True
        assert result["current_usage"] == 16

    def test_acquire_missing_fields(self):
        """Acquire returns error for missing fields."""
        result = lambda_handler(
            {
                "action": "acquire",
                "dag_id": "batch_001",
                # missing dag_run_id and src_db_id
            },
            None,
        )

        assert "error" in result
        assert "required" in result

    def test_release_success(self):
        """Release action succeeds."""
        # First acquire
        lambda_handler(
            {
                "action": "acquire",
                "dag_id": "batch_001",
                "dag_run_id": "batch_001_run",
                "src_db_id": 4,
                "parallel_hint": 8,
            },
            None,
        )

        # Then release
        result = lambda_handler(
            {
                "action": "release",
                "dag_run_id": "batch_001_run",
                "src_db_id": 4,
            },
            None,
        )

        assert result["released"] is True
        assert result["released_connections"] == 8

    def test_release_not_found(self):
        """Release returns error for unknown batch."""
        result = lambda_handler(
            {
                "action": "release",
                "dag_run_id": "unknown_run",
                "src_db_id": 4,
            },
            None,
        )

        assert result["released"] is False
        assert "error" in result

    def test_status_action(self):
        """Status action returns summary."""
        # Add some batches first
        for i in range(3):
            lambda_handler(
                {
                    "action": "acquire",
                    "dag_id": f"batch_{i:03d}",
                    "dag_run_id": f"batch_{i:03d}_run",
                    "src_db_id": 4,
                    "parallel_hint": 10,
                },
                None,
            )

        result = lambda_handler({"action": "status"}, None)

        assert "sources" in result
        assert "timestamp" in result
        assert result["sources"]["4"]["current_usage"] == 30

    def test_unknown_action(self):
        """Unknown action returns error."""
        result = lambda_handler({"action": "unknown"}, None)

        assert "error" in result
        assert "valid_actions" in result

    def test_default_action_is_status(self):
        """No action defaults to status."""
        result = lambda_handler({}, None)

        assert "sources" in result


class TestFullWorkflow:
    """Integration tests for full acquire-release workflow."""

    def test_multiple_batches_workflow(self):
        """Multiple batches acquire and release correctly."""
        # Acquire 5 batches
        for i in range(5):
            result = lambda_handler(
                {
                    "action": "acquire",
                    "dag_id": f"batch_{i:03d}",
                    "dag_run_id": f"batch_{i:03d}_run",
                    "src_db_id": 4,
                    "parallel_hint": 10,
                },
                None,
            )
            assert result["allowed"] is True

        # Check status
        status = lambda_handler({"action": "status"}, None)
        assert status["sources"]["4"]["current_usage"] == 50
        assert status["sources"]["4"]["active_batches"] == 5

        # Release 3 batches
        for i in range(3):
            result = lambda_handler(
                {
                    "action": "release",
                    "dag_run_id": f"batch_{i:03d}_run",
                    "src_db_id": 4,
                },
                None,
            )
            assert result["released"] is True

        # Check status again
        status = lambda_handler({"action": "status"}, None)
        assert status["sources"]["4"]["current_usage"] == 20
        assert status["sources"]["4"]["active_batches"] == 2

    def test_downgrade_workflow(self):
        """Batch gets downgraded when capacity limited."""
        # Fill up most capacity (900 connections)
        for i in range(90):
            lambda_handler(
                {
                    "action": "acquire",
                    "dag_id": f"filler_{i:03d}",
                    "dag_run_id": f"filler_{i:03d}_run",
                    "src_db_id": 4,
                    "parallel_hint": 10,
                },
                None,
            )

        # Check current usage
        status = lambda_handler({"action": "status"}, None)
        assert status["sources"]["4"]["current_usage"] == 900

        # Request large parallel - should be downgraded
        # Available: 950 - 900 = 50, request 64
        result = lambda_handler(
            {
                "action": "acquire",
                "dag_id": "large_batch",
                "dag_run_id": "large_batch_run",
                "src_db_id": 4,
                "parallel_hint": 64,
            },
            None,
        )

        assert result["allowed"] is True
        assert result.get("downgraded") is True
        assert result["adjusted_parallel"] < 64
        assert result["adjusted_parallel"] <= 50  # Must fit in available space

    def test_wait_when_full(self):
        """Batch waits when capacity exhausted."""
        # Fill up capacity (950 connections - threshold)
        for i in range(95):
            lambda_handler(
                {
                    "action": "acquire",
                    "dag_id": f"filler_{i:03d}",
                    "dag_run_id": f"filler_{i:03d}_run",
                    "src_db_id": 4,
                    "parallel_hint": 10,
                },
                None,
            )

        # Check current usage
        status = lambda_handler({"action": "status"}, None)
        assert status["sources"]["4"]["current_usage"] == 950

        # Request when no capacity - should wait
        result = lambda_handler(
            {
                "action": "acquire",
                "dag_id": "blocked_batch",
                "dag_run_id": "blocked_batch_run",
                "src_db_id": 4,
                "parallel_hint": 8,
            },
            None,
        )

        assert result["allowed"] is False
        assert result["wait_seconds"] > 0
        assert result["reason"] == "connection_limit_exceeded"
