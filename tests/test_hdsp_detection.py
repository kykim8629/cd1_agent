"""
Unit Tests for HDSP Agent Components.

Tests for Prometheus client, HDSP anomaly detector, and detection handler.
"""

import os
import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

# Set test environment before imports
os.environ["PROMETHEUS_MOCK"] = "true"
os.environ["AWS_MOCK"] = "true"
os.environ["AWS_PROVIDER"] = "mock"
os.environ["LLM_PROVIDER"] = "mock"

from src.services.prometheus_client import (
    PrometheusClient,
    PrometheusProvider,
    PrometheusQueryResult,
    RealPrometheusProvider,
    MockPrometheusProvider,
)
from src.services.hdsp_anomaly_detector import (
    HDSPAnomalyDetector,
    HDSPAnomalyType,
    HDSPSeverity,
    HDSPAnomaly,
    HDSPDetectionResult,
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


class TestHDSPAnomaly:
    """Test suite for HDSPAnomaly dataclass."""

    def test_creation(self):
        """Test HDSPAnomaly creation."""
        anomaly = HDSPAnomaly(
            anomaly_type=HDSPAnomalyType.CRASH_LOOP,
            severity=HDSPSeverity.CRITICAL,
            namespace="spark",
            resource_name="spark-executor-123",
            resource_type="pod",
            message="Pod in CrashLoopBackOff state",
        )

        assert anomaly.anomaly_type == HDSPAnomalyType.CRASH_LOOP
        assert anomaly.severity == HDSPSeverity.CRITICAL
        assert anomaly.namespace == "spark"
        assert anomaly.resource_type == "pod"

    def test_to_dict(self):
        """Test to_dict serialization."""
        anomaly = HDSPAnomaly(
            anomaly_type=HDSPAnomalyType.OOM_KILLED,
            severity=HDSPSeverity.CRITICAL,
            namespace="hdsp",
            resource_name="data-processor",
            resource_type="pod",
            message="Pod terminated due to OOMKilled",
            metrics={"memory_usage": "4.2Gi"},
        )

        d = anomaly.to_dict()

        assert d["anomaly_type"] == "oom_killed"
        assert d["severity"] == "critical"
        assert d["metrics"]["memory_usage"] == "4.2Gi"


class TestHDSPDetectionResult:
    """Test suite for HDSPDetectionResult."""

    def test_creation(self):
        """Test HDSPDetectionResult creation."""
        anomaly = HDSPAnomaly(
            anomaly_type=HDSPAnomalyType.POD_RESTART,
            severity=HDSPSeverity.HIGH,
            namespace="default",
            resource_name="app-pod",
            resource_type="pod",
            message="Excessive restarts",
        )

        result = HDSPDetectionResult(
            anomalies=[anomaly],
            total_anomalies=1,
            critical_count=0,
            high_count=1,
            medium_count=0,
            low_count=0,
            detection_timestamp=datetime.utcnow().isoformat(),
            cluster_name="test-cluster",
            namespaces_checked=["default"],
            summary="1 anomaly detected",
        )

        assert result.total_anomalies == 1
        assert result.high_count == 1
        assert result.has_anomalies is True
        assert result.has_critical is False

    def test_to_dict(self):
        """Test to_dict serialization."""
        result = HDSPDetectionResult(
            anomalies=[],
            total_anomalies=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            detection_timestamp=datetime.utcnow().isoformat(),
            cluster_name="test-cluster",
            namespaces_checked=["default", "spark"],
            summary="No anomalies",
        )

        d = result.to_dict()

        assert d["total_anomalies"] == 0
        assert d["cluster_name"] == "test-cluster"
        assert "default" in d["namespaces_checked"]


class TestHDSPAnomalyDetector:
    """Test suite for HDSPAnomalyDetector."""

    def test_creation(self):
        """Test HDSPAnomalyDetector creation."""
        detector = HDSPAnomalyDetector()

        assert detector.restart_threshold == 3
        assert detector.cpu_threshold == 90.0
        assert detector.memory_threshold == 85.0

    def test_creation_with_custom_thresholds(self):
        """Test creation with custom thresholds."""
        detector = HDSPAnomalyDetector(
            restart_threshold=5,
            cpu_threshold=80.0,
            memory_threshold=75.0,
            cluster_name="custom-cluster",
        )

        assert detector.restart_threshold == 5
        assert detector.cpu_threshold == 80.0
        assert detector.cluster_name == "custom-cluster"

    def test_detect_all(self):
        """Test detect_all method."""
        detector = HDSPAnomalyDetector()

        result = detector.detect_all()

        assert isinstance(result, HDSPDetectionResult)
        assert result.cluster_name is not None
        assert len(result.namespaces_checked) > 0

    def test_detect_pod_failures(self):
        """Test detect_pod_failures method."""
        detector = HDSPAnomalyDetector()

        anomalies = detector.detect_pod_failures()

        assert isinstance(anomalies, list)
        for anomaly in anomalies:
            assert anomaly.anomaly_type in (
                HDSPAnomalyType.CRASH_LOOP,
                HDSPAnomalyType.OOM_KILLED,
                HDSPAnomalyType.POD_RESTART,
            )
            assert anomaly.resource_type == "pod"

    def test_detect_node_pressure(self):
        """Test detect_node_pressure method."""
        detector = HDSPAnomalyDetector()

        anomalies = detector.detect_node_pressure()

        assert isinstance(anomalies, list)
        for anomaly in anomalies:
            assert anomaly.anomaly_type == HDSPAnomalyType.NODE_PRESSURE
            assert anomaly.resource_type == "node"

    def test_detect_resource_anomalies(self):
        """Test detect_resource_anomalies method."""
        detector = HDSPAnomalyDetector()

        anomalies = detector.detect_resource_anomalies()

        assert isinstance(anomalies, list)
        for anomaly in anomalies:
            assert anomaly.anomaly_type == HDSPAnomalyType.RESOURCE_ANOMALY

    def test_severity_calculation_restarts(self):
        """Test restart severity calculation."""
        detector = HDSPAnomalyDetector(restart_threshold=3)

        assert detector._calculate_restart_severity(10) == HDSPSeverity.CRITICAL
        assert detector._calculate_restart_severity(7) == HDSPSeverity.HIGH
        assert detector._calculate_restart_severity(4) == HDSPSeverity.MEDIUM
        assert detector._calculate_restart_severity(1) == HDSPSeverity.LOW

    def test_severity_calculation_resources(self):
        """Test resource severity calculation."""
        detector = HDSPAnomalyDetector(cpu_threshold=90.0)

        # >= 95 is critical
        assert detector._calculate_resource_severity(98.0, 90.0) == HDSPSeverity.CRITICAL
        assert detector._calculate_resource_severity(96.0, 90.0) == HDSPSeverity.CRITICAL
        # >= threshold + 5 is high
        assert detector._calculate_resource_severity(95.5, 90.0) == HDSPSeverity.CRITICAL
        # >= threshold is medium
        assert detector._calculate_resource_severity(91.0, 90.0) == HDSPSeverity.MEDIUM

    def test_generate_summary(self):
        """Test summary generation."""
        detector = HDSPAnomalyDetector()

        anomalies = [
            HDSPAnomaly(
                anomaly_type=HDSPAnomalyType.CRASH_LOOP,
                severity=HDSPSeverity.CRITICAL,
                namespace="spark",
                resource_name="executor",
                resource_type="pod",
                message="CrashLoop",
            ),
            HDSPAnomaly(
                anomaly_type=HDSPAnomalyType.NODE_PRESSURE,
                severity=HDSPSeverity.HIGH,
                namespace="cluster",
                resource_name="node-1",
                resource_type="node",
                message="MemoryPressure",
            ),
        ]

        summary = detector._generate_summary(anomalies, 1, 1, 0, 0)

        assert "2 anomalies" in summary
        assert "1 CRITICAL" in summary
        assert "1 HIGH" in summary

    def test_exclude_pods_pattern(self):
        """Test pod exclusion pattern."""
        detector = HDSPAnomalyDetector()
        detector.exclude_pods_pattern = r"^kube-.*"

        assert detector._should_exclude_pod("kube-proxy-abc123") is True
        assert detector._should_exclude_pod("my-app-pod") is False

    def test_detect_with_injected_anomaly(self):
        """Test detection with injected anomaly."""
        client = PrometheusClient()
        client.provider.inject_anomaly(
            anomaly_type="crash_loop",
            namespace="test-ns",
            pod="test-crash-pod",
        )

        detector = HDSPAnomalyDetector(
            prometheus_client=client,
            namespaces=["test-ns"],
        )

        anomalies = detector.detect_pod_failures()

        # Should detect the injected anomaly
        crash_anomalies = [
            a for a in anomalies if a.anomaly_type == HDSPAnomalyType.CRASH_LOOP
        ]
        assert len(crash_anomalies) > 0


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
        from src.handlers.hdsp_detection_handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        assert handler.prometheus_client is not None
        assert handler.detector is not None

    def test_process_full_detection(self, lambda_context):
        """Test full detection processing."""
        from src.handlers.hdsp_detection_handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "all"}
        result = handler.process(event, lambda_context)

        assert "detection_type" in result
        assert result["detection_type"] == "all"
        assert "total_anomalies" in result
        assert "severity_breakdown" in result

    def test_process_pod_failure_only(self, lambda_context):
        """Test pod failure only detection."""
        from src.handlers.hdsp_detection_handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "pod_failure"}
        result = handler.process(event, lambda_context)

        assert result["detection_type"] == "pod_failure"

    def test_process_node_pressure_only(self, lambda_context):
        """Test node pressure only detection."""
        from src.handlers.hdsp_detection_handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "node_pressure"}
        result = handler.process(event, lambda_context)

        assert result["detection_type"] == "node_pressure"

    def test_process_resource_only(self, lambda_context):
        """Test resource anomaly only detection."""
        from src.handlers.hdsp_detection_handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "resource"}
        result = handler.process(event, lambda_context)

        assert result["detection_type"] == "resource"

    def test_process_invalid_type(self, lambda_context):
        """Test invalid detection type."""
        from src.handlers.hdsp_detection_handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        event = {"detection_type": "invalid"}

        with pytest.raises(ValueError) as excinfo:
            handler.process(event, lambda_context)

        assert "Invalid detection_type" in str(excinfo.value)

    def test_lambda_entry_point(self, lambda_context):
        """Test Lambda entry point function."""
        from src.handlers.hdsp_detection_handler import handler

        event = {"body": '{"detection_type": "all"}'}
        result = handler(event, lambda_context)

        assert result["statusCode"] == 200
        assert "body" in result

    def test_handler_with_default_event(self, lambda_context):
        """Test handler with minimal event."""
        from src.handlers.hdsp_detection_handler import HDSPDetectionHandler

        handler = HDSPDetectionHandler()

        # Empty event should use defaults
        event = {}
        result = handler.process(event, lambda_context)

        assert result["detection_type"] == "all"


