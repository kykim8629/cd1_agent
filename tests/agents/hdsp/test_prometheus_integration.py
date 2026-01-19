"""
Prometheus Integration Tests for HDSP Agent.

Tests failure scenarios injected into Prometheus/Pushgateway to verify
detection capabilities in a realistic environment.

Usage:
    # Start HDSP test environment first
    make hdsp-up

    # Run Prometheus integration tests
    make hdsp-test

    # Or run directly with pytest
    TEST_PROMETHEUS_PROVIDER=real pytest tests/agents/hdsp/test_prometheus_integration.py -v -m prometheus
"""

import os
import pytest
from datetime import datetime, timedelta


pytestmark = [pytest.mark.integration, pytest.mark.prometheus]


class TestPrometheusClientIntegration:
    """Test PrometheusClient against real local Prometheus."""

    @pytest.mark.prometheus
    def test_prometheus_connection(
        self,
        prometheus_client_real,
        skip_without_prometheus,
    ):
        """Test basic Prometheus connectivity."""
        # Simple query that should return something
        results = prometheus_client_real.query("up")

        # 'up' metric should exist for prometheus and pushgateway
        assert isinstance(results, list)
        assert len(results) >= 1, "Expected 'up' metric to be present"

    @pytest.mark.prometheus
    def test_query_non_existent_metric(
        self,
        prometheus_client_real,
        skip_without_prometheus,
    ):
        """Test query for non-existent metric returns empty list."""
        results = prometheus_client_real.query("non_existent_metric_12345")

        assert isinstance(results, list)
        assert len(results) == 0


class TestCrashLoopDetection:
    """Test CrashLoopBackOff detection against real Prometheus."""

    @pytest.mark.prometheus
    def test_detects_crash_loop(
        self,
        prometheus_client_real,
        inject_crash_loop_scenario,
        skip_without_prometheus,
    ):
        """Test that CrashLoopBackOff scenario is detected.

        Scenario: Pod in CrashLoopBackOff state
        Expected: Metric with reason=CrashLoopBackOff detected
        """
        scenario = inject_crash_loop_scenario

        # Query for crash loop pods
        results = prometheus_client_real.get_crash_loop_pods(
            namespace=scenario["namespace"]
        )

        # Verify detection
        assert len(results) >= 1, f"Expected to detect crash loop pod, got {len(results)} results"

        # Verify the injected pod is found
        pods_found = [r.labels.get("pod") for r in results]
        assert scenario["pod"] in pods_found, \
            f"Expected pod '{scenario['pod']}' in results, found: {pods_found}"

    @pytest.mark.prometheus
    def test_crash_loop_with_namespace_filter(
        self,
        prometheus_client_real,
        inject_crash_loop_scenario,
        skip_without_prometheus,
    ):
        """Test crash loop detection with namespace filter."""
        scenario = inject_crash_loop_scenario

        # Query with matching namespace
        results_match = prometheus_client_real.get_crash_loop_pods(
            namespace=scenario["namespace"]
        )
        assert len(results_match) >= 1

        # Query with different namespace - should not find our injected pod
        results_no_match = prometheus_client_real.get_crash_loop_pods(
            namespace="non-existent-namespace"
        )
        injected_pods = [r for r in results_no_match if r.labels.get("pod") == scenario["pod"]]
        assert len(injected_pods) == 0


class TestOOMKilledDetection:
    """Test OOMKilled detection against real Prometheus."""

    @pytest.mark.prometheus
    def test_detects_oom_killed(
        self,
        prometheus_client_real,
        inject_oom_killed_scenario,
        skip_without_prometheus,
    ):
        """Test that OOMKilled scenario is detected.

        Scenario: Pod terminated with OOMKilled
        Expected: Metric with reason=OOMKilled detected
        """
        scenario = inject_oom_killed_scenario

        # Query for OOM killed pods
        results = prometheus_client_real.get_oom_killed_pods(
            namespace=scenario["namespace"]
        )

        # Verify detection
        assert len(results) >= 1, f"Expected to detect OOM killed pod, got {len(results)} results"

        # Verify the injected pod is found
        pods_found = [r.labels.get("pod") for r in results]
        assert scenario["pod"] in pods_found, \
            f"Expected pod '{scenario['pod']}' in results, found: {pods_found}"


class TestNodePressureDetection:
    """Test Node Pressure detection against real Prometheus."""

    @pytest.mark.prometheus
    def test_detects_node_pressure(
        self,
        prometheus_client_real,
        inject_node_pressure_scenario,
        skip_without_prometheus,
    ):
        """Test that Node Pressure scenario is detected.

        Scenario: Node with MemoryPressure condition
        Expected: Node condition metric detected
        """
        scenario = inject_node_pressure_scenario

        # Query for node conditions
        results = prometheus_client_real.get_node_conditions(
            condition=scenario["condition"]
        )

        # Verify detection
        assert len(results) >= 1, f"Expected to detect node pressure, got {len(results)} results"

        # Verify the injected node is found
        nodes_found = [r.labels.get("node") for r in results]
        assert scenario["node"] in nodes_found, \
            f"Expected node '{scenario['node']}' in results, found: {nodes_found}"


class TestHighResourceDetection:
    """Test high resource usage detection against real Prometheus."""

    @pytest.mark.prometheus
    def test_detects_high_cpu(
        self,
        prometheus_client_real,
        inject_high_cpu_scenario,
        skip_without_prometheus,
        metric_injector,
    ):
        """Test that High CPU scenario metrics are available.

        Scenario: Pod with 95% CPU usage
        Expected: CPU metrics present in Prometheus
        """
        scenario = inject_high_cpu_scenario

        # Verify the metric exists
        exists = metric_injector.verify_metric_exists(
            scenario["expected_metric"],
            {"namespace": scenario["namespace"], "pod": scenario["pod"]},
        )
        assert exists, f"Expected metric '{scenario['expected_metric']}' to exist"

    @pytest.mark.prometheus
    def test_detects_high_memory(
        self,
        prometheus_client_real,
        inject_high_memory_scenario,
        skip_without_prometheus,
        metric_injector,
    ):
        """Test that High Memory scenario metrics are available.

        Scenario: Pod with 95% memory usage
        Expected: Memory metrics present in Prometheus
        """
        scenario = inject_high_memory_scenario

        # Verify the metric exists
        exists = metric_injector.verify_metric_exists(
            scenario["expected_metric"],
            {"namespace": scenario["namespace"], "pod": scenario["pod"]},
        )
        assert exists, f"Expected metric '{scenario['expected_metric']}' to exist"


class TestPodRestartsDetection:
    """Test pod restarts detection against real Prometheus."""

    @pytest.mark.prometheus
    def test_detects_pod_restarts(
        self,
        prometheus_client_real,
        inject_pod_restarts_scenario,
        skip_without_prometheus,
    ):
        """Test that Pod Restarts scenario is detected.

        Scenario: Pod with 25 restarts
        Expected: Restart count metric detected
        """
        scenario = inject_pod_restarts_scenario

        # Query for pod restarts
        results = prometheus_client_real.get_pod_restarts(
            namespace=scenario["namespace"]
        )

        # Verify detection
        assert len(results) >= 1, f"Expected to detect pod restarts, got {len(results)} results"

        # Find the injected pod
        injected_results = [
            r for r in results
            if r.labels.get("pod") == scenario["pod"]
        ]
        assert len(injected_results) >= 1, \
            f"Expected to find pod '{scenario['pod']}' in results"

        # Verify restart count
        for result in injected_results:
            if result.latest_value is not None:
                assert result.latest_value >= 20, \
                    f"Expected restart count >= 20, got {result.latest_value}"


class TestMultipleScenarios:
    """Test multiple concurrent scenarios."""

    @pytest.mark.prometheus
    def test_multiple_scenarios_isolation(
        self,
        prometheus_client_real,
        metric_injector,
        skip_without_prometheus,
    ):
        """Test that multiple scenarios can be active and detected independently.

        Verifies isolation between different failure scenarios.
        """
        # Inject multiple scenarios
        crash_loop = metric_injector.inject_crash_loop(
            namespace="multi-test", pod="crash-pod"
        )
        oom_killed = metric_injector.inject_oom_killed(
            namespace="multi-test", pod="oom-pod"
        )
        node_pressure = metric_injector.inject_node_pressure(
            node="multi-test-node", condition="MemoryPressure"
        )

        # Wait for scrape
        metric_injector.wait_for_scrape(20)

        # Verify all scenarios are detectable
        crash_results = prometheus_client_real.get_crash_loop_pods(namespace="multi-test")
        oom_results = prometheus_client_real.get_oom_killed_pods(namespace="multi-test")
        node_results = prometheus_client_real.get_node_conditions(condition="MemoryPressure")

        # All should be detected
        crash_pods = [r.labels.get("pod") for r in crash_results]
        assert "crash-pod" in crash_pods, "CrashLoop pod not detected"

        oom_pods = [r.labels.get("pod") for r in oom_results]
        assert "oom-pod" in oom_pods, "OOM pod not detected"

        pressure_nodes = [r.labels.get("node") for r in node_results]
        assert "multi-test-node" in pressure_nodes, "Node pressure not detected"

    @pytest.mark.prometheus
    def test_metric_cleanup(
        self,
        metric_injector,
        prometheus_client_real,
        skip_without_prometheus,
    ):
        """Test that metric cleanup works properly."""
        # Inject a metric
        metric_injector.inject_crash_loop(
            namespace="cleanup-test", pod="cleanup-pod"
        )
        metric_injector.wait_for_scrape(20)

        # Verify it exists
        results_before = prometheus_client_real.get_crash_loop_pods(namespace="cleanup-test")
        cleanup_pods = [r for r in results_before if r.labels.get("pod") == "cleanup-pod"]
        assert len(cleanup_pods) >= 1, "Metric should exist before cleanup"

        # Clear metrics
        cleared = metric_injector.clear_metrics()
        assert cleared >= 1, "Should have cleared at least 1 metric"

        # Verify tracking is cleared
        assert metric_injector.injected_count == 0


