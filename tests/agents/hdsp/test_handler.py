"""
Unit Tests for HDSP Agent Detection Handler.

Tests for HDSP Detection Handler Lambda implementation.
"""

import os
import pytest
from unittest.mock import patch

# Set test environment before imports
os.environ["PROMETHEUS_MOCK"] = "true"
os.environ["AWS_MOCK"] = "true"
os.environ["AWS_PROVIDER"] = "mock"
os.environ["LLM_PROVIDER"] = "mock"

# Handler tests require langchain_core - check for availability
try:
    from langchain_core.messages import BaseMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


@pytest.mark.skipif(not LANGCHAIN_AVAILABLE, reason="langchain_core not installed")
class TestHDSPDetectionHandler:
    """Test suite for HDSP Detection Handler."""

    def test_handler_creation(self):
        """Test HDSPDetectionHandler creation."""
        from src.agents.hdsp.handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        assert handler.prometheus_client is not None
        assert handler.detector is not None

    def test_process_full_detection(self, lambda_context):
        """Test full detection processing."""
        from src.agents.hdsp.handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "all"}
        result = handler.process(event, lambda_context)

        assert "detection_type" in result
        assert result["detection_type"] == "all"
        assert "total_anomalies" in result
        assert "severity_breakdown" in result

    def test_process_pod_failure_only(self, lambda_context):
        """Test pod failure only detection."""
        from src.agents.hdsp.handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "pod_failure"}
        result = handler.process(event, lambda_context)

        assert result["detection_type"] == "pod_failure"

    def test_process_node_pressure_only(self, lambda_context):
        """Test node pressure only detection."""
        from src.agents.hdsp.handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "node_pressure"}
        result = handler.process(event, lambda_context)

        assert result["detection_type"] == "node_pressure"

    def test_process_resource_only(self, lambda_context):
        """Test resource anomaly only detection."""
        from src.agents.hdsp.handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "resource"}
        result = handler.process(event, lambda_context)

        assert result["detection_type"] == "resource"

    def test_process_invalid_type(self, lambda_context):
        """Test invalid detection type."""
        from src.agents.hdsp.handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "invalid"}

        with pytest.raises(ValueError) as excinfo:
            handler.process(event, lambda_context)

        assert "Invalid detection_type" in str(excinfo.value)

    def test_lambda_entry_point(self, lambda_context):
        """Test Lambda entry point function."""
        from src.agents.hdsp.handler import handler

        event = {"body": '{"detection_type": "all"}'}
        result = handler(event, lambda_context)

        assert result["statusCode"] == 200
        assert "body" in result

    def test_handler_with_default_event(self, lambda_context):
        """Test handler with minimal event."""
        from src.agents.hdsp.handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        # Empty event should use defaults
        event = {}
        result = handler.process(event, lambda_context)

        assert result["detection_type"] == "all"