# Fixtures for HDSP tests
@pytest.fixture
def sample_hdsp_anomaly() -> HDSPAnomaly:
    """Provide sample HDSP anomaly."""
    return HDSPAnomaly(
        anomaly_type=HDSPAnomalyType.CRASH_LOOP,
        severity=HDSPSeverity.CRITICAL,
        namespace="spark",
        resource_name="spark-executor-123",
        resource_type="pod",
        message="Pod in CrashLoopBackOff state",
        metrics={"crash_loop_status": 1},
        labels={"app": "spark", "role": "executor"},
    )


@pytest.fixture
def sample_hdsp_detection_result(sample_hdsp_anomaly) -> HDSPDetectionResult:
    """Provide sample HDSP detection result."""
    return HDSPDetectionResult(
        anomalies=[sample_hdsp_anomaly],
        total_anomalies=1,
        critical_count=1,
        high_count=0,
        medium_count=0,
        low_count=0,
        detection_timestamp=datetime.utcnow().isoformat(),
        cluster_name="on-prem-k8s",
        namespaces_checked=["default", "spark", "hdsp"],
        summary="1 critical anomaly detected: CrashLoopBackOff in spark namespace",
    )


@pytest.fixture
def mock_prometheus_data() -> Dict[str, Any]:
    """Provide mock Prometheus metric data."""
    return {
        "pod_restarts": [
            {"namespace": "spark", "pod": "executor-1", "restarts": 5},
            {"namespace": "hdsp", "pod": "worker-2", "restarts": 3},
        ],
        "crash_loop_pods": [
            {"namespace": "spark", "pod": "driver-pod", "reason": "CrashLoopBackOff"},
        ],
        "oom_killed_pods": [
            {"namespace": "hdsp", "pod": "memory-hog", "reason": "OOMKilled"},
        ],
        "node_conditions": [
            {"node": "worker-node-1", "condition": "MemoryPressure", "status": "true"},
            {"node": "worker-node-2", "condition": "Ready", "status": "true"},
        ],
        "high_cpu_pods": [
            {"namespace": "spark", "pod": "executor-heavy", "cpu_percent": 95.0},
        ],
        "high_memory_pods": [
            {"namespace": "hdsp", "pod": "cache-pod", "memory_percent": 92.0},
        ],
    }
