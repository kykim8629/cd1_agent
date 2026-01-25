"""
MWAA (Managed Workflows for Apache Airflow) Cluster Monitor.

Mock implementation for testing MWAA cluster health monitoring.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class MWAAEnvironmentStatus(str, Enum):
    """MWAA Environment status."""
    AVAILABLE = "AVAILABLE"
    CREATING = "CREATING"
    UPDATING = "UPDATING"
    DELETING = "DELETING"
    CREATE_FAILED = "CREATE_FAILED"
    UPDATE_FAILED = "UPDATE_FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class DAGRunState(str, Enum):
    """Airflow DAG run state."""
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"
    QUEUED = "queued"


@dataclass
class DAGStatus:
    """Status of a single DAG."""
    dag_id: str
    is_paused: bool
    is_active: bool
    last_run_state: Optional[DAGRunState]
    last_run_time: Optional[datetime]
    next_run_time: Optional[datetime]
    failed_runs_24h: int = 0
    success_runs_24h: int = 0


@dataclass
class MWAAEnvironmentHealth:
    """Health status of MWAA environment."""
    environment_name: str
    status: MWAAEnvironmentStatus
    airflow_version: str
    environment_class: str
    scheduler_status: str  # HEALTHY, UNHEALTHY
    webserver_status: str  # HEALTHY, UNHEALTHY
    worker_status: str     # HEALTHY, UNHEALTHY

    # Metrics
    running_tasks: int = 0
    queued_tasks: int = 0
    scheduler_heartbeat_seconds_ago: float = 0

    # DAG stats
    total_dags: int = 0
    active_dags: int = 0
    paused_dags: int = 0
    failed_dags_24h: int = 0

    # Resource utilization
    scheduler_cpu_percent: float = 0
    scheduler_memory_percent: float = 0
    worker_cpu_percent: float = 0
    worker_memory_percent: float = 0

    # Issues
    issues: List[str] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        """Check if environment is healthy."""
        return (
            self.status == MWAAEnvironmentStatus.AVAILABLE
            and self.scheduler_status == "HEALTHY"
            and self.webserver_status == "HEALTHY"
            and self.worker_status == "HEALTHY"
            and len(self.issues) == 0
        )

    @property
    def severity(self) -> str:
        """Get overall severity level."""
        if self.status != MWAAEnvironmentStatus.AVAILABLE:
            return "critical"
        if self.scheduler_status != "HEALTHY" or self.worker_status != "HEALTHY":
            return "critical"
        if self.webserver_status != "HEALTHY":
            return "high"
        if self.failed_dags_24h > 5:
            return "high"
        if self.failed_dags_24h > 0 or self.queued_tasks > 100:
            return "medium"
        return "low"


class MockMWAAMonitor:
    """Mock MWAA cluster monitor for testing."""

    def __init__(self, environment_name: str = "cd1-airflow-prod"):
        """Initialize mock monitor.

        Args:
            environment_name: MWAA environment name
        """
        self.environment_name = environment_name

    def get_environment_health(self, simulate_issues: bool = False) -> MWAAEnvironmentHealth:
        """Get MWAA environment health status.

        Args:
            simulate_issues: If True, randomly simulate some issues

        Returns:
            MWAAEnvironmentHealth object
        """
        # Base healthy state
        health = MWAAEnvironmentHealth(
            environment_name=self.environment_name,
            status=MWAAEnvironmentStatus.AVAILABLE,
            airflow_version="2.8.1",
            environment_class="mw1.medium",
            scheduler_status="HEALTHY",
            webserver_status="HEALTHY",
            worker_status="HEALTHY",
            running_tasks=random.randint(5, 20),
            queued_tasks=random.randint(0, 10),
            scheduler_heartbeat_seconds_ago=random.uniform(1, 10),
            total_dags=15,
            active_dags=12,
            paused_dags=3,
            failed_dags_24h=0,
            scheduler_cpu_percent=random.uniform(20, 50),
            scheduler_memory_percent=random.uniform(30, 60),
            worker_cpu_percent=random.uniform(25, 55),
            worker_memory_percent=random.uniform(35, 65),
            issues=[],
        )

        if simulate_issues:
            # Randomly simulate various issues
            issue_scenarios = [
                self._simulate_scheduler_unhealthy,
                self._simulate_high_queue,
                self._simulate_failed_dags,
                self._simulate_resource_pressure,
                self._simulate_worker_issue,
            ]

            # Pick 1-2 random issues
            num_issues = random.randint(1, 2)
            selected = random.sample(issue_scenarios, num_issues)

            for scenario in selected:
                scenario(health)

        return health

    def get_dag_statuses(self) -> List[DAGStatus]:
        """Get status of all DAGs.

        Returns:
            List of DAGStatus objects
        """
        dag_names = [
            "bdp_agent_detection",
            "hdsp_agent_detection",
            "cost_agent_detection",
            "drift_agent_detection",
            "daily_report_generator",
            "data_sync_pipeline",
            "etl_daily_batch",
            "ml_model_training",
            "alert_aggregator",
            "cleanup_old_logs",
        ]

        statuses = []
        now = datetime.utcnow()

        for dag_id in dag_names:
            # Random state
            is_paused = random.random() < 0.2
            last_state = random.choice(list(DAGRunState))

            statuses.append(DAGStatus(
                dag_id=dag_id,
                is_paused=is_paused,
                is_active=not is_paused,
                last_run_state=last_state,
                last_run_time=now - timedelta(minutes=random.randint(5, 120)),
                next_run_time=now + timedelta(minutes=random.randint(5, 60)),
                failed_runs_24h=random.randint(0, 3) if last_state == DAGRunState.FAILED else 0,
                success_runs_24h=random.randint(10, 50),
            ))

        return statuses

    def _simulate_scheduler_unhealthy(self, health: MWAAEnvironmentHealth) -> None:
        """Simulate scheduler being unhealthy."""
        health.scheduler_status = "UNHEALTHY"
        health.scheduler_heartbeat_seconds_ago = random.uniform(300, 600)
        health.issues.append("Scheduler heartbeat timeout - no heartbeat for 5+ minutes")

    def _simulate_high_queue(self, health: MWAAEnvironmentHealth) -> None:
        """Simulate high task queue."""
        health.queued_tasks = random.randint(150, 300)
        health.issues.append(f"High task queue: {health.queued_tasks} tasks waiting")

    def _simulate_failed_dags(self, health: MWAAEnvironmentHealth) -> None:
        """Simulate multiple failed DAGs."""
        health.failed_dags_24h = random.randint(5, 10)
        health.issues.append(f"Multiple DAG failures: {health.failed_dags_24h} DAGs failed in 24h")

    def _simulate_resource_pressure(self, health: MWAAEnvironmentHealth) -> None:
        """Simulate resource pressure."""
        health.scheduler_cpu_percent = random.uniform(85, 98)
        health.scheduler_memory_percent = random.uniform(80, 95)
        health.issues.append(f"Scheduler resource pressure: CPU {health.scheduler_cpu_percent:.1f}%, Memory {health.scheduler_memory_percent:.1f}%")

    def _simulate_worker_issue(self, health: MWAAEnvironmentHealth) -> None:
        """Simulate worker issues."""
        health.worker_status = "UNHEALTHY"
        health.worker_cpu_percent = random.uniform(90, 99)
        health.issues.append("Worker node unhealthy - high CPU utilization")


def run_mwaa_health_check(
    environment_name: str = "cd1-airflow-prod",
    simulate_issues: bool = True,
) -> Dict[str, Any]:
    """Run MWAA health check and return results.

    Args:
        environment_name: MWAA environment name
        simulate_issues: Whether to simulate random issues

    Returns:
        Health check results dictionary
    """
    monitor = MockMWAAMonitor(environment_name)

    # Get health
    health = monitor.get_environment_health(simulate_issues=simulate_issues)

    # Get DAG statuses
    dag_statuses = monitor.get_dag_statuses()
    failed_dags = [d for d in dag_statuses if d.last_run_state == DAGRunState.FAILED]

    return {
        "environment_name": health.environment_name,
        "status": health.status.value,
        "is_healthy": health.is_healthy,
        "severity": health.severity,
        "airflow_version": health.airflow_version,
        "components": {
            "scheduler": health.scheduler_status,
            "webserver": health.webserver_status,
            "worker": health.worker_status,
        },
        "metrics": {
            "running_tasks": health.running_tasks,
            "queued_tasks": health.queued_tasks,
            "scheduler_heartbeat_seconds_ago": round(health.scheduler_heartbeat_seconds_ago, 1),
        },
        "dags": {
            "total": health.total_dags,
            "active": health.active_dags,
            "paused": health.paused_dags,
            "failed_24h": health.failed_dags_24h,
        },
        "resources": {
            "scheduler_cpu_percent": round(health.scheduler_cpu_percent, 1),
            "scheduler_memory_percent": round(health.scheduler_memory_percent, 1),
            "worker_cpu_percent": round(health.worker_cpu_percent, 1),
            "worker_memory_percent": round(health.worker_memory_percent, 1),
        },
        "issues": health.issues,
        "failed_dags": [
            {
                "dag_id": d.dag_id,
                "last_run_time": d.last_run_time.isoformat() if d.last_run_time else None,
                "failed_runs_24h": d.failed_runs_24h,
            }
            for d in failed_dags
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }
