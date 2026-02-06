"""Connection Limits Model."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConnectionLimits:
    """
    Connection limits for a source database.

    Stored in DynamoDB emr_connection_limits table.
    """

    src_db_id: int
    name: str
    db_type: str  # oracle, mysql, postgresql, etc.
    max_connections: int
    threshold_percent: int = 95  # Allow up to 95% of max
    default_parallel: int = 8
    min_parallel: int = 2  # Minimum for downgrade

    @property
    def threshold_connections(self) -> int:
        """Calculate the threshold connection count."""
        return int(self.max_connections * self.threshold_percent / 100)

    def to_dynamodb_item(self) -> dict:
        """Convert to DynamoDB item format."""
        return {
            "src_db_id": self.src_db_id,
            "name": self.name,
            "db_type": self.db_type,
            "max_connections": self.max_connections,
            "threshold_percent": self.threshold_percent,
            "default_parallel": self.default_parallel,
            "min_parallel": self.min_parallel,
        }

    @classmethod
    def from_dynamodb_item(cls, item: dict) -> "ConnectionLimits":
        """Create from DynamoDB item."""
        return cls(
            src_db_id=int(item["src_db_id"]),
            name=item["name"],
            db_type=item["db_type"],
            max_connections=int(item["max_connections"]),
            threshold_percent=int(item.get("threshold_percent", 95)),
            default_parallel=int(item.get("default_parallel", 8)),
            min_parallel=int(item.get("min_parallel", 2)),
        )

    @classmethod
    def default_for_adw(cls) -> "ConnectionLimits":
        """Default limits for ADW (srcDbId: 4)."""
        return cls(
            src_db_id=4,
            name="ADW",
            db_type="oracle",
            max_connections=1000,
            threshold_percent=95,
            default_parallel=8,
            min_parallel=2,
        )
