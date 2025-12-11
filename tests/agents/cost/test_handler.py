"""
Unit Tests for Cost Agent Detection Handler.

Tests for Cost Detection Handler Lambda implementation.
"""

import pytest
import json
from unittest.mock import patch


class TestCostDetectionHandler:
    """Test suite for Cost Detection Handler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "mock",
                "AWS_PROVIDER": "mock",
            },
        ):
            from src.agents.cost.handler import CostDetectionHandler
            return CostDetectionHandler()

    def test_handler_creation(self, handler):
        """Test CostDetectionHandler creation."""
        assert handler is not None
        assert handler.cost_client is not None
        assert handler.detector is not None

    def test_process_cost_detection(self, handler, lambda_context):
        """Test cost detection processing."""
        event = {"days": 7}
        result = handler.process(event, lambda_context)

        assert "anomalies_detected" in result
        assert "services_analyzed" in result

    def test_process_with_custom_days(self, handler, lambda_context):
        """Test cost detection with custom days parameter."""
        event = {"days": 14}
        result = handler.process(event, lambda_context)

        assert "anomalies_detected" in result

    def test_lambda_entry_point(self, lambda_context):
        """Test Lambda entry point function."""
        with patch.dict(
            "os.environ",
            {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"},
        ):
            from src.agents.cost.handler import handler

            event = {"body": '{"days": 7}'}
            result = handler(event, lambda_context)

            assert result["statusCode"] == 200
            assert "body" in result

    def test_handler_with_default_event(self, handler, lambda_context):
        """Test handler with minimal event."""
        # Empty event should use defaults
        event = {}
        result = handler.process(event, lambda_context)

        assert "anomalies_detected" in result
