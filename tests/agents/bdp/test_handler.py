"""
Unit Tests for BDP Agent Detection Handler.

Tests for BDP Agent Lambda handler implementation.
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from src.agents.bdp.handler import DetectionHandler, handler as detection_handler


class TestDetectionHandler:
    """Test suite for DetectionHandler."""

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
            return DetectionHandler()

    def test_handler_creation(self, handler):
        """Test DetectionHandler creation."""
        assert handler is not None
        assert handler.config["llm_provider"] == "mock"

    def test_validate_input_missing_type(self, handler):
        """Test validation with missing detection_type."""
        event = {"body": "{}"}
        error = handler._validate_input(event)

        assert error is not None
        assert "detection_type" in error

    def test_validate_input_invalid_type(self, handler):
        """Test validation with invalid detection_type."""
        event = {"body": json.dumps({"detection_type": "invalid_type"})}
        error = handler._validate_input(event)

        assert error is not None

    def test_validate_input_valid(self, handler):
        """Test validation with valid input."""
        event = {"body": json.dumps({"detection_type": "log_anomaly"})}
        error = handler._validate_input(event)

        assert error is None

    def test_detect_log_anomalies(self, handler):
        """Test log anomaly detection."""
        result = handler._detect_log_anomalies({
            "log_group": "/aws/lambda/test",
            "service_name": "test-service",
            "time_range_hours": 1,
        })

        # Result should have expected structure
        assert "anomalies_detected" in result

    def test_detect_cost_anomalies(self, handler):
        """Test cost anomaly detection."""
        result = handler._detect_cost_anomalies({"days": 7})

        assert "anomalies_detected" in result
        assert "services_analyzed" in result

    def test_handler_function(self, lambda_context):
        """Test Lambda handler function."""
        event = {
            "body": json.dumps({
                "detection_type": "scheduled",
                "services": [],
            })
        }

        with patch.dict(
            "os.environ",
            {"LLM_PROVIDER": "mock", "AWS_PROVIDER": "mock"},
        ):
            response = detection_handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["success"] is True
