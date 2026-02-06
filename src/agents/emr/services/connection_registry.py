"""Connection Registry Service - DynamoDB CRUD operations."""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from src.agents.emr.models.batch_registration import BatchRegistration, BatchStatus
from src.agents.emr.models.connection_limits import ConnectionLimits


class ConnectionRegistry:
    """
    Manages batch registrations in DynamoDB.

    Tracks active connections per source database.

    In mock mode (AWS_MOCK=true), uses in-memory storage for testing.
    """

    def __init__(self, aws_client: Any):
        """
        Initialize registry.

        Args:
            aws_client: AWSClient instance (real or mock)
        """
        self.aws_client = aws_client
        self.registry_table = os.getenv(
            "EMR_AGENT_TABLE_REGISTRY", "emr_connection_registry"
        )
        self.limits_table = os.getenv(
            "EMR_AGENT_TABLE_LIMITS", "emr_connection_limits"
        )

        # Check if mock mode
        self._is_mock = os.getenv("AWS_MOCK", "false").lower() == "true"

        # In-memory store for mock mode
        # Key: (src_db_id, dag_run_id) -> BatchRegistration
        self._mock_registry: Dict[tuple, BatchRegistration] = {}

        # Default limits cache (srcDbId -> ConnectionLimits)
        self._limits_cache: Dict[int, ConnectionLimits] = {}
        self._init_default_limits()

    def _init_default_limits(self) -> None:
        """Initialize default connection limits."""
        # ADW (srcDbId: 4) - 1000 connections
        self._limits_cache[4] = ConnectionLimits.default_for_adw()

    def get_limits(self, src_db_id: int) -> ConnectionLimits:
        """
        Get connection limits for a source database.

        Args:
            src_db_id: Source database ID

        Returns:
            ConnectionLimits for the source
        """
        # Check cache first
        if src_db_id in self._limits_cache:
            return self._limits_cache[src_db_id]

        # Try to fetch from DynamoDB (skip in mock mode)
        if not self._is_mock:
            try:
                item = self.aws_client.get_dynamodb_item(
                    table_name=self.limits_table,
                    key={"src_db_id": src_db_id},
                )
                if item:
                    limits = ConnectionLimits.from_dynamodb_item(item)
                    self._limits_cache[src_db_id] = limits
                    return limits
            except Exception:
                pass

        # Return default limits if not found
        return ConnectionLimits(
            src_db_id=src_db_id,
            name=f"Unknown_{src_db_id}",
            db_type="oracle",
            max_connections=100,  # Conservative default
            threshold_percent=90,
            default_parallel=4,
            min_parallel=1,
        )

    def register_batch(self, registration: BatchRegistration) -> bool:
        """
        Register a batch job.

        Args:
            registration: Batch registration info

        Returns:
            True if registered successfully
        """
        try:
            if self._is_mock:
                key = (registration.src_db_id, registration.dag_run_id)
                self._mock_registry[key] = registration
            else:
                self.aws_client.put_dynamodb_item(
                    table_name=self.registry_table,
                    item=registration.to_dynamodb_item(),
                )
            return True
        except Exception as e:
            print(f"Failed to register batch: {e}")
            return False

    def unregister_batch(self, src_db_id: int, dag_run_id: str) -> Optional[BatchRegistration]:
        """
        Unregister a batch job (mark as completed).

        Args:
            src_db_id: Source database ID
            dag_run_id: DAG run ID

        Returns:
            The unregistered batch info, or None if not found
        """
        if self._is_mock:
            key = (src_db_id, dag_run_id)
            registration = self._mock_registry.get(key)
            if registration is None:
                return None

            # Update status to COMPLETED
            registration.status = BatchStatus.COMPLETED
            self._mock_registry[key] = registration
            return registration

        # Real DynamoDB mode
        item = self.aws_client.get_dynamodb_item(
            table_name=self.registry_table,
            key={"src_db_id": src_db_id, "dag_run_id": dag_run_id},
        )

        if not item:
            return None

        registration = BatchRegistration.from_dynamodb_item(item)

        # Update status to COMPLETED
        registration.status = BatchStatus.COMPLETED

        self.aws_client.put_dynamodb_item(
            table_name=self.registry_table,
            item=registration.to_dynamodb_item(),
        )

        return registration

    def get_running_batches(self, src_db_id: int) -> List[BatchRegistration]:
        """
        Get all running batches for a source database.

        Args:
            src_db_id: Source database ID

        Returns:
            List of running batch registrations
        """
        if self._is_mock:
            return [
                reg
                for (db_id, _), reg in self._mock_registry.items()
                if db_id == src_db_id and reg.status == BatchStatus.RUNNING
            ]

        try:
            items = self.aws_client.query_dynamodb(
                table_name=self.registry_table,
                key_condition="src_db_id = :src_db_id",
                expression_values={":src_db_id": src_db_id},
                limit=1000,
            )

            batches = []
            for item in items:
                reg = BatchRegistration.from_dynamodb_item(item)
                if reg.status == BatchStatus.RUNNING:
                    batches.append(reg)

            return batches
        except Exception as e:
            print(f"Failed to get running batches: {e}")
            return []

    def get_current_usage(self, src_db_id: int) -> int:
        """
        Get current connection usage for a source database.

        Args:
            src_db_id: Source database ID

        Returns:
            Total parallel hints of running batches
        """
        running = self.get_running_batches(src_db_id)
        return sum(batch.parallel_hint for batch in running)

    def get_waiting_count(self, src_db_id: int) -> int:
        """
        Get count of waiting batches for a source database.

        Args:
            src_db_id: Source database ID

        Returns:
            Number of waiting batches
        """
        if self._is_mock:
            return sum(
                1
                for (db_id, _), reg in self._mock_registry.items()
                if db_id == src_db_id and reg.status == BatchStatus.WAITING
            )

        try:
            items = self.aws_client.query_dynamodb(
                table_name=self.registry_table,
                key_condition="src_db_id = :src_db_id",
                expression_values={":src_db_id": src_db_id},
                limit=1000,
            )

            return sum(
                1
                for item in items
                if item.get("status") == BatchStatus.WAITING.value
            )
        except Exception:
            return 0

    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get status summary for all source databases.

        Returns:
            Dictionary with usage info per source
        """
        summary = {"sources": {}, "timestamp": datetime.now(timezone.utc).isoformat()}

        # Get status for each known source
        for src_db_id, limits in self._limits_cache.items():
            current_usage = self.get_current_usage(src_db_id)
            running = self.get_running_batches(src_db_id)
            waiting = self.get_waiting_count(src_db_id)

            summary["sources"][str(src_db_id)] = {
                "name": limits.name,
                "max_connections": limits.max_connections,
                "threshold": limits.threshold_connections,
                "current_usage": current_usage,
                "available": limits.threshold_connections - current_usage,
                "active_batches": len(running),
                "waiting_batches": waiting,
            }

        return summary

    def set_limits(self, limits: ConnectionLimits) -> bool:
        """
        Set connection limits for a source database.

        Args:
            limits: Connection limits to set

        Returns:
            True if saved successfully
        """
        try:
            if not self._is_mock:
                self.aws_client.put_dynamodb_item(
                    table_name=self.limits_table,
                    item=limits.to_dynamodb_item(),
                )
            self._limits_cache[limits.src_db_id] = limits
            return True
        except Exception as e:
            print(f"Failed to set limits: {e}")
            return False

    def clear_mock_registry(self) -> None:
        """Clear the mock registry (for testing)."""
        self._mock_registry.clear()
