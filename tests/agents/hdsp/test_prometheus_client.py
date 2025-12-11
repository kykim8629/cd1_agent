"""
Unit Tests for HDSP Prometheus Client.

Tests for Prometheus client and providers.
"""

import os
import pytest
from datetime import datetime, timedelta

# Set test environment before imports
os.environ["PROMETHEUS_MOCK"] = "true"

from src.agents.hdsp.services.prometheus_client import (
    PrometheusClient,
    PrometheusProvider,
    PrometheusQueryResult,
    RealPrometheusProvider,
    MockPrometheusProvider,
)


class TestPrometheusQueryResult:
    """Test suite for PrometheusQueryResult."""

    def test_creation(self):
        """Test PrometheusQueryResult creation."""
        result = PrometheusQueryResult(
            metric_name="kube_pod_container_status_restarts_total",
            labels={"namespace": "default", "pod": "test-pod"},
            values=[(datetime.utcnow().timestamp(), 5.0)],
        )

        assert result.metric_name == "kube_pod_container_status_restarts_total"
        assert result.labels["namespace"] == "default"
        assert len(result.values) == 1

    def test_latest_value(self):
        """Test latest_value property."""
        now = datetime.utcnow().timestamp()
        result = PrometheusQueryResult(
            metric_name="test_metric",
            labels={},
            values=[
                (now - 60, 1.0),
                (now - 30, 2.0),
                (now, 3.0),
            ],
        )

        assert result.latest_value == 3.0

    def test_average_value(self):
        """Test average_value property."""
        now = datetime.utcnow().timestamp()
        result = PrometheusQueryResult(
            metric_name="test_metric",
            labels={},
            values=[
                (now - 60, 1.0),
                (now - 30, 2.0),
                (now, 3.0),
            ],
        )

        assert result.average_value == 2.0

    def test_empty_values(self):
        """Test with empty values."""
        result = PrometheusQueryResult(
            metric_name="test_metric",
            labels={},
            values=[],
        )

        assert result.latest_value is None
        assert result.average_value is None


class TestMockPrometheusProvider:
    """Test suite for MockPrometheusProvider."""

    def test_creation(self):
        """Test MockPrometheusProvider creation."""
        provider = MockPrometheusProvider()

        # Mock data is stored in _mock_data
        assert provider._mock_data is not None

    def test_query(self):
        """Test query method."""
        provider = MockPrometheusProvider()

        results = provider.query("kube_pod_container_status_restarts_total")

        assert len(results) > 0
        assert all(isinstance(r, PrometheusQueryResult) for r in results)

    def test_query_range(self):
        """Test query_range method."""
        provider = MockPrometheusProvider()

        end = datetime.utcnow()
        start = end - timedelta(hours=1)

        results = provider.query_range(
            "kube_pod_container_status_restarts_total",
            start=start,
            end=end,
            step="15s",
        )

        assert len(results) > 0

    def test_inject_anomaly(self):
        """Test anomaly injection."""
        provider = MockPrometheusProvider()

        # Use the actual inject_anomaly signature
        provider.inject_anomaly(
            anomaly_type="crash_loop",
            namespace="test-ns",
            pod="injected-pod",
        )

        results = provider.query("kube_pod_container_status_waiting_reason")

        # Should include the injected anomaly
        injected = [r for r in results if r.labels.get("pod") == "injected-pod"]
        assert len(injected) == 1
        assert injected[0].latest_value == 1.0


class TestPrometheusClient:
    """Test suite for PrometheusClient."""

    def test_mock_mode_detection(self):
        """Test automatic mock mode detection."""
        client = PrometheusClient()

        # Should be in mock mode due to environment variable
        assert client.provider_type == PrometheusProvider.MOCK

    def test_get_pod_restarts(self):
        """Test get_pod_restarts method."""
        client = PrometheusClient()

        # Use single namespace (not list)
        results = client.get_pod_restarts(namespace="default")

        assert isinstance(results, list)
        for result in results:
            assert isinstance(result, PrometheusQueryResult)

    def test_get_crash_loop_pods(self):
        """Test get_crash_loop_pods method."""
        client = PrometheusClient()

        # Use single namespace (not list)
        results = client.get_crash_loop_pods(namespace="spark")

        assert isinstance(results, list)

    def test_get_oom_killed_pods(self):
        """Test get_oom_killed_pods method."""
        client = PrometheusClient()

        # Use single namespace
        results = client.get_oom_killed_pods(namespace="hdsp")

        assert isinstance(results, list)

    def test_get_node_conditions(self):
        """Test get_node_conditions method."""
        client = PrometheusClient()

        results = client.get_node_conditions()

        assert isinstance(results, list)
        # Should have some node condition results
        assert len(results) > 0

    def test_get_high_cpu_pods(self):
        """Test get_high_cpu_pods method."""
        client = PrometheusClient()

        # Use single namespace
        results = client.get_high_cpu_pods(namespace="default", threshold=0.9)

        assert isinstance(results, list)

    def test_get_high_memory_pods(self):
        """Test get_high_memory_pods method."""
        client = PrometheusClient()

        # Use single namespace
        results = client.get_high_memory_pods(namespace="default", threshold=0.85)

        assert isinstance(results, list)
