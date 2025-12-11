"""
Unit Tests for Drift Agent Detection Handler.

Tests for Drift Detection Handler Lambda implementation.
"""

import pytest
import json
from unittest.mock import patch


class TestDriftDetectionHandler:
    """Test suite for Drift Detection Handler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "mock",
                "AWS_PROVIDER": "mock",
                "GITLAB_TOKEN": "mock-token",
            },
        ):
            from src.agents.drift.handler import DriftDetectionHandler
            return DriftDetectionHandler()

    def test_handler_creation(self, handler):
        """Test DriftDetectionHandler creation."""
        assert handler is not None

    def test_process_drift_detection(self, handler, lambda_context):
        """Test drift detection processing."""
        event = {
            "config_type": "all",
            "services": [],
        }
        result = handler.process(event, lambda_context)

        assert "drifts_detected" in result or "status" in result

    def test_lambda_entry_point(self, lambda_context):
        """Test Lambda entry point function."""
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "mock",
                "AWS_PROVIDER": "mock",
                "GITLAB_TOKEN": "mock-token",
            },
        ):
            from src.agents.drift.handler import handler

            event = {"body": '{"config_type": "all"}'}
            result = handler(event, lambda_context)

            assert result["statusCode"] == 200
            assert "body" in result

    def test_handler_with_default_event(self, handler, lambda_context):
        """Test handler with minimal event."""
        # Empty event should use defaults
        event = {}
        result = handler.process(event, lambda_context)

        # Should have some result structure
        assert isinstance(result, dict)
