"""Admission Controller - Connection pool admission control logic."""

import os
from typing import Any

from src.agents.emr.models.batch_registration import BatchRegistration, BatchStatus
from src.agents.emr.models.admission_result import AdmissionResult, ReleaseResult
from src.agents.emr.services.connection_registry import ConnectionRegistry


class AdmissionController:
    """
    Controls admission of batch jobs based on connection availability.

    Implements:
    - Capacity check before allowing new batches
    - Dynamic hint downgrade when capacity is limited
    - Wait time estimation when capacity is exhausted
    """

    def __init__(self, aws_client: Any):
        """
        Initialize controller.

        Args:
            aws_client: AWSClient instance (real or mock)
        """
        self.registry = ConnectionRegistry(aws_client)
        self.default_wait_seconds = int(os.getenv("DEFAULT_WAIT_SECONDS", "30"))
        self.max_wait_seconds = int(os.getenv("MAX_WAIT_SECONDS", "300"))

    def check_admission(
        self,
        src_db_id: int,
        dag_id: str,
        dag_run_id: str,
        table_name: str,
        parallel_hint: int,
    ) -> AdmissionResult:
        """
        Check if a batch can be admitted.

        Args:
            src_db_id: Source database ID
            dag_id: DAG name
            dag_run_id: DAG run ID
            table_name: Target table name
            parallel_hint: Requested parallel degree

        Returns:
            AdmissionResult indicating allowed/wait/downgrade
        """
        limits = self.registry.get_limits(src_db_id)
        current_usage = self.registry.get_current_usage(src_db_id)
        threshold = limits.threshold_connections

        # Case 1: Full capacity available
        if current_usage + parallel_hint <= threshold:
            # Register the batch
            registration = BatchRegistration(
                src_db_id=src_db_id,
                dag_run_id=dag_run_id,
                dag_id=dag_id,
                table_name=table_name,
                parallel_hint=parallel_hint,
                status=BatchStatus.RUNNING,
            )
            self.registry.register_batch(registration)

            return AdmissionResult(
                allowed=True,
                parallel=parallel_hint,
                current_usage=current_usage + parallel_hint,
                available=threshold - current_usage - parallel_hint,
            )

        # Case 2: Try downgrade
        adjusted = self._find_acceptable_parallel(
            current_usage=current_usage,
            threshold=threshold,
            requested=parallel_hint,
            min_parallel=limits.min_parallel,
        )

        if adjusted is not None:
            # Register with downgraded parallel
            registration = BatchRegistration(
                src_db_id=src_db_id,
                dag_run_id=dag_run_id,
                dag_id=dag_id,
                table_name=table_name,
                parallel_hint=adjusted,
                original_parallel=parallel_hint,
                status=BatchStatus.RUNNING,
            )
            self.registry.register_batch(registration)

            return AdmissionResult(
                allowed=True,
                parallel=adjusted,
                downgraded=True,
                original_parallel=parallel_hint,
                reason="partial_capacity_available",
                current_usage=current_usage + adjusted,
                available=threshold - current_usage - adjusted,
            )

        # Case 3: No capacity - must wait
        wait_seconds = self._estimate_wait_time(src_db_id)
        queue_position = self.registry.get_waiting_count(src_db_id) + 1

        return AdmissionResult(
            allowed=False,
            parallel=parallel_hint,
            wait_seconds=wait_seconds,
            queue_position=queue_position,
            reason="connection_limit_exceeded",
            current_usage=current_usage,
            available=threshold - current_usage,
        )

    def release(self, src_db_id: int, dag_run_id: str) -> ReleaseResult:
        """
        Release connections held by a batch.

        Args:
            src_db_id: Source database ID
            dag_run_id: DAG run ID

        Returns:
            ReleaseResult with release info
        """
        registration = self.registry.unregister_batch(src_db_id, dag_run_id)

        if registration is None:
            return ReleaseResult(
                released=False,
                error=f"Batch not found: {dag_run_id}",
            )

        current_usage = self.registry.get_current_usage(src_db_id)

        return ReleaseResult(
            released=True,
            released_connections=registration.parallel_hint,
            current_usage=current_usage,
        )

    def get_status(self) -> dict:
        """
        Get current status of all source databases.

        Returns:
            Status summary dictionary
        """
        return self.registry.get_status_summary()

    def _find_acceptable_parallel(
        self,
        current_usage: int,
        threshold: int,
        requested: int,
        min_parallel: int,
    ) -> int | None:
        """
        Find an acceptable parallel degree through downgrade.

        Tries halving the parallel degree until it fits or hits minimum.

        Args:
            current_usage: Current connection usage
            threshold: Maximum allowed connections
            requested: Originally requested parallel
            min_parallel: Minimum acceptable parallel

        Returns:
            Acceptable parallel degree, or None if none found
        """
        adjusted = requested

        while adjusted >= min_parallel:
            adjusted = adjusted // 2
            if adjusted < min_parallel:
                adjusted = min_parallel

            if current_usage + adjusted <= threshold:
                return adjusted

            if adjusted == min_parallel:
                break

        return None

    def _estimate_wait_time(self, src_db_id: int) -> int:
        """
        Estimate wait time until capacity becomes available.

        Based on running batch count and average completion time.

        Args:
            src_db_id: Source database ID

        Returns:
            Estimated wait time in seconds
        """
        running = self.registry.get_running_batches(src_db_id)

        if not running:
            return self.default_wait_seconds

        # Simple estimation: assume batches complete every 30 seconds on average
        # More sophisticated: use historical completion times
        base_wait = self.default_wait_seconds
        queue_factor = min(len(running) // 10, 5)  # Add delay based on queue size

        estimated = base_wait + (queue_factor * 10)
        return min(estimated, self.max_wait_seconds)
