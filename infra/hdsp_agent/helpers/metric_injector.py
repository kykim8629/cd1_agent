"""
Metric Injector for HDSP Agent Integration Tests.

Provides Python API for injecting K8s failure metrics into Pushgateway
for testing the HDSP Agent's detection capabilities.

Usage:
    injector = MetricInjector()
    injector.inject_crash_loop(namespace="spark", pod="test-pod")
    injector.inject_oom_killed(namespace="hdsp", pod="processor")
    injector.clear_metrics()  # Clean up after tests
"""

import os
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class InjectedMetric:
    """Represents an injected metric for tracking."""

    metric_name: str
    labels: Dict[str, str]
    value: float
    job: str
    grouping_key: Dict[str, str]
    injected_at: datetime = field(default_factory=datetime.utcnow)


class MetricInjector:
    """
    Python helper for injecting K8s metrics into Pushgateway.

    Provides a clean API for pytest fixtures to inject various
    K8s failure scenarios and verify detection.
    """

    def __init__(
        self,
        pushgateway_url: Optional[str] = None,
        prometheus_url: Optional[str] = None,
    ):
        """
        Initialize MetricInjector.

        Args:
            pushgateway_url: Pushgateway URL (default: http://localhost:9091)
            prometheus_url: Prometheus URL (default: http://localhost:9090)
        """
        self.pushgateway_url = pushgateway_url or os.environ.get(
            "PUSHGATEWAY_URL", "http://localhost:9091"
        )
        self.prometheus_url = prometheus_url or os.environ.get(
            "PROMETHEUS_URL", "http://localhost:9090"
        )
        self._injected_metrics: List[InjectedMetric] = []
        self._session = None

    def _get_session(self):
        """Get or create requests session."""
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    def _push_metrics(
        self,
        metrics_text: str,
        job: str,
        grouping_key: Dict[str, str],
    ) -> bool:
        """
        Push metrics to Pushgateway.

        Args:
            metrics_text: Prometheus exposition format metrics
            job: Job name for grouping
            grouping_key: Additional grouping labels

        Returns:
            True if successful, False otherwise
        """
        session = self._get_session()

        # Build URL with grouping key
        url = f"{self.pushgateway_url}/metrics/job/{job}"
        for key, value in grouping_key.items():
            url += f"/{key}/{value}"

        try:
            response = session.post(
                url,
                data=metrics_text,
                headers={"Content-Type": "text/plain"},
                timeout=10,
            )
            response.raise_for_status()
            logger.info(f"Pushed metrics to {url}")
            return True
        except Exception as e:
            logger.error(f"Failed to push metrics: {e}")
            return False

    def _delete_metrics(
        self,
        job: str,
        grouping_key: Dict[str, str],
    ) -> bool:
        """
        Delete metrics from Pushgateway.

        Args:
            job: Job name for grouping
            grouping_key: Additional grouping labels

        Returns:
            True if successful, False otherwise
        """
        session = self._get_session()

        # Build URL with grouping key
        url = f"{self.pushgateway_url}/metrics/job/{job}"
        for key, value in grouping_key.items():
            url += f"/{key}/{value}"

        try:
            response = session.delete(url, timeout=10)
            # 202 Accepted or 200 OK are both valid
            if response.status_code in [200, 202]:
                logger.info(f"Deleted metrics from {url}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete metrics: {e}")
            return False

    def inject_crash_loop(
        self,
        namespace: str = "spark",
        pod: str = "test-crash-loop-pod",
        container: str = "main",
        restart_count: int = 15,
    ) -> InjectedMetric:
        """
        Inject CrashLoopBackOff scenario.

        Args:
            namespace: K8s namespace
            pod: Pod name
            container: Container name
            restart_count: Number of restarts to simulate

        Returns:
            InjectedMetric tracking object
        """
        metrics = f"""# HELP kube_pod_container_status_waiting_reason Describes the reason the container is currently in waiting state.
# TYPE kube_pod_container_status_waiting_reason gauge
kube_pod_container_status_waiting_reason{{namespace="{namespace}",pod="{pod}",container="{container}",reason="CrashLoopBackOff"}} 1
# HELP kube_pod_container_status_restarts_total The number of container restarts per container.
# TYPE kube_pod_container_status_restarts_total counter
kube_pod_container_status_restarts_total{{namespace="{namespace}",pod="{pod}",container="{container}"}} {restart_count}
"""
        grouping_key = {"namespace": namespace, "pod": pod}
        self._push_metrics(metrics, "kube-state-metrics", grouping_key)

        injected = InjectedMetric(
            metric_name="kube_pod_container_status_waiting_reason",
            labels={
                "namespace": namespace,
                "pod": pod,
                "container": container,
                "reason": "CrashLoopBackOff",
            },
            value=1.0,
            job="kube-state-metrics",
            grouping_key=grouping_key,
        )
        self._injected_metrics.append(injected)
        logger.info(f"Injected CrashLoopBackOff for {namespace}/{pod}")
        return injected

    def inject_oom_killed(
        self,
        namespace: str = "hdsp",
        pod: str = "test-oom-pod",
        container: str = "processor",
        restart_count: int = 8,
    ) -> InjectedMetric:
        """
        Inject OOMKilled scenario.

        Args:
            namespace: K8s namespace
            pod: Pod name
            container: Container name
            restart_count: Number of restarts to simulate

        Returns:
            InjectedMetric tracking object
        """
        metrics = f"""# HELP kube_pod_container_status_last_terminated_reason Describes the last reason the container was in terminated state.
# TYPE kube_pod_container_status_last_terminated_reason gauge
kube_pod_container_status_last_terminated_reason{{namespace="{namespace}",pod="{pod}",container="{container}",reason="OOMKilled"}} 1
# HELP kube_pod_container_status_terminated Describes whether the container is currently in terminated state.
# TYPE kube_pod_container_status_terminated gauge
kube_pod_container_status_terminated{{namespace="{namespace}",pod="{pod}",container="{container}"}} 1
# HELP kube_pod_container_status_restarts_total The number of container restarts per container.
# TYPE kube_pod_container_status_restarts_total counter
kube_pod_container_status_restarts_total{{namespace="{namespace}",pod="{pod}",container="{container}"}} {restart_count}
"""
        grouping_key = {"namespace": namespace, "pod": pod}
        self._push_metrics(metrics, "kube-state-metrics", grouping_key)

        injected = InjectedMetric(
            metric_name="kube_pod_container_status_last_terminated_reason",
            labels={
                "namespace": namespace,
                "pod": pod,
                "container": container,
                "reason": "OOMKilled",
            },
            value=1.0,
            job="kube-state-metrics",
            grouping_key=grouping_key,
        )
        self._injected_metrics.append(injected)
        logger.info(f"Injected OOMKilled for {namespace}/{pod}")
        return injected

    def inject_node_pressure(
        self,
        node: str = "worker-node-1",
        condition: str = "MemoryPressure",
        available_memory_bytes: int = 500_000_000,  # 500MB
        allocatable_memory_bytes: int = 8_000_000_000,  # 8GB
    ) -> InjectedMetric:
        """
        Inject Node Pressure scenario.

        Args:
            node: Node name
            condition: Pressure condition (MemoryPressure, DiskPressure, etc.)
            available_memory_bytes: Available memory in bytes
            allocatable_memory_bytes: Allocatable memory in bytes

        Returns:
            InjectedMetric tracking object
        """
        metrics = f"""# HELP kube_node_status_condition The condition of a cluster node.
# TYPE kube_node_status_condition gauge
kube_node_status_condition{{node="{node}",condition="{condition}",status="true"}} 1
kube_node_status_condition{{node="{node}",condition="{condition}",status="false"}} 0
kube_node_status_condition{{node="{node}",condition="{condition}",status="unknown"}} 0
# HELP kube_node_status_allocatable_memory_bytes The allocatable memory of a node that is available for scheduling.
# TYPE kube_node_status_allocatable_memory_bytes gauge
kube_node_status_allocatable_memory_bytes{{node="{node}"}} {allocatable_memory_bytes}
# HELP node_memory_MemAvailable_bytes Memory information field MemAvailable_bytes.
# TYPE node_memory_MemAvailable_bytes gauge
node_memory_MemAvailable_bytes{{node="{node}"}} {available_memory_bytes}
"""
        grouping_key = {"node": node}
        self._push_metrics(metrics, "kube-state-metrics", grouping_key)

        injected = InjectedMetric(
            metric_name="kube_node_status_condition",
            labels={
                "node": node,
                "condition": condition,
                "status": "true",
            },
            value=1.0,
            job="kube-state-metrics",
            grouping_key=grouping_key,
        )
        self._injected_metrics.append(injected)
        logger.info(f"Injected {condition} for node {node}")
        return injected

    def inject_high_cpu(
        self,
        namespace: str = "default",
        pod: str = "high-cpu-pod",
        container: str = "app",
        cpu_usage_ratio: float = 0.95,  # 95% CPU
        cpu_limit_cores: float = 1.0,
    ) -> InjectedMetric:
        """
        Inject High CPU scenario.

        Args:
            namespace: K8s namespace
            pod: Pod name
            container: Container name
            cpu_usage_ratio: CPU usage as ratio (0-1)
            cpu_limit_cores: CPU limit in cores

        Returns:
            InjectedMetric tracking object
        """
        # Simulate cumulative CPU seconds
        now = int(time.time())
        cpu_seconds = now * cpu_usage_ratio
        throttled_seconds = 1500 if cpu_usage_ratio > 0.9 else 0

        metrics = f"""# HELP container_cpu_usage_seconds_total Cumulative cpu time consumed.
# TYPE container_cpu_usage_seconds_total counter
container_cpu_usage_seconds_total{{namespace="{namespace}",pod="{pod}",container="{container}"}} {cpu_seconds}
# HELP kube_pod_container_resource_limits The number of requested limit resource by a container.
# TYPE kube_pod_container_resource_limits gauge
kube_pod_container_resource_limits{{namespace="{namespace}",pod="{pod}",container="{container}",resource="cpu"}} {cpu_limit_cores}
# HELP container_cpu_cfs_throttled_seconds_total Total time duration the container has been throttled.
# TYPE container_cpu_cfs_throttled_seconds_total counter
container_cpu_cfs_throttled_seconds_total{{namespace="{namespace}",pod="{pod}",container="{container}"}} {throttled_seconds}
"""
        grouping_key = {"namespace": namespace, "pod": pod}
        self._push_metrics(metrics, "cadvisor", grouping_key)

        injected = InjectedMetric(
            metric_name="container_cpu_usage_seconds_total",
            labels={
                "namespace": namespace,
                "pod": pod,
                "container": container,
            },
            value=cpu_seconds,
            job="cadvisor",
            grouping_key=grouping_key,
        )
        self._injected_metrics.append(injected)
        logger.info(f"Injected high CPU ({cpu_usage_ratio*100}%) for {namespace}/{pod}")
        return injected

    def inject_high_memory(
        self,
        namespace: str = "hdsp",
        pod: str = "high-memory-pod",
        container: str = "processor",
        memory_usage_gb: float = 3.8,  # 3.8 GB
        memory_limit_gb: float = 4.0,  # 4 GB limit
    ) -> InjectedMetric:
        """
        Inject High Memory scenario.

        Args:
            namespace: K8s namespace
            pod: Pod name
            container: Container name
            memory_usage_gb: Memory usage in GB
            memory_limit_gb: Memory limit in GB

        Returns:
            InjectedMetric tracking object
        """
        memory_bytes = int(memory_usage_gb * 1024 * 1024 * 1024)
        limit_bytes = int(memory_limit_gb * 1024 * 1024 * 1024)
        cache_bytes = 100_000_000  # 100MB cache

        metrics = f"""# HELP container_memory_working_set_bytes Current working set of the container in bytes.
# TYPE container_memory_working_set_bytes gauge
container_memory_working_set_bytes{{namespace="{namespace}",pod="{pod}",container="{container}"}} {memory_bytes}
# HELP container_memory_usage_bytes Current memory usage in bytes.
# TYPE container_memory_usage_bytes gauge
container_memory_usage_bytes{{namespace="{namespace}",pod="{pod}",container="{container}"}} {memory_bytes}
# HELP kube_pod_container_resource_limits The number of requested limit resource by a container.
# TYPE kube_pod_container_resource_limits gauge
kube_pod_container_resource_limits{{namespace="{namespace}",pod="{pod}",container="{container}",resource="memory"}} {limit_bytes}
# HELP container_memory_cache Total page cache memory.
# TYPE container_memory_cache gauge
container_memory_cache{{namespace="{namespace}",pod="{pod}",container="{container}"}} {cache_bytes}
"""
        grouping_key = {"namespace": namespace, "pod": pod}
        self._push_metrics(metrics, "cadvisor", grouping_key)

        injected = InjectedMetric(
            metric_name="container_memory_working_set_bytes",
            labels={
                "namespace": namespace,
                "pod": pod,
                "container": container,
            },
            value=float(memory_bytes),
            job="cadvisor",
            grouping_key=grouping_key,
        )
        self._injected_metrics.append(injected)
        usage_percent = (memory_usage_gb / memory_limit_gb) * 100
        logger.info(f"Injected high memory ({usage_percent:.1f}%) for {namespace}/{pod}")
        return injected

    def inject_pod_restarts(
        self,
        namespace: str = "spark",
        pod: str = "unstable-pod",
        container: str = "worker",
        restart_count: int = 25,
    ) -> InjectedMetric:
        """
        Inject Excessive Pod Restarts scenario.

        Args:
            namespace: K8s namespace
            pod: Pod name
            container: Container name
            restart_count: Number of restarts to simulate

        Returns:
            InjectedMetric tracking object
        """
        metrics = f"""# HELP kube_pod_container_status_restarts_total The number of container restarts per container.
# TYPE kube_pod_container_status_restarts_total counter
kube_pod_container_status_restarts_total{{namespace="{namespace}",pod="{pod}",container="{container}"}} {restart_count}
# HELP kube_pod_container_status_running Describes whether the container is currently in running state.
# TYPE kube_pod_container_status_running gauge
kube_pod_container_status_running{{namespace="{namespace}",pod="{pod}",container="{container}"}} 1
# HELP kube_pod_status_phase The pods current phase.
# TYPE kube_pod_status_phase gauge
kube_pod_status_phase{{namespace="{namespace}",pod="{pod}",phase="Running"}} 1
kube_pod_status_phase{{namespace="{namespace}",pod="{pod}",phase="Pending"}} 0
kube_pod_status_phase{{namespace="{namespace}",pod="{pod}",phase="Failed"}} 0
"""
        grouping_key = {"namespace": namespace, "pod": pod}
        self._push_metrics(metrics, "kube-state-metrics", grouping_key)

        injected = InjectedMetric(
            metric_name="kube_pod_container_status_restarts_total",
            labels={
                "namespace": namespace,
                "pod": pod,
                "container": container,
            },
            value=float(restart_count),
            job="kube-state-metrics",
            grouping_key=grouping_key,
        )
        self._injected_metrics.append(injected)
        logger.info(f"Injected {restart_count} restarts for {namespace}/{pod}")
        return injected

    def clear_metrics(self) -> int:
        """
        Clear all injected metrics from Pushgateway.

        Returns:
            Number of metrics cleared
        """
        cleared = 0
        for metric in self._injected_metrics:
            if self._delete_metrics(metric.job, metric.grouping_key):
                cleared += 1

        self._injected_metrics.clear()
        logger.info(f"Cleared {cleared} injected metrics")
        return cleared

    def wait_for_scrape(self, seconds: int = 20):
        """
        Wait for Prometheus to scrape metrics.

        Args:
            seconds: Seconds to wait (default: 20, slightly more than scrape_interval)
        """
        logger.info(f"Waiting {seconds}s for Prometheus scrape...")
        time.sleep(seconds)

    def query_prometheus(self, query: str) -> Dict:
        """
        Execute PromQL query against Prometheus.

        Args:
            query: PromQL query string

        Returns:
            Prometheus API response as dict
        """
        session = self._get_session()

        try:
            response = session.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
            return {"status": "error", "error": str(e)}

    def verify_metric_exists(self, metric_name: str, labels: Dict[str, str] = None) -> bool:
        """
        Verify a metric exists in Prometheus.

        Args:
            metric_name: Metric name to check
            labels: Optional label filters

        Returns:
            True if metric exists, False otherwise
        """
        query = metric_name
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            query = f"{metric_name}{{{label_str}}}"

        result = self.query_prometheus(query)

        if result.get("status") == "success":
            data = result.get("data", {}).get("result", [])
            return len(data) > 0

        return False

    @property
    def injected_count(self) -> int:
        """Get count of currently injected metrics."""
        return len(self._injected_metrics)

    @property
    def injected_metrics(self) -> List[InjectedMetric]:
        """Get list of injected metrics."""
        return self._injected_metrics.copy()


# Convenience function for quick testing
def create_injector(
    pushgateway_url: Optional[str] = None,
    prometheus_url: Optional[str] = None,
) -> MetricInjector:
    """Create MetricInjector instance."""
    return MetricInjector(pushgateway_url, prometheus_url)


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)

    injector = MetricInjector()
    print(f"Pushgateway: {injector.pushgateway_url}")
    print(f"Prometheus: {injector.prometheus_url}")

    # Inject test scenario
    injector.inject_crash_loop(namespace="test", pod="demo-pod")
    print(f"Injected {injector.injected_count} metrics")

    # Wait and verify
    injector.wait_for_scrape(5)

    if injector.verify_metric_exists(
        "kube_pod_container_status_waiting_reason",
        {"namespace": "test", "pod": "demo-pod"},
    ):
        print("Metric verified in Prometheus!")
    else:
        print("Metric not found (Prometheus may not be running)")

    # Clean up
    injector.clear_metrics()
    print("Metrics cleared")
