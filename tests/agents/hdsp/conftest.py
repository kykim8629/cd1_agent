"""
HDSP Agent Test Configuration and Fixtures.

Specialized fixtures for HDSP (Health Detection and Service Protection) agent tests.
Includes Prometheus integration test fixtures.
"""

import os
import sys
import pytest
from typing import Any, Dict
from unittest.mock import patch

# Add infra helpers to path for metric injection
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "infra", "hdsp_agent"))

# Provider selection based on environment
_test_prometheus_provider = os.getenv("TEST_PROMETHEUS_PROVIDER", "mock")

# Set default providers
if _test_prometheus_provider == "real":
    os.environ.setdefault("PROMETHEUS_MOCK", "false")
else:
    os.environ.setdefault("PROMETHEUS_MOCK", "true")

# LLM always uses mock for tests
os.environ.setdefault("LLM_PROVIDER", "mock")


# ============================================================================
# Prometheus Test Environment Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def prometheus_endpoint() -> str:
    """Get Prometheus endpoint URL."""
    return os.getenv("PROMETHEUS_URL", "http://localhost:9090")


@pytest.fixture(scope="session")
def pushgateway_endpoint() -> str:
    """Get Pushgateway endpoint URL."""
    return os.getenv("PUSHGATEWAY_URL", "http://localhost:9091")


