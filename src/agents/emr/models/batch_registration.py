"""Batch Registration Model."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class BatchStatus(str, Enum):
    """Batch execution status."""

    RUNNING = "RUNNING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class BatchRegistration:
    """
    Represents a batch job's connection registration.

    Stored in DynamoDB emr_connection_registry table.
    """

    src_db_id: int
    dag_run_id: str
    dag_id: str
    table_name: str
    parallel_hint: int
    status: BatchStatus = BatchStatus.RUNNING
    original_parallel: Optional[int] = None  # Set if downgraded
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl: Optional[int] = None  # Unix timestamp for DynamoDB TTL

    def __post_init__(self):
        """Set TTL to 24 hours from now if not provided."""
        if self.ttl is None:
            self.ttl = int(datetime.now(timezone.utc).timestamp()) + 86400  # 24 hours

    @property
    def is_downgraded(self) -> bool:
        """Check if this batch was downgraded."""
        return self.original_parallel is not None

    def to_dynamodb_item(self) -> dict:
        """Convert to DynamoDB item format."""
        item = {
            "src_db_id": self.src_db_id,
            "dag_run_id": self.dag_run_id,
            "dag_id": self.dag_id,
            "table_name": self.table_name,
            "parallel_hint": self.parallel_hint,
            "status": self.status.value,
            "started_at": self.started_at,
            "ttl": self.ttl,
        }
        if self.original_parallel is not None:
            item["original_parallel"] = self.original_parallel
        return item

    @classmethod
    def from_dynamodb_item(cls, item: dict) -> "BatchRegistration":
        """Create from DynamoDB item."""
        return cls(
            src_db_id=int(item["src_db_id"]),
            dag_run_id=item["dag_run_id"],
            dag_id=item["dag_id"],
            table_name=item["table_name"],
            parallel_hint=int(item["parallel_hint"]),
            status=BatchStatus(item["status"]),
            original_parallel=int(item["original_parallel"]) if item.get("original_parallel") else None,
            started_at=item["started_at"],
            ttl=int(item["ttl"]) if item.get("ttl") else None,
        )