class TestEdgeCases:
    """Edge case tests for Prometheus integration."""

    @pytest.mark.prometheus
    def test_empty_namespace_query(
        self,
        prometheus_client_real,
        skip_without_prometheus,
    ):
        """Test query with non-existent namespace returns empty."""
        results = prometheus_client_real.get_crash_loop_pods(
            namespace="definitely-does-not-exist-12345"
        )

        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.prometheus
    def test_query_range_functionality(
        self,
        prometheus_client_real,
        inject_crash_loop_scenario,
        skip_without_prometheus,
    ):
        """Test range query functionality."""
        end = datetime.utcnow()
        start = end - timedelta(hours=1)

        # Range query should work
        results = prometheus_client_real.query_range(
            'kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"}',
            start=start,
            end=end,
            step="15s",
        )

        assert isinstance(results, list)
        # Should have at least our injected metric
        assert len(results) >= 1

    @pytest.mark.prometheus
    def test_metric_metadata(
        self,
        prometheus_client_real,
        inject_crash_loop_scenario,
        skip_without_prometheus,
    ):
        """Test metric metadata retrieval."""
        # This may or may not return data depending on Prometheus config
        metadata = prometheus_client_real.get_metric_metadata(
            "kube_pod_container_status_waiting_reason"
        )

        # Should at least return a dict (possibly empty)
        assert isinstance(metadata, dict)


class TestMetricInjectorAPI:
    """Test MetricInjector API independently."""

    @pytest.mark.prometheus
    def test_injector_tracking(
        self,
        metric_injector,
        skip_without_prometheus,
    ):
        """Test that injector properly tracks injected metrics."""
        assert metric_injector.injected_count == 0

        metric_injector.inject_crash_loop(namespace="track-test", pod="pod-1")
        assert metric_injector.injected_count == 1

        metric_injector.inject_oom_killed(namespace="track-test", pod="pod-2")
        assert metric_injector.injected_count == 2

        injected = metric_injector.injected_metrics
        assert len(injected) == 2
        assert injected[0].metric_name == "kube_pod_container_status_waiting_reason"
        assert injected[1].metric_name == "kube_pod_container_status_last_terminated_reason"

    @pytest.mark.prometheus
    def test_injector_verify_metric(
        self,
        metric_injector,
        skip_without_prometheus,
    ):
        """Test verify_metric_exists functionality."""
        # Inject a metric
        metric_injector.inject_crash_loop(namespace="verify-test", pod="verify-pod")
        metric_injector.wait_for_scrape(20)

        # Verify it exists
        exists = metric_injector.verify_metric_exists(
            "kube_pod_container_status_waiting_reason",
            {"namespace": "verify-test", "pod": "verify-pod"},
        )
        assert exists, "Injected metric should be verifiable"

        # Verify non-existent metric returns False
        not_exists = metric_injector.verify_metric_exists(
            "fake_metric_12345",
            {"namespace": "fake"},
        )
        assert not not_exists, "Non-existent metric should return False"

    @pytest.mark.prometheus
    def test_injector_direct_query(
        self,
        metric_injector,
        skip_without_prometheus,
    ):
        """Test direct PromQL query through injector."""
        # Inject a metric
        metric_injector.inject_crash_loop(namespace="query-test", pod="query-pod")
        metric_injector.wait_for_scrape(20)

        # Direct query
        result = metric_injector.query_prometheus(
            'kube_pod_container_status_waiting_reason{namespace="query-test"}'
        )

        assert result.get("status") == "success"
        data = result.get("data", {}).get("result", [])
        assert len(data) >= 1