@pytest.fixture(scope="session")
def prometheus_available(prometheus_endpoint: str) -> bool:
    """Check if Prometheus is available and healthy.

    Returns True if Prometheus is running and healthy, False otherwise.
    """
    import urllib.request
    import urllib.error

    try:
        health_url = f"{prometheus_endpoint}/-/healthy"
        with urllib.request.urlopen(health_url, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


@pytest.fixture(scope="session")
def pushgateway_available(pushgateway_endpoint: str) -> bool:
    """Check if Pushgateway is available and healthy.

    Returns True if Pushgateway is running and healthy, False otherwise.
    """
    import urllib.request
    import urllib.error

    try:
        health_url = f"{pushgateway_endpoint}/-/healthy"
        with urllib.request.urlopen(health_url, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


@pytest.fixture
def skip_without_prometheus(prometheus_available: bool, pushgateway_available: bool):
    """Skip test if Prometheus/Pushgateway is not available."""
    if not prometheus_available:
        pytest.skip("Prometheus is not available")
    if not pushgateway_available:
        pytest.skip("Pushgateway is not available")


# ============================================================================
# Metric Injector Fixtures
# ============================================================================


@pytest.fixture
def metric_injector(pushgateway_available: bool, pushgateway_endpoint: str, prometheus_endpoint: str):
    """Create MetricInjector for test metric injection.

    Automatically skips if Pushgateway is not available.
    Automatically cleans up injected metrics after test.
    """
    if not pushgateway_available:
        pytest.skip("Pushgateway is not available")

    from helpers.metric_injector import MetricInjector

    injector = MetricInjector(
        pushgateway_url=pushgateway_endpoint,
        prometheus_url=prometheus_endpoint,
    )

    yield injector

    # Cleanup after test
    injector.clear_metrics()


# ============================================================================
# Prometheus Client Fixtures
# ============================================================================


@pytest.fixture
def prometheus_client_mock():
    """Create PrometheusClient with mock provider."""
    with patch.dict("os.environ", {"PROMETHEUS_MOCK": "true"}):
        from src.agents.hdsp.services.prometheus_client import PrometheusClient

        return PrometheusClient()


@pytest.fixture
def prometheus_client_real(prometheus_available: bool, prometheus_endpoint: str):
    """Create PrometheusClient with real provider pointing to local Prometheus.

    Automatically skips if Prometheus is not available.
    """
    if not prometheus_available:
        pytest.skip("Prometheus is not available")

    with patch.dict(
        "os.environ",
        {
            "PROMETHEUS_MOCK": "false",
            "PROMETHEUS_URL": prometheus_endpoint,
        },
    ):
        from src.agents.hdsp.services.prometheus_client import PrometheusClient

        return PrometheusClient()


# ============================================================================
# HDSP Handler Fixtures
# ============================================================================


@pytest.fixture
def hdsp_handler_mock():
    """Create HDSP handler with mock providers."""
    with patch.dict(
        "os.environ",
        {
            "LLM_PROVIDER": "mock",
            "AWS_PROVIDER": "mock",
            "PROMETHEUS_MOCK": "true",
        },
    ):
        from src.agents.hdsp.handler import DetectionHandler

        return DetectionHandler()


@pytest.fixture
def hdsp_handler_prometheus(prometheus_available: bool, prometheus_endpoint: str):
    """Create HDSP handler with real Prometheus provider.

    Automatically skips if Prometheus is not available.
    """
    if not prometheus_available:
        pytest.skip("Prometheus is not available")

    with patch.dict(
        "os.environ",
        {
            "LLM_PROVIDER": "mock",
            "AWS_PROVIDER": "mock",
            "PROMETHEUS_MOCK": "false",
            "PROMETHEUS_URL": prometheus_endpoint,
        },
    ):
        from src.agents.hdsp.handler import DetectionHandler

        return DetectionHandler()


# ============================================================================
# Scenario Injection Fixtures
# ============================================================================


@pytest.fixture
def inject_crash_loop_scenario(metric_injector):
    """Inject CrashLoopBackOff scenario and wait for scrape.

    Returns metadata about the injected scenario.
    """
    metric_injector.inject_crash_loop(
        namespace="spark",
        pod="test-crash-loop-pod",
        container="main",
        restart_count=15,
    )
    metric_injector.wait_for_scrape(20)

    return {
        "namespace": "spark",
        "pod": "test-crash-loop-pod",
        "container": "main",
        "expected_severity": "critical",
        "expected_metric": "kube_pod_container_status_waiting_reason",
    }


@pytest.fixture
def inject_oom_killed_scenario(metric_injector):
    """Inject OOMKilled scenario and wait for scrape.

    Returns metadata about the injected scenario.
    """
    metric_injector.inject_oom_killed(
        namespace="hdsp",
        pod="test-oom-pod",
        container="processor",
        restart_count=8,
    )
    metric_injector.wait_for_scrape(20)

    return {
        "namespace": "hdsp",
        "pod": "test-oom-pod",
        "container": "processor",
        "expected_severity": "critical",
        "expected_metric": "kube_pod_container_status_last_terminated_reason",
    }


@pytest.fixture
def inject_node_pressure_scenario(metric_injector):
    """Inject NodePressure scenario and wait for scrape.

    Returns metadata about the injected scenario.
    """
    metric_injector.inject_node_pressure(
        node="worker-node-1",
        condition="MemoryPressure",
    )
    metric_injector.wait_for_scrape(20)

    return {
        "node": "worker-node-1",
        "condition": "MemoryPressure",
        "expected_severity": "high",
        "expected_metric": "kube_node_status_condition",
    }


@pytest.fixture
def inject_high_cpu_scenario(metric_injector):
    """Inject High CPU scenario and wait for scrape.

    Returns metadata about the injected scenario.
    """
    metric_injector.inject_high_cpu(
        namespace="default",
        pod="test-high-cpu-pod",
        container="app",
        cpu_usage_ratio=0.95,
    )
    metric_injector.wait_for_scrape(20)

    return {
        "namespace": "default",
        "pod": "test-high-cpu-pod",
        "container": "app",
        "expected_severity": "high",
        "expected_metric": "container_cpu_usage_seconds_total",
    }


@pytest.fixture
def inject_high_memory_scenario(metric_injector):
    """Inject High Memory scenario and wait for scrape.

    Returns metadata about the injected scenario.
    """
    metric_injector.inject_high_memory(
        namespace="hdsp",
        pod="test-high-memory-pod",
        container="processor",
        memory_usage_gb=3.8,
        memory_limit_gb=4.0,
    )
    metric_injector.wait_for_scrape(20)

    return {
        "namespace": "hdsp",
        "pod": "test-high-memory-pod",
        "container": "processor",
        "expected_severity": "high",
        "expected_metric": "container_memory_working_set_bytes",
    }


@pytest.fixture
def inject_pod_restarts_scenario(metric_injector):
    """Inject Pod Restarts scenario and wait for scrape.

    Returns metadata about the injected scenario.
    """
    metric_injector.inject_pod_restarts(
        namespace="spark",
        pod="test-unstable-pod",
        container="worker",
        restart_count=25,
    )
    metric_injector.wait_for_scrape(20)

    return {
        "namespace": "spark",
        "pod": "test-unstable-pod",
        "container": "worker",
        "expected_severity": "medium",
        "expected_metric": "kube_pod_container_status_restarts_total",
    }


# ============================================================================
# Assertion Helpers
# ============================================================================


@pytest.fixture
def assert_prometheus_result():
    """Factory fixture for Prometheus query result validation."""

    def _assert(results: list, expected_count: int = None, min_count: int = None):
        """Assert Prometheus query results.

        Args:
            results: List of PrometheusQueryResult objects
            expected_count: Expected exact count (optional)
            min_count: Minimum expected count (optional)
        """
        assert isinstance(results, list)

        if expected_count is not None:
            assert len(results) == expected_count, \
                f"Expected {expected_count} results, got {len(results)}"

        if min_count is not None:
            assert len(results) >= min_count, \
                f"Expected at least {min_count} results, got {len(results)}"

    return _assert
